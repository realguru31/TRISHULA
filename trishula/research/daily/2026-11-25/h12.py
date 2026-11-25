import sys, datetime as dt, glob, os, zipfile
sys.path.insert(0, "/tmp/claude-0/-home-claude-trishula/dff9d8c6-57a3-5af1-a46d-2b8a03bb2a16/scratchpad/app/trishula")
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from core import terrain as T
ET = "America/New_York"
Z = "/tmp/claude-0/-home-claude-trishula/dff9d8c6-57a3-5af1-a46d-2b8a03bb2a16/scratchpad/zips/"
files = {"2026-11-12": "trishula_day_20261112_close.zip", "2026-11-16": "trishula_day_20261116_close.zip", "2026-11-18": "trishula_day_20261118_close.zip",
         "2026-11-20": "trishula_day_20261120_close.zip", "2026-11-23": "trishula_day_20261123_1400.zip", "2026-11-24": "trishula_day_20261124_close.zip", "2026-11-25": "trishula_day_20261125_1400.zip"}
CFG = {"best (naive·book.35·Vol-else-OI·vw.25)": dict(signed=False, wt="Vol else OI (legacy)", vw=0.25, book=0.35),
       "control (naive·OI opening·no book)": dict(signed=False, wt="OI (opening book)", vw=1.0, book=0.0)}
rows = []
for day, f in files.items():
    z = zipfile.ZipFile(Z + f); nm = z.namelist()
    c = pd.read_parquet(z.open("chain_snapshots.parquet")); c["exp"] = c["exp"].astype(str)
    s = pd.read_parquet(z.open("spx1m.parquet")); s["t"] = pd.to_datetime(s.ts_ms, unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    s = s[s.t.dt.date == pd.Timestamp(day).date()].set_index("t").sort_index()
    bk = pd.read_parquet(z.open("book.parquet")) if "book.parquet" in nm else pd.DataFrame()
    if len(bk): bk["exp"] = bk["exp"].astype(str)
    d = dt.date.fromisoformat(day); e0 = day
    for hh in np.arange(10.0, 15.01, 0.5):
        now = dt.datetime.combine(d, dt.time(int(hh), int(round((hh % 1) * 60))))
        now_ms = int(pd.Timestamp(now).tz_localize(ET).value // 10**6)
        cs = c[(c.ts_ms <= now_ms) & (c.ts_ms >= now_ms - 10 * 60000)]
        if not len(cs): continue
        ch = cs[cs.ts_ms == cs.ts_ms.max()].copy(); ch["type"] = np.where(ch.cp > 0, "call", "put"); ch["volume"] = ch["day_volume"]
        spot = float(ch.spot.dropna().iloc[-1]) if ch.spot.notna().any() else np.nan
        fut = s[(s.index > now) & (s.index <= now + pd.Timedelta("60min"))]
        if not np.isfinite(spot) or len(fut) < 50: continue
        rng = fut.high.max() - fut.low.min(); mv = fut.close.iloc[-1] - spot
        for cname, cf in CFG.items():
            chx, ex = ch, [e0]
            if cf["book"] and len(bk):
                b2 = bk[bk.exp != e0].assign(dsign=lambda x: np.where(x.cp > 0, 1.0, -1.0) * cf["book"], day_volume=0.0)
                chx = pd.concat([ch, b2[[k for k in b2.columns if k in ch.columns or k == "dsign"]]], ignore_index=True); ex = ex + sorted(b2.exp.unique())
            try:
                pg, F, taus = T.terrain_grid(chx, spot, ex, now, d, greek="Gamma", field_mode=T.FIELD_MODES[0], vol_adj=0.0,
                                             p_min=spot - 60, p_max=spot + 60, n_price=121, n_time=40, weighting=cf["wt"], signed=cf["signed"], units="minis", vol_w=cf["vw"])
            except Exception as er:
                continue
            j = int(np.argmin([abs((t - now).total_seconds()) for t in taus]))
            col = F[:, j]; at = float(np.interp(spot, pg, col))
            zc = pg[np.where(np.diff(np.sign(col)) != 0)[0]]
            nearest = zc[np.argmin(np.abs(zc - spot))] if len(zc) else np.nan
            rows.append(dict(day=day, t=now.strftime("%H:%M"), cfg=cname, gamma_at_spot=at, range60=rng, move60=mv,
                             boundary=nearest, dist=(nearest - spot) if nearest == nearest else np.nan))
R = pd.DataFrame(rows); R.to_pickle("/tmp/claude-0/-home-claude-trishula/dff9d8c6-57a3-5af1-a46d-2b8a03bb2a16/scratchpad/work/h12.pkl")
for cname, g in R.groupby("cfg"):
    rho = spearmanr(g.gamma_at_spot, g.range60)
    red, grn = g[g.gamma_at_spot < 0], g[g.gamma_at_spot > 0]
    # day-demeaned (range differs by day)
    g = g.assign(rr=g.range60 - g.groupby("day").range60.transform("mean"))
    rho_d = spearmanr(g.gamma_at_spot, g.rr)
    hh = g.dropna(subset=["dist"]); hh = hh[hh.dist.abs() > 2]
    toward = (np.sign(hh.dist) == np.sign(hh.move60)).mean()
    print(f"\n{cname}: {len(g)} checkpoints on {g.day.nunique()} days")
    print(f"  H1 γ at spot vs next-60-min range: rho {rho.correlation:+.2f} (p {rho.pvalue:.2f}) · within-day rho {rho_d.correlation:+.2f} (p {rho_d.pvalue:.2f})")
    print(f"     red (−γ) {len(red)} → range {red.range60.mean():.1f} pts · green (+γ) {len(grn)} → range {grn.range60.mean():.1f} pts")
    print(f"  H2 moved toward the nearest zero boundary within 60 min: {toward:.0%} of {len(hh)} (50 % = no magnet) · median distance {hh.dist.abs().median():.0f} pts")
