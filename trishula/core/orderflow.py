"""v0.39.0 OrderFlow — the options-delta version of an order-flow delta map / footprint (OFL Delta Map idea).

Each print → signed customer delta = aggressor (+1 at the ask / −1 at the bid) × option delta × size × 100, i.e.
SPX-equivalent shares bought (+: calls bought / puts sold) or sold (−: puts bought / calls sold), placed at the SPX
price at the moment it printed. Aggregated incrementally per 1-minute × 2-point SPX row, single-leg and all prints.
Delta: the print's own live delta, else Black-Scholes at the print's SPX (iv 0.18, like Lean) for replayed prints.
18 Nov check (research): single-leg tracks the bar's move a little tighter than all prints (5-min corr +0.66 vs
+0.60); NEITHER predicts the next bar — a reading tool for turns / divergences, not an entry signal."""
from __future__ import annotations

import numpy as np
import pandas as pd

ROW = 2.0                                            # SPX points per footprint row


def _spx_map(rec) -> dict:
    """minute (ms) → SPX 1-minute close, for prints without a recorded spot."""
    try:
        c = rec.candles_df()
        if len(c):
            return dict(zip((c["ts_ms"].astype("int64") // 60000) * 60000, c["close"].astype(float)))
    except Exception:                                # noqa: BLE001
        pass
    return {}


def _mid(d: pd.DataFrame) -> np.ndarray:
    """v0.42.0: printed strictly inside the bid/ask (two sides meeting halfway — the "zero" write-up ignores these)."""
    if not {"px", "bid", "ask"} <= set(d.columns):
        return np.zeros(len(d), bool)
    px, b, a = (d[c].values.astype(float) for c in ("px", "bid", "ask"))
    return (px > b + 1e-9) & (px < a - 1e-9)


def minutes(rec, exp: str) -> pd.DataFrame:
    """Per minute × 2-pt SPX row: sl_buy, sl_sell, al_buy, al_sell (shares of SPX delta). Incremental on the print store."""
    from .lean import _bs_delta
    from . import expiry as EX
    cols = ["m", "row", "sl_buy", "sl_sell", "al_buy", "al_sell", "slx_buy", "slx_sell", "alx_buy", "alx_sell"]
    df = rec._all_prints()
    with rec.lock:
        st_ = getattr(rec, "_oflow", None)
        gen = getattr(rec, "_pgen", 0)
        if st_ is None or st_["exp"] != exp or st_["gen"] != gen or st_["n"] > len(df) or not st_.get("x"):
            st_ = {"exp": exp, "gen": gen, "n": 0, "agg": None, "x": True}
        n0 = st_["n"]
    if len(df) > n0:
        new = df.iloc[n0:]
        keep = (new["exp"].astype(str).values == exp) & (new["ev_type"].astype(str).values != "2")
        if "eth" in new:
            keep &= ~new["eth"].values.astype(bool)
        if "valid" in new:
            keep &= new["valid"].values.astype(bool)
        new = new[keep]
        new = new[np.isfinite(new["aggr"].values.astype(float)) & (new["aggr"].values.astype(float) != 0)]
        if len(new):
            ts = new["ts_ms"].values.astype("int64")
            m = (ts // 60000) * 60000
            spot = new["spot"].values.astype(float) if "spot" in new else np.full(len(new), np.nan)
            miss = ~np.isfinite(spot)
            if miss.any():
                mp = _spx_map(rec)
                spot[miss] = pd.Series(m[miss]).map(mp).values.astype(float)
                still = ~np.isfinite(spot)
                if still.any():
                    s_now, _ = rec.spot_now()
                    spot[still] = s_now
            cp = new["cp"].values.astype(float)
            dl = np.abs(new["delta"].values.astype(float)) if "delta" in new else np.full(len(new), np.nan)
            dm = ~np.isfinite(dl)
            if dm.any():
                tyr = (EX.end_ms(exp) - ts[dm]) / (365.25 * 86400e3)
                dl[dm] = _bs_delta(spot[dm], new["strike"].values.astype(float)[dm], tyr, cp[dm])
            sd = np.sign(new["aggr"].values.astype(float)) * np.sign(cp) * dl * new["size"].values.astype(float) * 100
            sl = ~new["spread_leg"].values.astype(bool) if "spread_leg" in new else np.ones(len(new), bool)
            ok = np.isfinite(spot) & np.isfinite(sd)
            nm = ~_mid(new)                              # v0.42.0: x = without prints traded inside the spread
            a = pd.DataFrame({"m": m[ok], "row": np.floor(spot[ok] / ROW) * ROW,
                              "sl_buy": np.where(sl, np.clip(sd, 0, None), 0.0)[ok],
                              "sl_sell": np.where(sl, np.clip(-sd, 0, None), 0.0)[ok],
                              "al_buy": np.clip(sd, 0, None)[ok], "al_sell": np.clip(-sd, 0, None)[ok],
                              "slx_buy": np.where(sl & nm, np.clip(sd, 0, None), 0.0)[ok],
                              "slx_sell": np.where(sl & nm, np.clip(-sd, 0, None), 0.0)[ok],
                              "alx_buy": np.where(nm, np.clip(sd, 0, None), 0.0)[ok],
                              "alx_sell": np.where(nm, np.clip(-sd, 0, None), 0.0)[ok]})
            agg = a if st_["agg"] is None else pd.concat([st_["agg"], a], ignore_index=True)
            st_["agg"] = agg.groupby(["m", "row"], as_index=False, sort=True).sum()
        st_ = dict(st_, n=len(df))
        with rec.lock:
            rec._oflow = st_
    return st_["agg"] if st_["agg"] is not None else pd.DataFrame(columns=cols)


# ── v0.40.0: ES options + SPY options (same view, own underlying) ─────────────────────────────────────────────────────
XROW = {"ES": 2.0, "SPY": 0.2}


def _bs_d(S, K, T, iv, cp):
    from scipy.special import ndtr
    T = np.maximum(T, 1e-6)
    d1 = (np.log(np.maximum(S, 1e-9) / K) + 0.5 * iv * iv * T) / (iv * np.sqrt(T))
    nd = ndtr(d1)
    return np.where(cp > 0, nd, nd - 1.0), d1


def _bs_px(S, K, T, iv, cp):
    from scipy.special import ndtr
    T = np.maximum(T, 1e-6)
    sd = iv * np.sqrt(T)
    d1 = (np.log(np.maximum(S, 1e-9) / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    c = S * ndtr(d1) - K * ndtr(d2)
    return np.where(cp > 0, c, c - S + K)


def implied_delta(px, S, K, T, cp):
    """|delta| from each trade's own price: IV by vectorised bisection (0.01–3.0), then Black-Scholes (r = 0)."""
    lo, hi = np.full(len(px), 0.01), np.full(len(px), 3.0)
    for _ in range(30):
        mid = (lo + hi) / 2
        v = _bs_px(S, K, T, mid, cp)
        up = v > px
        hi = np.where(up, mid, hi)
        lo = np.where(up, lo, mid)
    d, _ = _bs_d(S, K, T, (lo + hi) / 2, cp)
    return np.abs(d)


def xminutes(rec, mkt: str) -> pd.DataFrame:
    """Like minutes() for ES / SPY options: per minute × row of the UNDERLYING price (ES 2 pt, SPY 0.2): buy / sell in
    SPX-equivalent delta shares (delta × size × multiplier × underlying ÷ SPX), single-leg and all, plus und o/h/l/c.
    Incremental on the store."""
    from .timeutil import ET
    cols = ["m", "row", "sl_buy", "sl_sell", "al_buy", "al_sell", "slx_buy", "slx_sell", "alx_buy", "alx_sell"]
    df = rec.xprints_df(mkt) if hasattr(rec, "xprints_df") else pd.DataFrame()
    key = f"_oflow_{mkt}"
    with rec.lock:
        st_ = getattr(rec, key, None)
        if st_ is None or st_["n"] > len(df) or not st_.get("x"):
            st_ = {"n": 0, "agg": None, "und": None, "x": True}
        n0 = st_["n"]
    info = (getattr(rec, "xinfo", {}) or {}).get(mkt, {})
    if len(df) > n0 and info:
        new = df.iloc[n0:]
        keep = new["valid"].values.astype(bool) & ~new["eth"].values.astype(bool) & np.isfinite(new["und"].values) \
            & (new["aggr"].values != 0) & np.isfinite(new["aggr"].values) & (new["px"].values > 0)
        new = new[keep]
        if len(new):
            ts = new["ts_ms"].values.astype("int64")
            exp_end = pd.Timestamp(info["exp"] + " 16:00").tz_localize(ET).value // 10**6
            T = np.maximum(exp_end - ts, 60_000) / (365.25 * 86400e3)
            S = new["und"].values.astype(float); K = new["strike"].values.astype(float)
            cp = new["cp"].values.astype(float)
            dl = implied_delta(new["px"].values.astype(float), S, K, T, cp)
            mult = 50.0 if mkt == "ES" else 100.0
            s_now, _ = rec.spot_now()
            scale = (S / s_now) if (s_now and np.isfinite(s_now)) else np.ones(len(S))
            sd = np.sign(new["aggr"].values.astype(float)) * np.sign(cp) * dl * new["size"].values.astype(float) * mult * scale
            sl = ~new["spread_leg"].values.astype(bool)
            m = (ts // 60000) * 60000
            r = XROW[mkt]
            nm = ~_mid(new)
            a = pd.DataFrame({"m": m, "row": np.floor(S / r) * r,
                              "sl_buy": np.where(sl, np.clip(sd, 0, None), 0.0), "sl_sell": np.where(sl, np.clip(-sd, 0, None), 0.0),
                              "al_buy": np.clip(sd, 0, None), "al_sell": np.clip(-sd, 0, None),
                              "slx_buy": np.where(sl & nm, np.clip(sd, 0, None), 0.0),
                              "slx_sell": np.where(sl & nm, np.clip(-sd, 0, None), 0.0),
                              "alx_buy": np.where(nm, np.clip(sd, 0, None), 0.0),
                              "alx_sell": np.where(nm, np.clip(-sd, 0, None), 0.0)})
            agg = a if st_["agg"] is None else pd.concat([st_["agg"], a], ignore_index=True)
            st_["agg"] = agg.groupby(["m", "row"], as_index=False, sort=True).sum()
            u = pd.DataFrame({"m": m, "o": S, "h": S, "l": S, "c": S})
            u = u.groupby("m").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).reset_index()
            if st_["und"] is not None:
                u = pd.concat([st_["und"], u]).groupby("m").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"),
                                                                 c=("c", "last")).reset_index()
            st_["und"] = u
        st_ = dict(st_, n=len(df))
        with rec.lock:
            setattr(rec, key, st_)
    agg = st_["agg"] if st_["agg"] is not None else pd.DataFrame(columns=cols)
    und = st_["und"] if st_["und"] is not None else pd.DataFrame(columns=["m", "o", "h", "l", "c"])
    return agg, und
