"""v0.41.0 OrderFlow · unusual options (SPX / ES / SPY), each flag on its own toggle.

ORDERS, not prints: prints on the same contract, same side, same second are one order (a 500-lot fills as 50–70
prints). Size that matters = delta notional (|Δ| × contracts × multiplier × underlying), Δ from the order's own price.

1 big orders     the top N orders of the day so far by delta notional (top-N adapts by itself — no fixed size).
2 bursts         a strike (C+P) trading > k × its own rolling median minute (prior `win` min, zeros included) and
                 > k × the market's typical busy strike-minute; the top N by that multiple.
3 paying up      orders that bought at/through the ask or sold at/through the bid (or through only); top N by delta notional.
4 new positions  a contract's volume today (whole session, all prints) reaching ratio × its prior-close open
                 interest (OI ≥ min_oi) — the order that crossed, coloured by the side that traded more up to it; top N by OI.

Colour everywhere: blue = bullish (calls bought / puts sold), magenta = bearish (puts bought / calls sold)."""
from __future__ import annotations

import numpy as np
import pandas as pd

MULT = {"SPX": 100.0, "ES": 50.0, "SPY": 100.0}
DEF = dict(big_n=10, burst_k=3.0, burst_win=30, burst_n=10, pay_mode="at or through", pay_n=10,
           new_ratio=1.0, new_min_oi=100, new_n=10)
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


