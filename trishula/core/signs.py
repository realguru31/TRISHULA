"""Flow-signed dealer inference on the tastytrade tape (vs3dgbt gbt_dsign_map port).

Per (strike, type) the customer net initiative and total volume:
    net = Σ size · sign(aggr)   (ASK/ABOVE_ASK = bought, BID/BELOW_BID = sold,
                                 MID signed by aggressorSide — user decision 2026-10-18)
    tot = Σ size                (every print, MID included)
Seed = prior RTH + overnight on this expiry (replayed prints; 5-min candle
bidVolume/askVolume fills the window the 1,000-print replay cap could not reach).
Live = today's prints since 09:30 ET. dsign = clip(−(net_seed+net_live)/(tot_seed+tot_live), −1, 1)
(dealer = opposite of customer), exactly vs3dgbt. Legs without evidence: NaN
(callers apply naive × GBT_UNSEEDED_W = 0.2).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from .timeutil import ET

UNSEEDED_W = 0.2


def prev_trading_day(d: date) -> date:
    p = d - timedelta(days=1)
    while p.weekday() > 4:
        p -= timedelta(days=1)
    return p


def _anchor(exp: str, session: str | None) -> date:
    """The trading session the signing is about: the expiry itself for 0DTE/1DTE,
    the current session (0DTE date) for any later expiry."""
    e = date.fromisoformat(exp)
    return min(e, date.fromisoformat(session)) if session else e


def seed_from_ms(exp: str, session: str | None = None) -> int:
    """Prior session 09:30 ET (prior RTH + overnight) before the anchor session."""
    p = prev_trading_day(_anchor(exp, session))
    return int(datetime.combine(p, time(9, 30), tzinfo=ET).timestamp() * 1000)


def open_ms(exp: str, session: str | None = None) -> int:
    return int(datetime.combine(_anchor(exp, session), time(9, 30), tzinfo=ET).timestamp() * 1000)


def _typ(cp):
    return np.where(np.asarray(cp) == 1, "call", "put")


def side_stats_prints(p: pd.DataFrame, lo_ms=None, hi_ms=None, single_leg=False) -> pd.DataFrame:
    """DataFrame(sym, strike, type, net, tot, first_ms, n) from classified prints."""
    if p is None or p.empty:
        return pd.DataFrame(columns=["sym", "strike", "type", "net", "tot", "first_ms", "n"])
    d = p[p["ev_type"].astype(str) != "2"] if "ev_type" in p else p
    if lo_ms is not None:
        d = d[d["ts_ms"] >= lo_ms]
    if hi_ms is not None:
        d = d[d["ts_ms"] < hi_ms]
    if single_leg:
        d = d[~d["spread_leg"].astype(bool)]
    if d.empty:
        return pd.DataFrame(columns=["sym", "strike", "type", "net", "tot", "first_ms", "n"])
    d = d.assign(_n=np.sign(d["aggr"]) * d["size"], _t=d["size"])
    g = d.groupby(["sym", "strike", "cp"], as_index=False).agg(
        net=("_n", "sum"), tot=("_t", "sum"), first_ms=("ts_ms", "min"), n=("ts_ms", "size"))
    g["type"] = _typ(g["cp"])
    return g.drop(columns="cp")


def side_stats_candles(c5: pd.DataFrame, first_print: dict, lo_ms: int, hi_ms: int) -> pd.DataFrame:
    """Candle fill: per sym, 5-min bars inside [lo, hi) that END before the sym's first
    replayed print (so candles and prints never double-count)."""
    if c5 is None or c5.empty:
        return pd.DataFrame(columns=["sym", "net", "tot"])
    d = c5[(c5["ts_ms"] >= lo_ms) & (c5["ts_ms"] < hi_ms)].copy()
    if d.empty:
        return pd.DataFrame(columns=["sym", "net", "tot"])
    cut = d["sym"].map(lambda s: first_print.get(s, hi_ms))
    d = d[d["ts_ms"] + 5 * 60_000 <= cut]
    d["net"] = d["askv"] - d["bidv"]
    return d.groupby("sym", as_index=False).agg(net=("net", "sum"), tot=("vol", "sum"))


def dsign_table(prints: pd.DataFrame, candles5: pd.DataFrame, legs: dict, exp: str,
                now_ms: int, single_leg=False, session: str | None = None) -> pd.DataFrame:
    """Per leg of `exp`: seed/live net & tot, dsign and coverage."""
    lo, op = seed_from_ms(exp, session), open_ms(exp, session)
    cut = min(op, now_ms)
    p = prints[prints["exp"] == exp] if (prints is not None and len(prints)) else pd.DataFrame()
    sp = side_stats_prints(p, lo, cut, single_leg).set_index("sym") if len(p) else None
    lv = side_stats_prints(p, op, None, single_leg).set_index("sym") if (len(p) and now_ms > op) else None
    first = {} if sp is None else sp["first_ms"].to_dict()
    cf = None if single_leg else side_stats_candles(candles5, first, lo, cut).set_index("sym")
    rows = []
    for sym, (ex, k, cp) in legs.items():
        if ex != exp:
            continue
        sn = st = ln = lt = cn = ct = 0.0
        fp, npr = None, 0
        if sp is not None and sym in sp.index:
            sn, st, fp, npr = float(sp.at[sym, "net"]), float(sp.at[sym, "tot"]), int(sp.at[sym, "first_ms"]), int(sp.at[sym, "n"])
        if cf is not None and sym in cf.index:
            cn, ct = float(cf.at[sym, "net"]), float(cf.at[sym, "tot"])
        if lv is not None and sym in lv.index:
            ln, lt = float(lv.at[sym, "net"]), float(lv.at[sym, "tot"])
        net, tot = sn + cn + ln, st + ct + lt
        rows.append({"sym": sym, "strike": k, "cp": cp, "type": "call" if cp == 1 else "put",
                     "seed_net": sn + cn, "seed_tot": st + ct, "live_net": ln, "live_tot": lt,
                     "net": net, "tot": tot,
                     "dsign": float(np.clip(-net / tot, -1, 1)) if tot > 0 else np.nan,
                     "seed_dsign": float(np.clip(-(sn + cn) / (st + ct), -1, 1)) if (st + ct) > 0 else np.nan,
                     "first_print_ms": fp, "n_replayed": npr, "candle_tot": ct})
    return pd.DataFrame(rows)


def coverage_text(t: pd.DataFrame) -> str:
    if t is None or t.empty:
        return "seed: none yet"
    seeded = int((t["seed_tot"] > 0).sum())
    cfill = int((t["candle_tot"] > 0).sum())
    fp = t["first_print_ms"].dropna()
    late = ""
    if len(fp):
        q = pd.to_datetime(fp, unit="ms", utc=True).dt.tz_convert(ET)
        late = f" · replay reaches back to {q.min():%a %H:%M} (latest-start leg {q.max():%a %H:%M})"
    return (f"🧬 seed {seeded}/{len(t)} legs · candle-filled {cfill}{late} · "
            f"live {int((t['live_tot'] > 0).sum())} legs")
