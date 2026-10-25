import numpy as np, pandas as pd
from scipy.stats import norm
def lean_frames(o, S, minutes, near=60.0, iv=0.18, exp_close=None):
    """o: t, strike, cp, bidv, askv (1-min, one expiry). S: spot per minute.
    Returns per-minute bull / bear delta-weighted contracts for OTM strikes within ±near, and the ladder (minute × offset)."""
    o = o[(o.t >= minutes[0]) & (o.t <= minutes[-1])].copy()
    s = S.reindex(o.t).values
    T = np.maximum((exp_close - o.t).dt.total_seconds().values / (365 * 86400), 120 / (365 * 86400))
    ivv = o["iv"].fillna(iv).clip(0.05, 1.5).values if "iv" in o else np.full(len(o), iv)
    d1 = (np.log(s / o.strike.values) + 0.5 * ivv * ivv * T) / (ivv * np.sqrt(T))
    ad = np.abs(np.where(o.cp.values == 1, norm.cdf(d1), norm.cdf(d1) - 1))
    off = o.strike.values - s
    otm = ((o.cp.values == 1) & (off > 0)) | ((o.cp.values == -1) & (off < 0))
    keep = otm & (np.abs(off) <= near)
    bull = np.where(o.cp.values == 1, o.askv.values, o.bidv.values) * ad      # calls bought / puts sold
    bear = np.where(o.cp.values == 1, o.bidv.values, o.askv.values) * ad      # calls sold / puts bought
    d = pd.DataFrame({"t": o.t.values, "bull": bull * keep, "bear": bear * keep, "off": np.round(off / 5) * 5, "keep": keep})
    g = d.groupby("t")[["bull", "bear"]].sum().reindex(minutes).fillna(0)
    lad = d[d.keep].assign(net=lambda z: z.bull - z.bear).pivot_table(index="t", columns="off", values="net", aggfunc="sum").reindex(minutes).fillna(0)
    return g, lad
def alerts(g, S, W=15, share=0.15, flat=5.0, min_act=None, cool=20):
    b = g.bull.rolling(W, min_periods=W).sum(); r = g.bear.rolling(W, min_periods=W).sum()
    sh = (b - r) / (b + r + 1e-9); act = b + r
    rng = S.reindex(g.index).rolling(W, min_periods=W).apply(lambda x: x.max() - x.min(), raw=True)
    thr = act.expanding(30).median() if min_act is None else min_act
    sig = pd.Series(0, index=g.index); last = -10_000
    for i, t in enumerate(g.index):
        if i - last < cool or not np.isfinite(sh.iat[i]): continue
        if act.iat[i] >= (thr.iat[i] if hasattr(thr, "iat") else thr) and rng.iat[i] <= flat and abs(sh.iat[i]) >= share:
            sig.iat[i] = int(np.sign(sh.iat[i])); last = i
    return sig, sh, rng
