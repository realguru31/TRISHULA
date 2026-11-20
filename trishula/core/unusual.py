"""v0.41.0 OrderFlow · unusual options (SPX / ES / SPY), each flag on its own toggle:

1 big prints     single-leg print ≥ the market's own rolling size percentile (pct over the last `win` min, or the
                 whole session) AND ≥ floor × the median print in that window — adaptive, no fixed N.
2 bursts         a strike (C+P) trading > k × its own rolling median minute (prior `win` min, zeros included) AND
                 > k × the median busy strike-minute of the market (so a 2-lot on a dead strike is not a burst).
3 paying up      at-or-through (or through-only) the quote — buys at/above the ask, sells at/below the bid — AND
                 size ≥ its own rolling percentile (paying up alone is ~60 % of the tape).
4 new positions  a contract's volume today (whole session, all prints) reaching ratio × its prior-close open
                 interest (OI ≥ min_oi) — the crossing print, coloured by the side that traded more up to it.

Colour everywhere: blue = bullish (calls bought / puts sold), magenta = bearish (puts bought / calls sold).
All causal: every threshold at a minute uses only prints up to and including that minute."""
from __future__ import annotations

import numpy as np
import pandas as pd

MULT = {"SPX": 100.0, "ES": 50.0, "SPY": 100.0}
DEF = dict(big_pct=99.9, big_win=60, big_floor=5.0,
           burst_k=3.0, burst_win=30,
           pay_mode="at or through", pay_pct=99.9, pay_win=60,
           new_ratio=1.0, new_min_oi=100)
FLAGS = ["big", "burst", "pay", "new"]


