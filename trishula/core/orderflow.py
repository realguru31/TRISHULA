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


def minutes(rec, exp: str) -> pd.DataFrame:
    """Per minute × 2-pt SPX row: sl_buy, sl_sell, al_buy, al_sell (shares of SPX delta). Incremental on the print store."""
    from .lean import _bs_delta
    from . import expiry as EX
    cols = ["m", "row", "sl_buy", "sl_sell", "al_buy", "al_sell"]
    df = rec._all_prints()
    with rec.lock:
        st_ = getattr(rec, "_oflow", None)
        gen = getattr(rec, "_pgen", 0)
        if st_ is None or st_["exp"] != exp or st_["gen"] != gen or st_["n"] > len(df):
            st_ = {"exp": exp, "gen": gen, "n": 0, "agg": None}
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
            a = pd.DataFrame({"m": m[ok], "row": np.floor(spot[ok] / ROW) * ROW,
                              "sl_buy": np.where(sl, np.clip(sd, 0, None), 0.0)[ok],
                              "sl_sell": np.where(sl, np.clip(-sd, 0, None), 0.0)[ok],
                              "al_buy": np.clip(sd, 0, None)[ok], "al_sell": np.clip(-sd, 0, None)[ok]})
            agg = a if st_["agg"] is None else pd.concat([st_["agg"], a], ignore_index=True)
            st_["agg"] = agg.groupby(["m", "row"], as_index=False, sort=True).sum()
        st_ = dict(st_, n=len(df))
        with rec.lock:
            rec._oflow = st_
    return st_["agg"] if st_["agg"] is not None else pd.DataFrame(columns=cols)
