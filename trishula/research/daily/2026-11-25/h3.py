import sys, datetime as dt, json
sys.path.insert(0, "/tmp/claude-0/-home-claude-trishula/dff9d8c6-57a3-5af1-a46d-2b8a03bb2a16/scratchpad/app/trishula")
import numpy as np, pandas as pd
from scipy.signal import argrelextrema
from core import terrain as T
X = "/tmp/claude-0/-home-claude-trishula/dff9d8c6-57a3-5af1-a46d-2b8a03bb2a16/scratchpad/data/"
DAYS = {"2026-11-12": "trishula_day_20261112_close", "2026-11-16": "trishula_day_20261116_close",
        "2026-11-18": "trishula_day_20261118_close", "2026-11-20": "trishula_day_20261120_close",
        "2026-11-23": "trishula_day_20261123_1400", "2026-11-24": "d1124_1400full"}
if len(sys.argv) > 1: DAYS = dict(a.split("=") for a in sys.argv[1:])
ET = "America/New_York"
import os
GREEK = os.environ.get("GREEK", "Gamma")

def chains(Z, sign, thr):
    pts = {}
    for j in range(Z.shape[1]):
        colv = Z[:, j] * sign
        idx = argrelextrema(colv, np.greater, order=6)[0]
        pts[j] = [i for i in idx if colv[i] > thr and 4 <= i < Z.shape[0] - 4]
    used = set(); out = []
    for j0 in range(Z.shape[1]):
        for i0 in pts.get(j0, []):
            if (j0, i0) in used: continue
            ch = [(j0, i0)]; used.add((j0, i0)); j, i = j0, i0
            while j + 1 < Z.shape[1]:
                cand = [k for k in pts.get(j + 1, []) if abs(k - i) <= 4 and (j + 1, k) not in used]
                if not cand: break
                k = min(cand, key=lambda q: abs(q - i)); ch.append((j + 1, k)); used.add((j + 1, k)); j, i = j + 1, k
            if len(ch) >= 8: out.append(ch)
    out.sort(key=len, reverse=True)
    return out[:4]

def outcome(hi, lo, i0, L, above):
    """from minute index i0 (touch), 30 min: reversal / break / none"""
    for k in range(i0, min(i0 + 31, len(hi))):
        thr_b = hi[k] >= L + 8 if above else lo[k] <= L - 8
        thr_r = lo[k] <= L - 8 if above else hi[k] >= L + 8
        if thr_b: return "B"
        if thr_r: return "R"
    return None

def touch(hi, lo, i_start, levels, above):
    """levels: array per minute (nan = no line). first minute within 2 pts."""
    for k in range(i_start, min(i_start + 60, len(hi))):
        L = levels[k - i_start]
        if not L == L: continue
        if (above and hi[k] >= L - 2) or ((not above) and lo[k] <= L + 2): return k, L
    return None, None

rows = []
for day, d in DAYS.items():
    D = X + d + "/"
    c = pd.read_parquet(D + "chain_snapshots.parquet"); c["exp"] = c["exp"].astype(str)
    c["type"] = np.where(c.cp > 0, "call", "put"); c["volume"] = c["day_volume"]
    try:
        book = pd.read_parquet(D + "book.parquet"); book["exp"] = book["exp"].astype(str)
    except Exception: book = None
    s = pd.read_parquet(D + "spx1m.parquet").sort_values("ts_ms")
    s["t"] = pd.to_datetime(s.ts_ms, unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    dd = dt.date.fromisoformat(day)
    s = s[(s.t.dt.date == dd) & (s.t.dt.time >= dt.time(9, 30)) & (s.t.dt.time < dt.time(16, 0))].reset_index(drop=True)
    hi, lo, tt = s.high.values, s.low.values, s.t.values
    exp0 = day
    for cpm in range(10 * 60, 15 * 60 + 1, 15):
        now = dt.datetime.combine(dd, dt.time(cpm // 60, cpm % 60))
        now_ms = int(pd.Timestamp(now).tz_localize(ET).value // 10**6)
        cc = c[c.ts_ms <= now_ms]
        if not len(cc): continue
        snap = cc.ts_ms.max()
        if now_ms - snap > 10 * 60_000: continue
        ch = c[(c.ts_ms == snap) & (c.exp == exp0)].copy()
        if not len(ch) or not ch.gamma.notna().any(): continue
        spot = float(ch.spot.dropna().iloc[-1])
        exps = [exp0]
        if book is not None:
            bk = book[book.exp != exp0].assign(dsign=lambda x: np.where(x.cp > 0, 1.0, -1.0) * .35, day_volume=0.0)
            ch = pd.concat([ch, bk[[k for k in bk.columns if k in ch.columns or k == "dsign"]]], ignore_index=True)
            exps += sorted(bk.exp.unique())
        pg, Z, taus = T.terrain_grid(ch, spot, exps, now, dd, greek=GREEK, weighting="Vol else OI (legacy)",
                                     signed=False, units="minis", vol_w=.25,
                                     taus_override=[dt.datetime.combine(dd, dt.time(9, 30)) + dt.timedelta(seconds=x) for x in np.linspace(0, 6.5 * 3600, 84)])
        tmin = np.array([(pd.Timestamp(x) - pd.Timestamp(dd)).total_seconds() / 60 for x in taus])
        i_now = np.searchsorted(tt, np.datetime64(now))
        if i_now >= len(tt) - 5: continue
        spot_px = s.close.values[i_now - 1] if i_now > 0 else spot
        p95 = np.percentile(np.abs(Z), 95); mx = np.abs(Z).max()
        for var, thr in (("A", .25 * mx), ("B", .25 * p95)):
            for sgn, kind in ((1, "MAX"), (-1, "MIN")):
                for chn in chains(Z, sgn, thr):
                    cols = {j: pg[i] for j, i in chn}
                    # level per minute after now
                    mins = np.arange(cpm + 1, cpm + 61)
                    lev = np.array([cols.get(int(np.argmin(np.abs(tmin - m))), np.nan) if tmin[0] <= m <= tmin[-1] else np.nan for m in mins])
                    L0 = next((x for x in lev if x == x), np.nan)
                    if not L0 == L0: continue
                    dist = L0 - spot_px
                    if abs(dist) < 5: continue
                    above = dist > 0
                    k, L = touch(hi, lo, i_now, lev, above)
                    res = outcome(hi, lo, k, L, above) if k is not None else None
                    # null
                    nr = nb = 0
                    for dd_ in range(int(abs(dist)) - 10, int(abs(dist)) + 11):
                        if dd_ < 5 or abs(dd_ - abs(dist)) < 3: continue
                        Lf = spot_px + (dd_ if above else -dd_)
                        k2, L2 = touch(hi, lo, i_now, np.full(60, Lf), above)
                        if k2 is None: continue
                        o2 = outcome(hi, lo, k2, L2, above)
                        nr += o2 == "R"; nb += o2 == "B"
                    rows.append(dict(day=day, cp=cpm, var=var, kind=kind, dist=dist, level=L0,
                                     touch_t=(str(pd.Timestamp(tt[k]).time()) if k is not None else None),
                                     touch_i=k, res=res, null_r=nr, null_b=nb))
    print(day, "done", flush=True)
R = pd.DataFrame(rows); R.to_pickle(f"h3_raw_{GREEK.split()[0]}.pkl" if len(sys.argv) == 1 else f"h3_raw_oos_{GREEK.split()[0]}.pkl"); print(len(R))