def _spx_frame(rec, exp: str) -> pd.DataFrame:
    from .orderflow import _spx_map
    df = rec._all_prints()
    keep = (df["exp"].astype(str).values == exp) & (df["ev_type"].astype(str).values != "2")
    if "valid" in df:
        keep &= df["valid"].values.astype(bool)
    d = df[keep]
    if not len(d):
        return pd.DataFrame()
    ts = d["ts_ms"].values.astype("int64")
    S = d["spot"].values.astype(float) if "spot" in d else np.full(len(d), np.nan)
    miss = ~np.isfinite(S)
    if miss.any():
        mp = _spx_map(rec)
        S[miss] = pd.Series((ts[miss] // 60000) * 60000).map(mp).values.astype(float)
        still = ~np.isfinite(S)
        if still.any():
            S[still] = rec.spot_now()[0]
    oi = getattr(rec, "oi", {}) or {}
    sym = d["sym"]
    return pd.DataFrame({"ts_ms": ts, "sym": sym.values,
                         "strike": d["strike"].values.astype(float), "cp": d["cp"].values.astype(float),
                         "px": d["px"].values.astype(float), "size": d["size"].values.astype(float),
                         "bid": d["bid"].values.astype(float), "ask": d["ask"].values.astype(float),
                         "aggr": np.nan_to_num(d["aggr"].values.astype(float)),
                         "sl": ~d["spread_leg"].values.astype(bool) if "spread_leg" in d else np.ones(len(d), bool),
                         "eth": d["eth"].values.astype(bool) if "eth" in d else np.zeros(len(d), bool),
                         "S": S, "oi": pd.Series(sym.values).map(lambda s: oi.get(str(s), np.nan)).values.astype(float)})


def _x_frame(rec, mkt: str) -> pd.DataFrame:
    d = rec.xprints_df(mkt) if hasattr(rec, "xprints_df") else pd.DataFrame()
    if not len(d):
        return pd.DataFrame()
    d = d[d["valid"].values.astype(bool)]
    oi = getattr(rec, "oi", {}) or {}
    sym = d["sym"] if "sym" in d else pd.Series([""] * len(d))
    return pd.DataFrame({"ts_ms": d["ts_ms"].values.astype("int64"), "sym": sym.values,
                         "strike": d["strike"].values.astype(float), "cp": d["cp"].values.astype(float),
                         "px": d["px"].values.astype(float), "size": d["size"].values.astype(float),
                         "bid": d["bid"].values.astype(float), "ask": d["ask"].values.astype(float),
                         "aggr": np.nan_to_num(d["aggr"].values.astype(float)), "sl": ~d["spread_leg"].values.astype(bool),
                         "eth": d["eth"].values.astype(bool), "S": d["und"].values.astype(float),
                         "oi": pd.Series(sym.values).map(lambda s: oi.get(str(s), np.nan)).values.astype(float)})


def frame(rec, mkt: str, exp: str) -> pd.DataFrame:
    """All of today's prints for the market (whole session, sorted), cached on the store size."""
    n = len(rec._all_prints()) if mkt == "SPX" else len(rec.xprints_df(mkt)) if hasattr(rec, "xprints_df") else 0
    key = (mkt, exp, n, len(getattr(rec, "oi", {}) or {}))
    c = getattr(rec, "_unu_frames", {})
    if c.get(mkt, (None,))[0] == key:
        return c[mkt][1]
    f = _spx_frame(rec, exp) if mkt == "SPX" else _x_frame(rec, mkt)
    if len(f):
        f = f.sort_values("ts_ms", kind="stable").reset_index(drop=True)
    c = dict(c)
    c[mkt] = (key, f)
    try:
        rec._unu_frames = c
    except Exception:                                    # noqa: BLE001
        pass
    return f


def roll_thr(ts, size, t0, pct, win, floor):
    """Per print: the size threshold at its minute = max(pct-percentile, floor × median) of `size` over the prior
    `win` minutes INCLUDING its own minute (win None = since t0). Integer-size histogram per minute → fast."""
    if not len(ts):
        return np.array([])
    mi = ((ts - t0) // 60000).astype(int)
    m0, m1 = mi.min(), mi.max()
    M = m1 - m0 + 1
    sz = np.minimum(np.round(size).astype(int), 100_000)
    u, r = np.unique(sz, return_inverse=True)
    H = np.zeros((M + 1, len(u)))
    np.add.at(H, (mi - m0 + 1, r), 1.0)
    C = np.cumsum(H, axis=0)                              # C[k] = counts of minutes < k
    k = np.arange(1, M + 1)
    lo = np.zeros(M, int) if win is None else np.maximum(k - int(win), 0)
    W = C[k] - C[lo]                                     # per minute: counts over the window ending that minute
    tot = W.sum(1)
    cw = np.cumsum(W, axis=1)
    out = np.full(M, np.inf)
    ok = tot >= 30
    if ok.any():
        q = np.argmax(cw[ok] >= (pct / 100.0) * tot[ok, None], axis=1)
        md = np.argmax(cw[ok] >= 0.5 * tot[ok, None], axis=1)
        out[ok] = np.maximum(u[q], floor * u[md])
    return out[mi - m0]


def detect(f: pd.DataFrame, mkt: str, day: pd.Timestamp, legs: str, on: list, p: dict):
    """→ (prints with flag columns + bull, bursts frame) for RTH of `day`. Only flags in `on` are computed."""
    from .timeutil import ET
    t0 = int(pd.Timestamp(day + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)
    t1 = int(pd.Timestamp(day + pd.Timedelta("16h")).tz_localize(ET).timestamp() * 1000)
    if not len(f):
        return pd.DataFrame(), pd.DataFrame()
    f = f.copy()
    f["bull"] = np.sign(f["aggr"].values) * np.sign(f["cp"].values)
    for k in FLAGS:
        f[k] = False
    if "new" in on:                                      # whole session (incl. overnight), all prints
        oi = f["oi"].values
        cum = f.groupby("sym", observed=True)["size"].cumsum().values
        lim = p["new_ratio"] * oi
        cross = (oi >= p["new_min_oi"]) & (cum >= lim) & (cum - f["size"].values < lim)
        f["new"] = cross
        sb = (f["bull"] * f["size"]).groupby(f["sym"], observed=True).cumsum().values
        f["new_bull"] = np.sign(sb)
    rth = (f["ts_ms"].values >= t0) & (f["ts_ms"].values < t1) & ~f["eth"].values
    f = f[rth].reset_index(drop=True)
    if not len(f):
        return f, pd.DataFrame()
    ts = f["ts_ms"].values
    pop = f["sl"].values if legs == "single-leg" else np.ones(len(f), bool)
    if "big" in on:                                      # always single-leg (ES feed has no flag → all)
        sl = f["sl"].values
        thr = np.full(len(f), np.inf)
        thr[sl] = roll_thr(ts[sl], f["size"].values[sl], t0, p["big_pct"],
                           None if p["big_win"] == "day" else p["big_win"], p["big_floor"])
        f["big"] = sl & (f["size"].values >= thr) & (f["bull"].values != 0)
    if "pay" in on:
        px, b, a, ag = f["px"].values, f["bid"].values, f["ask"].values, f["aggr"].values
        if p["pay_mode"] == "through only":
            hit = ((ag > 0) & (px > a + 1e-9)) | ((ag < 0) & (px < b - 1e-9))
        else:
            hit = ((ag > 0) & (px >= a - 1e-9)) | ((ag < 0) & (px <= b + 1e-9))
        thr = np.full(len(f), np.inf)
        thr[pop] = roll_thr(ts[pop], f["size"].values[pop], t0, p["pay_pct"],
                            None if p["pay_win"] == "day" else p["pay_win"], 1.0)
        f["pay"] = pop & hit & (f["size"].values >= thr)
    bursts = pd.DataFrame()
    if "burst" in on:
        g = f[pop]
        m = (g["ts_ms"].values - t0) // 60000
        V = pd.DataFrame({"m": m, "k": g["strike"].values, "v": g["size"].values,
                          "b": g["bull"].values * g["size"].values, "S": g["S"].values})
        A = V.groupby(["m", "k"]).agg(v=("v", "sum"), b=("b", "sum"), S=("S", "mean")).reset_index()
        if len(A):
            P = A.pivot(index="m", columns="k", values="v").reindex(range(int(A["m"].max()) + 1)).fillna(0.0)
            w = int(p["burst_win"])
            med = P.rolling(w, min_periods=min(5, w)).median().shift(1)
            nz = P.where(P > 0)
            busy = nz.stack().dropna().groupby(level=0).median().reindex(P.index).expanding().median().shift(1)
            ok = (P > p["burst_k"] * med) & (P.gt(p["burst_k"] * busy, axis=0)) & (P > 0)
            hits = ok.stack()
            hits = hits[hits].index
            if len(hits):
                bursts = A.set_index(["m", "k"]).loc[hits].reset_index()
                bursts["med"] = [med.at[mm, kk] for mm, kk in zip(bursts["m"], bursts["k"])]
                bursts["ts_ms"] = t0 + bursts["m"] * 60000
                gm = (f["ts_ms"].values - t0) // 60000
                inb = pd.MultiIndex.from_arrays([gm, f["strike"].values]).isin(
                    pd.MultiIndex.from_arrays([bursts["m"].values, bursts["k"].values])) & pop
                if inb.any():                            # table: the biggest print in each burst minute
                    cand = f[inb].assign(_m=gm[inb])
                    top = cand.sort_values("size").groupby(["_m", "strike"]).tail(1).index
                    f.loc[top, "burst"] = True
    f["mult"] = MULT[mkt]
    f["prem"] = f["px"] * f["size"] * f["mult"]
    return f, bursts


def table(f: pd.DataFrame, on: list, mkt: str, n: int, sort: str, min_flags: int) -> pd.DataFrame:
    if not len(f) or not on:
        return pd.DataFrame()
    nf = f[on].sum(1)
    t = f[nf >= max(1, min_flags)].copy()
    if not len(t):
        return pd.DataFrame()
    t["nf"] = nf[t.index]
    from .timeutil import ET
    lab = {"big": "big", "burst": "burst", "pay": "pay-up", "new": "new pos"}
    t = t.sort_values({"premium": "prem", "size": "size", "time": "ts_ms"}[sort], ascending=False)
    t = t.head(n)
    return pd.DataFrame({
        "mkt": mkt,
        "time": pd.to_datetime(t["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.strftime("%H:%M:%S").values,
        "strike": t["strike"].values, "C/P": np.where(t["cp"].values > 0, "C", "P"),
        "size": t["size"].astype(int).values, "price": t["px"].round(2).values,
        "side": np.where(t["aggr"].values > 0, "bought", np.where(t["aggr"].values < 0, "sold", "mid")),
        "read": np.where(t["bull"].values > 0, "bullish", np.where(t["bull"].values < 0, "bearish", "—")),
        "premium $": t["prem"].round(0).astype(int).values,
        "vs spot": (t["strike"] - t["S"]).round(1).values,
        "flags": [" · ".join(lab[k] for k in on if r[k]) for _, r in t[on].iterrows()],
        "_ts": t["ts_ms"].values, "_S": t["S"].values})
