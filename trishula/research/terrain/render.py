import sys, datetime as dt
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
src = open("dan/sweep.py").read(); exec(src[:src.index("res = []")])
from matplotlib.colors import LinearSegmentedColormap
cm = LinearSegmentedColormap.from_list("rg", ["#b3261e", "#111111", "#1f9d55"])
def ours(tname, sign, exset, wt, vw, scale):
    t = TARGETS[tname]; now = dt.datetime(2026, 11, 24, *t["now"]); now_ms = int(pd.Timestamp(now).tz_localize(ET).value // 10**6)
    snap = c[c.ts_ms <= now_ms].ts_ms.max(); ch = c[c.ts_ms == snap].copy(); ch["type"] = np.where(ch.cp > 0, "call", "put"); ch["volume"] = ch["day_volume"]
    spot = float(ch["spot"].dropna().iloc[-1]); ex = exps_all[:1]
    if "book" in exset:
        w = 0.35 if ".35" in exset else 1.0
        bk = book[~book.exp.isin(ex)].assign(dsign=lambda d: np.where(d.cp > 0, 1.0, -1.0) * w, day_volume=0.0)
        ch = pd.concat([ch, bk[[k for k in bk.columns if k in ch.columns or k == "dsign"]]], ignore_index=True); ex = ex + sorted(bk.exp.unique())
    pg, Z, _ = T.terrain_grid(ch, spot, ex, now, day, greek="Gamma", field_mode=T.FIELD_MODES[0], vol_adj=0.0, p_min=prices[0], p_max=prices[-1],
                              n_price=len(prices), n_time=84, weighting=wt, signed=(sign != "naive"), units="minis", vol_w=vw)
    V = np.clip(Z / 250, -1, 1) if scale == "Dan" else T.terrain_scale(Z, "Percentile", None, 95)[0]
    return V, spot
taus = [dt.datetime(2026, 11, 24, 9, 30) + dt.timedelta(seconds=s) for s in np.linspace(0, 6.5 * 3600, 84)]
mins = np.array([t.hour * 60 + t.minute for t in taus]); ext = [mins[0] / 60, mins[-1] / 60, prices[0], prices[-1]]
fig, A = plt.subplots(2, 3, figsize=(16, 7.5))
for r, tn in enumerate(("12:47", "14:04")):
    t = TARGETS[tn]; nowh = t["now"][0] + t["now"][1] / 60
    panels = [("Dan " + tn, dan_field(t, prices, mins), None),
              ("OURS now: signed single-leg · book .35 · OI+Vol · Dan ±250", *ours(tn, "signed single-leg", "0DTE+book.35", "OI + Volume", 0.05, "Dan")),
              ("BEST: naive · book .35 · Vol-else-OI · vol w .25 · Percentile 95", *ours(tn, "naive", "0DTE+book.35", "Vol else OI (legacy)", 0.25, "pct"))]
    for a, (ttl, F, sp) in zip(A[r], panels):
        a.imshow(F, origin="lower", aspect="auto", cmap=cm, vmin=-1, vmax=1, extent=ext)
        a.axvline(nowh, color="w", ls="--", lw=1); a.set_title(ttl, fontsize=9)
        if sp: a.axhline(sp, color="w", ls=":", lw=1)
plt.tight_layout(); plt.savefig("dan/terrain_vs_dan.png", dpi=90)
