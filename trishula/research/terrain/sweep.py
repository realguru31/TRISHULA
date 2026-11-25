import sys, itertools, datetime as dt, json
sys.path.insert(0, "/home/claude/trishula/trishula")
import numpy as np, pandas as pd
from PIL import Image
from scipy.ndimage import median_filter
from scipy.stats import spearmanr
from core import terrain as T, signs as SG
D = "days/x/d1124_1400full/"
ET = "America/New_York"
# ── Dan's pictures → signed intensity on (price, time) ──
TARGETS = {
 "12:47": dict(img="dan/d1247_gamma.png", box=(60, 10, 558, 414), y=((57, 7260), (393, 7140)), x=((112, 10*60+12), (491, 15*60+7)), now=(12, 47)),
 "14:04": dict(img="dan/d1404_gamma.png", box=(2, 90, 493, 495), y=((99, 7260), (436, 7140)), x=((47, 10*60+12), (418, 15*60+7)), now=(14, 4)),
}
def dan_field(t, prices, mins):
    a = np.asarray(Image.open(t["img"]).convert("RGB")).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = np.where(g > r, (g - np.maximum(r, b)), -(r - np.maximum(g, b)))
    v = median_filter(v, size=9)                                   # wipe candles, dashed lines, pink line
    (y1, p1), (y2, p2) = t["y"]; (x1, m1), (x2, m2) = t["x"]
    Y = y1 + (prices - p1) * (y2 - y1) / (p2 - p1); X = x1 + (mins - m1) * (x2 - x1) / (m2 - m1)
    x0, yy0, x9, yy9 = t["box"]
    out = np.full((len(prices), len(mins)), np.nan)
    for i, yy in enumerate(Y):
        for j, xx in enumerate(X):
            if yy0 <= yy <= yy9 and x0 <= xx <= x9:
                out[i, j] = v[int(yy), int(xx)]
    s = np.nanpercentile(np.abs(out), 98) or 1
    return np.clip(out / s, -1, 1)
# ── our data ──
c = pd.read_parquet(D + "chain_snapshots.parquet"); c["exp"] = c["exp"].astype(str)
book = pd.read_parquet(D + "book.parquet"); book["exp"] = book["exp"].astype(str)
P = pd.read_parquet(D + "prints.parquet"); C5 = pd.read_parquet(D + "candles5.parquet"); legs = json.load(open(D + "legs.json"))
for col in ("exp", "sym", "ev_type"):
    if col in P: P[col] = P[col].astype(str)
day = dt.date(2026, 11, 24); exps_all = sorted(c.exp.unique())
prices = np.linspace(7120, 7262, 72)
res = []
for tname, t in TARGETS.items():
    now = dt.datetime(2026, 11, 24, *t["now"]); now_ms = int(pd.Timestamp(now).tz_localize(ET).value // 10**6)
    snap = c[c.ts_ms <= now_ms].ts_ms.max(); ch0 = c[c.ts_ms == snap].copy()
    ch0["type"] = np.where(ch0.cp > 0, "call", "put"); ch0["volume"] = ch0["day_volume"]
    spot = float(ch0["spot"].dropna().iloc[-1])
    n_time = 84; taus = [dt.datetime(2026, 11, 24, 9, 30) + dt.timedelta(seconds=s) for s in np.linspace(0, 6.5 * 3600, n_time)]
    mins = np.array([tt.hour * 60 + tt.minute + tt.second / 60 for tt in taus])
    DF = dan_field(t, prices, mins)
    proj = mins >= t["now"][0] * 60 + t["now"][1]
    signs = {"naive": None, "signed all-prints": "dsign"}
    for e in exps_all[:2]:
        for sl, nm in ((True, "signed single-leg"), (False, "opening (seed)")):
            tb = SG.dsign_table(P, C5, legs, e, now_ms, single_leg=sl)
            if len(tb):
                col = "seed_dsign" if nm.startswith("opening") else "dsign"
                signs.setdefault(nm, {}).update(dict(zip(tb["sym"].astype(str), tb[col])))
    for sname, sv in signs.items():
        ch = ch0.copy()
        if isinstance(sv, dict):
            ch["dsign"] = ch["sym"].astype(str).map(sv)
        for exset in ("0DTE", "0+1DTE", "0DTE+book.35", "0DTE+book1", "0+1DTE+book.35"):
            ex = exps_all[:1] if exset.startswith("0DTE") else exps_all[:2]
            chx = ch
            if "book" in exset:
                w = 0.35 if ".35" in exset else 1.0
                bk = book[~book.exp.isin(ex)].assign(dsign=lambda d: np.where(d.cp > 0, 1.0, -1.0) * w, day_volume=0.0)
                chx = pd.concat([ch, bk[[k for k in bk.columns if k in ch.columns or k == "dsign"]]], ignore_index=True)
                ex = ex + sorted(bk.exp.unique())
            for wt in T.WEIGHTS:
                for vw in ((0.05, 0.25, 1.0) if "Vol" in wt or "+" in wt else (1.0,)):
                    for fm in T.FIELD_MODES:
                        try:
                            pg, Z, _ = T.terrain_grid(chx, spot, ex, now, day, greek="Gamma", field_mode=fm, vol_adj=0.0,
                                                      p_min=prices[0], p_max=prices[-1], n_price=len(prices), n_time=n_time,
                                                      weighting=wt, signed=(sname != "naive"), units="minis", vol_w=vw)
                        except Exception as ex_:
                            continue
                        m = np.isfinite(DF) & (np.abs(DF) > 0.15)
                        sg_all = float((np.sign(Z[m]) == np.sign(DF[m])).mean())
                        mp = m & proj[None, :]
                        sg_proj = float((np.sign(Z[mp]) == np.sign(DF[mp])).mean()) if mp.any() else np.nan
                        for scale in ("Dan ±250", "Percentile 95", "Percentile 99", "StdDev"):
                            if scale.startswith("Dan"): V = np.clip(Z / 250.0, -1, 1)
                            elif scale.startswith("Percentile"): V, _ = T.terrain_scale(Z, "Percentile", None, int(scale.split()[1]))
                            else: V, _ = T.terrain_scale(Z, "StdDev", None, 95)
                            for pw in (0.4, 1.0):
                                Vi = T.terrain_intensity(V, "Power", pw)
                                mm = np.isfinite(DF)
                                rho = spearmanr(Vi[mm], DF[mm]).correlation
                                rho_p = spearmanr(Vi[mm & proj[None, :]], DF[mm & proj[None, :]]).correlation
                                res.append(dict(target=tname, sign=sname, exps=exset, weighting=wt, vol_w=vw,
                                                field=fm.split()[0], scale=scale, power=pw, sign_agree=sg_all,
                                                sign_agree_proj=sg_proj, shape_rho=rho, shape_rho_proj=rho_p))
R = pd.DataFrame(res); R.to_pickle("dan/sweep.pkl")
print(len(R), "rows")