def detect(f: pd.DataFrame, mkt: str, day: pd.Timestamp, legs: str, on: list, p: dict, exp: str = ""):
    """→ (orders with flag columns, bursts frame) for RTH of `day`. Only flags in `on` are computed."""
    from .timeutil import ET
    from .orderflow import implied_delta
    t0 = int(pd.Timestamp(day + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)
    t1 = int(pd.Timestamp(day + pd.Timedelta("16h")).tz_localize(ET).timestamp() * 1000)
    if not len(f):
        return pd.DataFrame(), pd.DataFrame()
    f = f.copy()
    f["bull"] = np.sign(f["aggr"].values) * np.sign(f["cp"].values)
    f["new"] = False
    if "new" in on:                                      # whole session (incl. overnight), all prints
        oi = f["oi"].values
        cum = f.groupby("sym", observed=True)["size"].cumsum().values
        lim = p["new_ratio"] * oi
        f["new"] = (oi >= p["new_min_oi"]) & (cum >= lim) & (cum - f["size"].values < lim)
        f["new_bull"] = np.sign((f["bull"] * f["size"]).groupby(f["sym"], observed=True).cumsum().values)
    rth = (f["ts_ms"].values >= t0) & (f["ts_ms"].values < t1) & ~f["eth"].values
    f = f[rth]
    if legs == "single-leg":
        f = f[f["sl"].values]
    f = f[f["aggr"].values != 0]
    if not len(f):
        return pd.DataFrame(), pd.DataFrame()
    px, b, a, ag = f["px"].values, f["bid"].values, f["ask"].values, f["aggr"].values
    if p.get("pay_mode") == "through only":
        f["paid"] = ((ag > 0) & (px > a + 1e-9)) | ((ag < 0) & (px < b - 1e-9))
    else:
        f["paid"] = ((ag > 0) & (px >= a - 1e-9)) | ((ag < 0) & (px <= b + 1e-9))
    f["side"] = np.sign(ag)
    f["sec"] = f["ts_ms"].values // 1000
    f["pv"] = px * f["size"].values
    if "new_bull" not in f:
        f["new_bull"] = 0.0
    g = f.groupby([f["sym"].astype(str).values, f["side"].values, f["sec"].values], sort=False)
    o = g.agg(ts_ms=("ts_ms", "first"), sym=("sym", "first"), strike=("strike", "first"), cp=("cp", "first"),
              aggr=("side", "first"), size=("size", "sum"), pv=("pv", "sum"), S=("S", "first"), n=("px", "size"),
              paid=("paid", "max"), new=("new", "max"), oi=("oi", "first"), new_bull=("new_bull", "last"), bull=("bull", "first"))
    o = o.reset_index(drop=True)
    o["px"] = o["pv"] / o["size"].clip(lower=1)
    end = pd.Timestamp(f"{exp or day.date()} 16:00").tz_localize(ET).value // 10**6
    T = np.maximum(end - o["ts_ms"].values, 60_000) / (365.25 * 86400e3)
    o["d"] = implied_delta(o["px"].values, o["S"].values, o["strike"].values, T, o["cp"].values)
    o["mult"] = MULT[mkt]
    o["prem"] = o["pv"] * o["mult"]
    o["dn"] = o["d"] * o["size"] * o["mult"] * o["S"]
    o = o.sort_values("ts_ms", kind="stable").reset_index(drop=True)
    for k in ("big", "burst", "pay"):
        o[k] = False
    if "big" in on:
        o.loc[o["dn"].nlargest(int(p["big_n"])).index, "big"] = True
    if "new" in on:                                      # the N biggest positions opened (largest OI crossed)
        keep = o.loc[o["new"], "oi"].nlargest(int(p["new_n"])).index
        o["new"] = False
        o.loc[keep, "new"] = True
    if "pay" in on:
        o.loc[o.loc[o["paid"], "dn"].nlargest(int(p["pay_n"])).index, "pay"] = True
    bursts = pd.DataFrame()
    if "burst" in on:
        m = (f["ts_ms"].values - t0) // 60000
        V = pd.DataFrame({"m": m, "k": f["strike"].values, "v": f["size"].values,
                          "b": f["bull"].values * f["size"].values, "S": f["S"].values})
        A = V.groupby(["m", "k"]).agg(v=("v", "sum"), b=("b", "sum"), S=("S", "mean")).reset_index()
        P = A.pivot(index="m", columns="k", values="v").reindex(range(int(A["m"].max()) + 1)).fillna(0.0)
        w = int(p["burst_win"])
        med = P.rolling(w, min_periods=min(5, w)).median().shift(1)
        busy = P.where(P > 0).stack().dropna().groupby(level=0).median().reindex(P.index).expanding().median().shift(1)
        R = P / med.clip(lower=1.0)
        ok = (P > p["burst_k"] * med) & (P.gt(p["burst_k"] * busy, axis=0)) & (P > 0)
        r = R.where(ok).stack().dropna()
        if len(r):
            r = r.nlargest(int(p["burst_n"]))
            bursts = A.set_index(["m", "k"]).loc[r.index].reset_index()
            bursts["med"] = [med.at[mm, kk] for mm, kk in zip(bursts["m"], bursts["k"])]
            bursts["ts_ms"] = t0 + bursts["m"] * 60000
            om = (o["ts_ms"].values - t0) // 60000
            inb = pd.MultiIndex.from_arrays([om, o["strike"].values]).isin(
                pd.MultiIndex.from_arrays([bursts["m"].values, bursts["k"].values]))
            if inb.any():                                # table: the biggest order in each burst minute
                top = o[inb].assign(_m=om[inb]).sort_values("dn").groupby(["_m", "strike"]).tail(1).index
                o.loc[top, "burst"] = True
    return o, bursts


def table(f: pd.DataFrame, on: list, mkt: str, n: int, sort: str, min_flags: int) -> pd.DataFrame:
    if not len(f) or not on:
        return pd.DataFrame()
    nf = f[on].sum(1)
    t = f[nf >= max(1, min_flags)].copy()
    if not len(t):
        return pd.DataFrame()
    t["nf"] = nf[t.index]
    from .timeutil import ET
    lab = {"big": "big", "burst": "burst", "pay": "paying up", "new": "new pos"}
    t = t.sort_values({"delta $": "dn", "premium": "prem", "size": "size", "time": "ts_ms"}[sort], ascending=False)
    t = t.head(n)
    return pd.DataFrame({
        "mkt": mkt,
        "time": pd.to_datetime(t["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.strftime("%H:%M:%S").values,
        "strike": t["strike"].values, "C/P": np.where(t["cp"].values > 0, "C", "P"),
        "size": t["size"].astype(int).values, "price": t["px"].round(2).values,
        "side": np.where(t["aggr"].values > 0, "bought", np.where(t["aggr"].values < 0, "sold", "mid")),
        "read": np.where(t["bull"].values > 0, "bullish", np.where(t["bull"].values < 0, "bearish", "—")),
        "premium $": t["prem"].round(0).astype(int).values, "delta $M": (t["dn"] / 1e6).round(1).values,
        "vs spot": (t["strike"] - t["S"]).round(1).values,
        "flags": [" · ".join(lab[k] for k in on if r[k]) for _, r in t[on].iterrows()],
        "_ts": t["ts_ms"].values, "_S": t["S"].values})
