import numpy as np, pandas as pd
def wings(o, S, start, end, cw=(30, 90), pz=(-25, 5)):
    """5-min bins: call-wing net bought (calls spot+30..+90) and put-zone net bought (puts spot−25..+5)."""
    o = o[(o.t >= start) & (o.t < end)].copy()
    o["b"] = o.t.dt.floor("5min"); o["off"] = o.strike.values - S.reindex(o.t.dt.floor("1min")).values
    o["net"] = o.askv - o.bidv
    c = o[(o.cp == 1) & o.off.between(*cw)].groupby("b")[["net", "askv", "bidv"]].sum()
    p = o[(o.cp == -1) & o.off.between(*pz)].groupby("b")[["net", "askv", "bidv"]].sum()
    bins = pd.date_range(pd.Timestamp(start).floor("5min"), pd.Timestamp(end), freq="5min", inclusive="left")
    return pd.DataFrame({"cw_net": c.net, "cw_tot": c.askv + c.bidv, "pz_net": p.net, "pz_tot": p.askv + p.bidv}).reindex(bins).fillna(0)
def setup_signals(w, S, k=4, need=3, ratio=1.4, rng_max=15.0, cool=3):
    """bear: call wing net SOLD (sold ≥ ratio × bought) in ≥ need of last k bins AND put zone net bought over last 3 bins
       AND 15-min price range ≤ rng_max. bull: mirror. strength = call-wing sold/bought over the last k bins."""
    sold = (w.cw_tot - w.cw_net) / 2; bought = (w.cw_tot + w.cw_net) / 2
    bear_bin = (sold >= ratio * bought) & (w.cw_tot > 0); bull_bin = (bought >= ratio * sold) & (w.cw_tot > 0)
    nb = bear_bin.rolling(k, min_periods=need).sum(); nu = bull_bin.rolling(k, min_periods=need).sum()
    pz3 = w.pz_net.rolling(3, min_periods=3).sum()
    Sb = S.reindex(w.index + pd.Timedelta("4min")).values
    rng = pd.Series(S.rolling(15, min_periods=10).apply(lambda x: x.max() - x.min(), raw=True).reindex(w.index + pd.Timedelta("4min")).values, index=w.index)
    st = (sold.rolling(k, min_periods=need).sum() / bought.rolling(k, min_periods=need).sum().clip(lower=1))
    out = []; last = -99
    for i, b in enumerate(w.index):
        if i - last < cool: continue
        if nb.iat[i] >= need and pz3.iat[i] > 0 and rng.iat[i] <= rng_max:
            out.append((b + pd.Timedelta("5min"), -1, float(st.iat[i]))); last = i
        elif nu.iat[i] >= need and pz3.iat[i] < 0 and rng.iat[i] <= rng_max:
            out.append((b + pd.Timedelta("5min"), 1, float(1 / max(st.iat[i], 1e-9)))); last = i
    return pd.DataFrame(out, columns=["t", "dir", "strength"])
