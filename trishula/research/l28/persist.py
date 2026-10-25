import numpy as np, pandas as pd
def strike_bins(o, S, start, end, bin_min=5, span=120):
    """per 5-min bin, per (strike, cp): bought, sold; plus bearish/bullish orientation and offset from spot."""
    o = o[(o.t >= start) & (o.t < end)].copy()
    o["b"] = o.t.dt.floor(f"{bin_min}min")
    g = o.groupby(["b", "strike", "cp"])[["askv", "bidv"]].sum().reset_index()
    g["spot"] = S.reindex(g.b).values
    g["off"] = g.strike - g.spot
    g = g[g.off.abs() <= span]
    g["net"] = g.askv - g.bidv                                   # customer net bought
    g["tot"] = g.askv + g.bidv
    g["bear"] = np.where(g.cp == 1, -g.net, g.net)               # + = bearish (calls sold / puts bought)
    return g
def persistent(g, k=4, need=3, ratio=1.5, min_tot=100):
    """mark (bin, strike, cp) where the same side won ≥ need of the last k bins (each ≥ ratio and ≥ min_tot)."""
    g = g.sort_values("b").copy()
    win = np.where((g.askv >= ratio * g.bidv) & (g.tot >= min_tot), 1, np.where((g.bidv >= ratio * g.askv) & (g.tot >= min_tot), -1, 0))
    g["win"] = win
    out = []
    for (kx, cp), h in g.groupby(["strike", "cp"]):
        h = h.set_index("b").win
        bins = pd.date_range(h.index.min(), h.index.max(), freq="5min"); h = h.reindex(bins).fillna(0)
        bs = (h == 1).rolling(k, min_periods=1).sum(); ss = (h == -1).rolling(k, min_periods=1).sum()
        for b in h.index[(bs >= need) | (ss >= need)]:
            side = 1 if bs[b] >= need else -1               # customer bought (1) / sold (−1)
            out.append((b, kx, cp, side, -side if cp == 1 else side))   # bear: +1 if calls sold or puts bought
    return pd.DataFrame(out, columns=["b", "strike", "cp", "side", "bear"])
