"""VS3D data layer: builds vs3dgbt-shaped frames (chain with type and dsign, spot,
bars, open, opening straddle, 09:35 lock, strip history) from the recorder."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import book as B
from .timeutil import ET


def _typed(ch: pd.DataFrame) -> pd.DataFrame:
    if ch is None or ch.empty:
        return pd.DataFrame()
    c = ch.copy()
    c["type"] = np.where(c["cp"] == 1, "call", "put")
    return c


def naive_et(ms) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(ms) / 1000, ET).replace(tzinfo=None)


def et_ms(d: dt.date, t: dt.time) -> int:
    return int(dt.datetime.combine(d, t, tzinfo=ET).timestamp() * 1000)


def session_date(rec) -> dt.date:
    """The session the screen is about: today's 0DTE date, or the last traded day
    when no candle exists yet for it (weekend / pre-market shows Friday's path)."""
    d = rec.exps[0] if rec.exps else dt.date.today()
    c = rec.candles_df()
    if len(c):
        days = pd.to_datetime(c["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.date
        if not (days == d).any():
            past = days[days <= d]
            if len(past):
                return past.max()
    return d


def bars_for(rec, day: dt.date, upto_ms: int | None = None) -> pd.DataFrame:
    c = rec.candles_df()
    if c.empty:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "ts_ms"])
    lo, hi = et_ms(day, dt.time(9, 30)), et_ms(day, dt.time(16, 0))
    c = c[(c["ts_ms"] >= lo) & (c["ts_ms"] < hi)]
    if upto_ms:
        c = c[c["ts_ms"] <= upto_ms]
    t = pd.to_datetime(c["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return pd.DataFrame({"t": t.values, "o": c["open"].values, "h": c["high"].values, "l": c["low"].values,
                         "c": c["close"].values, "ts_ms": c["ts_ms"].values})


def snapshot_times(rec, exp: str) -> list[int]:
    h = rec.chain_df()
    if h.empty:
        return []
    return sorted(h.loc[h["exp"] == exp, "ts_ms"].unique().tolist())


def frame(rec, exps: list[str], ts_ms: int | None):
    """(chain, spot, ts) for the selected expiries at a snapshot (ts_ms) or live (None)."""
    if ts_ms is None:
        parts = []
        for e in exps:
            ch = rec.live_chain(e)
            if ch.empty:
                continue
            t = rec.dsign_table(e)
            ch["dsign"] = ch["sym"].map(dict(zip(t["sym"], t["dsign"]))) if len(t) else np.nan
            parts.append(ch)
        ch = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        spot, _ = rec.spot_now()
        return _typed(ch), spot, dt.datetime.now(ET).replace(tzinfo=None)
    h = rec.chain_df()
    ch = h[(h["ts_ms"] == ts_ms) & (h["exp"].isin(exps))]
    if "dsign" not in ch:
        ch = ch.assign(dsign=np.nan)
    spot = float(ch["spot"].dropna().iloc[0]) if len(ch) and ch["spot"].notna().any() else float("nan")
    return _typed(ch), spot, naive_et(ts_ms)


def first_snap(rec, exps, day, t: dt.time):
    """First snapshot at/after `t` on `day` (ts_ms) or None."""
    h = rec.chain_df()
    if h.empty:
        return None
    lo, hi = et_ms(day, t), et_ms(day, dt.time(16, 15))
    ts = h.loc[(h["exp"] == exps[0]) & (h["ts_ms"] >= lo) & (h["ts_ms"] < hi), "ts_ms"]
    return int(ts.min()) if len(ts) else None


def true_open(rec, day) -> float | None:
    b = bars_for(rec, day)
    return float(b["o"].iloc[0]) if len(b) else None


def method_ref(rec, spot, day, now: dt.datetime):
    """vs3dgbt method_ref: true 09:30 open, else a premarket anchor frozen once per day."""
    if (now.date() == day and now.time() >= dt.time(9, 30)) or now.date() > day:
        o = true_open(rec, day)
        if o:
            return o, "true-open"
        return spot, "spot"
    k = f"preref_{day}"
    if k not in rec.ui_state and spot == spot:
        rec.ui_state[k] = float(spot)
    return rec.ui_state.get(k, spot), "pre-frozen"


def open_straddle(rec, exps, day):
    """Opening straddle: ATM (true open, rounded to 5) call+put mid at the first ≥09:30 snapshot."""
    o = true_open(rec, day)
    ts = first_snap(rec, exps, day, dt.time(9, 30))
    if o is None or ts is None:
        return None
    ch, _, _ = frame(rec, exps[:1], ts)
    return B.mid_straddle(ch, round(o / 5.0) * 5.0)


def card_lock(rec, exps, day, strad_now):
    """09:35 lock: levels from the first snapshot ≥ 09:35, frozen for the session
    (shared by every viewer; recomputed after a reboot from the stored snapshot)."""
    key = f"lock_{day}_{'|'.join(exps)}"
    if key in rec.ui_state:
        return rec.ui_state[key]
    ts = first_snap(rec, exps, day, dt.time(9, 35))
    if ts is None:
        return None
    ch, sp, _ = frame(rec, exps, ts)
    rows = B.signed_book_rows(ch, sp, units="contracts")
    if rows is None:
        return None
    out = {}
    ref = true_open(rec, day) or sp
    B.key_levels_lines(rows, sp, B.mid_straddle(ch[ch["exp"] == exps[0]], sp) or strad_now,
                       "k", "g", "r", "c", "d", "y", ref_spot=ref, open_strad=open_straddle(rec, exps, day),
                       levels_out=out)
    if not out.get("ok"):
        return None
    lk = {"levels": out["levels"], "locked_at": naive_et(ts).strftime("%H:%M"), "ts_ms": ts}
    rec.ui_state[key] = lk
    return lk


def strip_inputs(rec, exp, day, upto_ms):
    """History for compute_strip: charm signs of the last snapshots, FUEL baseline at
    the first ≥09:30 snapshot, ATM bid-straddle tape sampled every 5 min."""
    h = rec.chain_df()
    if h.empty:
        return (), None, ()
    h = h[(h["exp"] == exp) & (h["ts_ms"] >= et_ms(day, dt.time(4, 0))) & (h["ts_ms"] <= upto_ms)]
    if h.empty:
        return (), None, ()
    key = ("strip", exp, str(day), int(h["ts_ms"].max()), len(h))
    c = rec.ui_state.get("_strip_cache")
    if c and c[0] == key:
        return c[1]
    times = sorted(h["ts_ms"].unique())
    hist = []
    for t in times[-4:-1]:
        s = _typed(h[h["ts_ms"] == t])
        sp = float(s["spot"].dropna().iloc[0]) if s["spot"].notna().any() else float("nan")
        eff, w = _eff(s), s["oi"].fillna(0)
        cm, _ = B.charm_of(s, sp, naive_et(t), eff, w)
        hist.append(1 if cm > 0 else -1 if cm < 0 else 0)
    fuel0 = None
    t0 = [t for t in times if t >= et_ms(day, dt.time(9, 30))]
    if t0:
        s = _typed(h[h["ts_ms"] == t0[0]])
        sp = float(s["spot"].dropna().iloc[0]) if s["spot"].notna().any() else float("nan")
        fuel0 = abs(B.fuel_of(s, sp, _eff(s), s["oi"].fillna(0))) or 1.0
    tape, last = [], 0
    for t in t0:
        if t - last < 5 * 60_000:
            continue
        last = t
        s = _typed(h[h["ts_ms"] == t])
        sp = float(s["spot"].dropna().iloc[0]) if s["spot"].notna().any() else float("nan")
        tape.append((naive_et(t), B.atm_bid_straddle(s, sp)))
    res = (tuple(hist), fuel0, tuple(tape))
    rec.ui_state["_strip_cache"] = (key, res)
    return res


def _eff(cc):
    nv = np.where(cc["type"].values == "call", 1.0, -1.0)
    d = cc["dsign"] if "dsign" in cc else pd.Series(np.nan, index=cc.index)
    return d.where(d.notna(), pd.Series(nv * B.GBT_UNSEEDED_W, index=cc.index))


def vix_today(rec, day):
    v = rec.vix_df()
    if v.empty:
        return None
    v = v[v["ts_ms"] >= et_ms(day, dt.time(9, 30))]
    return v["close"] if len(v) else None
