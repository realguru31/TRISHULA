import sys, datetime as dt, json
sys.path.insert(0, "/home/claude/trishula/trishula")
import numpy as np, pandas as pd
from PIL import Image
from scipy.ndimage import median_filter
from scipy.stats import spearmanr
from scipy.signal import argrelextrema
from core import terrain as T, signs as SG
S0 = "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/"
D = S0 + "days/x/d1125_1200/"; ET = "America/New_York"
day = dt.date(2026, 11, 25); now = dt.datetime(2026, 11, 25, 10, 22)
img = np.asarray(Image.open(S0 + "dan/d1022_g.png").convert("RGB")).astype(float)
Y = lambda p: 158 + (p - 7100) * (369 - 158) / (6900 - 7100)
Xm = lambda m: 113 + (m - 608) / 0.5865
prices = np.linspace(6815, 7195, 96)
taus = [dt.datetime(2026, 11, 25, 9, 30) + dt.timedelta(seconds=s) for s in np.linspace(0, 6.5 * 3600, 84)]
mins = np.array([t.hour * 60 + t.minute + t.second / 60 for t in taus])
r, g, b = img[..., 0], img[..., 1], img[..., 2]
cyan = (g > 150) & (b > 150) & (r < 120)
v = np.where(g > r, g - np.maximum(r, b), -(r - np.maximum(g, b)))
v = median_filter(np.where(cyan, np.nan, v), size=9)
DF = np.full((len(prices), len(mins)), np.nan)
for i, p in enumerate(prices):
    for j, m in enumerate(mins):
        y, x = int(Y(p)), int(Xm(m))
        if 56 <= y <= 440 and 50 <= x <= 694:
            DF[i, j] = v[y, x]
DF = np.clip(DF / (np.nanpercentile(np.abs(DF), 98) or 1), -1, 1)
nowm = 10 * 60 + 22
proj = mins >= nowm
# Dan's middle cyan line (local MIN near spot): per projection column, cyan y within 6950–7050
dline = np.full(len(mins), np.nan)
for j, m in enumerate(mins):
    if m < nowm: continue
    x = int(Xm(m))
    if not (50 <= x <= 694): continue
    ys = np.nonzero(cyan[56:441, max(0, x - 1):x + 2].any(1))[0] + 56
    ps = 7100 + (ys - 158) * (6900 - 7100) / (369 - 158)
    ps = ps[(ps > 6950) & (ps < 7050)]
    if len(ps): dline[j] = ps.mean()
print("Dan min line:", {f"{int(m)//60}:{int(m)%60:02d}": round(x) for m, x in zip(mins[::8], dline[::8]) if x == x})
c = pd.read_parquet(D + "chain_snapshots.parquet"); c["exp"] = c["exp"].astype(str)
book = pd.read_parquet(D + "book.parquet"); book["exp"] = book["exp"].astype(str)
P = pd.read_parquet(D + "prints.parquet"); C5 = pd.read_parquet(D + "candles5.parquet"); legs = json.load(open(D + "legs.json"))
for col in ("exp", "sym", "ev_type"):
    if col in P: P[col] = P[col].astype(str)
now_ms = int(pd.Timestamp(now).tz_localize(ET).value // 10**6)
snap = c[c.ts_ms <= now_ms].ts_ms.max(); ch0 = c[c.ts_ms == snap].copy()
ch0["type"] = np.where(ch0.cp > 0, "call", "put"); ch0["volume"] = ch0["day_volume"]
spot = float(ch0["spot"].dropna().iloc[-1]); exps_all = sorted(ch0.exp.unique()); print("spot", spot, exps_all)
signs = {"naive": None, "signed all-prints": "dsign"}
for e in exps_all[:2]:
    for sl, nm in ((True, "signed single-leg"), (False, "opening (seed)")):
        tb = SG.dsign_table(P, C5, legs, e, now_ms, single_leg=sl)
        if len(tb):
            col = "seed_dsign" if nm.startswith("opening") else "dsign"
            signs.setdefault(nm, {}).update(dict(zip(tb["sym"].astype(str), tb[col])))
def minlines(Z):
    thr = 0.08 * (np.percentile(np.abs(Z), 95) or 1)
    pts = {}
    for j in range(Z.shape[1]):
        cv = -Z[:, j]; idx = argrelextrema(cv, np.greater, order=4)[0]
        pts[j] = [i for i in idx if cv[i] > thr and 2 <= i < Z.shape[0] - 2]
    return pts
res = []
for sname, sv in signs.items():
    ch = ch0.copy()
    if isinstance(sv, dict): ch["dsign"] = ch["sym"].astype(str).map(sv)
    for exset in ("0DTE", "0+1DTE", "0DTE+book.35", "0DTE+book1", "0+1DTE+book.35"):
        ex = exps_all[:1] if exset.startswith("0DTE") else exps_all[:2]; chx = ch
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
                                                  p_min=prices[0], p_max=prices[-1], n_price=len(prices), weighting=wt,
                                                  signed=(sname != "naive"), units="minis", vol_w=vw, taus_override=taus)
                    except Exception as ex_:
                        continue
                    m = np.isfinite(DF) & (np.abs(DF) > 0.15)
                    sg = float((np.sign(Z[m]) == np.sign(DF[m])).mean())
                    V, _ = T.terrain_scale(Z, "Percentile", None, 95)
                    mm = np.isfinite(DF)
                    rho = spearmanr(V[mm], DF[mm]).correlation
                    rho_p = spearmanr(V[mm & proj[None, :]], DF[mm & proj[None, :]]).correlation
                    pts = minlines(Z); dd = []; cov = 0; tot = 0
                    for j in np.nonzero(np.isfinite(dline))[0]:
                        tot += 1
                        near = [pg[i] for i in pts[j] if abs(pg[i] - dline[j]) <= 40]
                        if near: cov += 1; dd.append(min(abs(x - dline[j]) for x in near))
                    # where is our deepest min within 6950–7050 at 13:00 / 15:30
                    def at(hm):
                        j = int(np.argmin(np.abs(mins - hm))); c_ = [pg[i] for i in pts[j] if 6900 <= pg[i] <= 7100]
                        return round(min(c_, key=lambda x: abs(x - 7000))) if c_ else None
                    res.append(dict(sign=sname, exps=exset, weighting=wt, vol_w=vw, field=fm.split()[0], sign_agree=sg,
                                    rho=rho, rho_proj=rho_p, line_cov=cov / max(tot, 1), line_err=np.median(dd) if dd else np.nan,
                                    min13=at(780), min1530=at(930), at_spot=float(np.interp(spot, pg, Z[:, int(np.argmin(np.abs(mins - nowm)))]))))
R = pd.DataFrame(res); R.to_pickle(S0 + "dan/sweep1125.pkl"); print(len(R))
