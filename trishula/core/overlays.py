"""TASTIER overlays — Velocity · Absorb · Pressure · VRVP (definitions written for TRISHULA;
the reference screenshots named the overlays without formulas).

All built from the classified tape (per print: dn = aggr · size · Δ · 100 · S, the SPXFlow
delta-notional) and 1-minute SPX candles, per RTH minute:
  VELOCITY  = EMA₃ of signed delta-notional per minute, in $M/min. Spikes (|z₃₀| ≥ 2 on the
              raw minute) are flagged — how fast aggressive money is moving, and which way.
  ABSORB    = a minute where flow is extreme (|z₃₀| ≥ 2) but price barely moves
              (|close − open| ≤ 0.25 × ATR₁₄ of 1-min true range). Buyers absorbed
              (dn > 0, price not up) = ▼ red above the high; sellers absorbed (dn < 0,
              price not down) = ▲ green below the low. Passive size is soaking up the push.
  PRESSURE  = rolling 15-min Σ delta-notional ÷ its own session σ, clipped ±3 — a slow
              oscillator of sustained one-way flow, drawn as background tint
              (green = buy pressure, red = sell pressure).
  VRVP      = visible-range volume profile from SPY 1-minute volume (SPX index has no
              volume): each minute's SPY volume spread evenly over its high–low, mapped
              to SPX points by that minute's SPX/SPY ratio, 2-pt bins. POC + 70 % value
              area (VAH/VAL) marked.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .timeutil import ET


def _t(ms):
    return pd.to_datetime(ms, unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)


def minute_flow(prints: pd.DataFrame, candles: pd.DataFrame, day, spot_now: float) -> pd.DataFrame:
    """Per RTH minute: OHLC + signed delta-notional dn ($)."""
    if candles is None or candles.empty:
        return pd.DataFrame()
    c = candles.copy()
    c["t"] = _t(c["ts_ms"])
    c = c[(c["t"].dt.date == day) & (c["t"].dt.time >= pd.Timestamp("09:30").time()) &
          (c["t"].dt.time < pd.Timestamp("16:00").time())].set_index("t").sort_index()
    if c.empty:
        return pd.DataFrame()
    c["dn"] = 0.0
    if prints is not None and len(prints):
        p = prints.copy()
        s = p["spot"].fillna(spot_now) if "spot" in p else spot_now
        p["dn"] = p["aggr"] * p["size"] * p["delta"].fillna(0) * 100.0 * s
        p["m"] = _t(p["ts_ms"]).dt.floor("1min")
        g = p.groupby("m")["dn"].sum()
        c["dn"] = g.reindex(c.index, fill_value=0.0).values
    return c[["open", "high", "low", "close", "dn"]]


def velocity(m: pd.DataFrame) -> pd.DataFrame:
    if m.empty:
        return m
    out = pd.DataFrame(index=m.index)
    out["vel"] = (m["dn"] / 1e6).ewm(span=3, adjust=False).mean()
    mu = m["dn"].rolling(30, min_periods=10).mean(); sd = m["dn"].rolling(30, min_periods=10).std()
    out["z"] = (m["dn"] - mu) / sd.replace(0, np.nan)
    out["spike"] = out["z"].abs() >= 2
    return out


def absorption(m: pd.DataFrame, z: pd.Series) -> pd.DataFrame:
    if m.empty:
        return pd.DataFrame(columns=["t", "y", "side"])
    tr = pd.concat([m["high"] - m["low"], (m["high"] - m["close"].shift()).abs(), (m["low"] - m["close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean()
    body = (m["close"] - m["open"])
    flat = body.abs() <= 0.25 * atr
    rows = []
    for t in m.index[(z.abs() >= 2) & flat.fillna(False)]:
        if m.at[t, "dn"] > 0 and body[t] <= 0.25 * atr[t]:
            rows.append((t, m.at[t, "high"] + 0.6, "buyers absorbed"))
        elif m.at[t, "dn"] < 0 and body[t] >= -0.25 * atr[t]:
            rows.append((t, m.at[t, "low"] - 0.6, "sellers absorbed"))
    return pd.DataFrame(rows, columns=["t", "y", "side"])


def pressure(m: pd.DataFrame) -> pd.Series:
    if m.empty:
        return pd.Series(dtype=float)
    r = m["dn"].rolling(15, min_periods=3).sum()
    sd = r.std()
    return (r / sd).clip(-3, 3) if sd and sd == sd else r * 0


def vrvp(spy: pd.DataFrame, candles: pd.DataFrame, day, bin_pts: float = 2.0):
    """SPY volume profile in SPX points. Returns (bins, vol, poc, vah, val) or None."""
    if spy is None or spy.empty or candles is None or candles.empty:
        return None
    s = spy.copy(); s["t"] = _t(s["ts_ms"])
    s = s[(s["t"].dt.date == day) & (s["t"].dt.time >= pd.Timestamp("09:30").time()) &
          (s["t"].dt.time < pd.Timestamp("16:00").time())].set_index("t")
    c = candles.copy(); c["t"] = _t(c["ts_ms"]); c = c.set_index("t")["close"]
    if s.empty or c.empty:
        return None
    ratio = (c.reindex(s.index, method="ffill") / s["close"]).ffill().bfill()
    lo = (s["low"] * ratio).values; hi = (s["high"] * ratio).values; vol = s["volume"].fillna(0).values
    if not np.isfinite(lo).any() or vol.sum() <= 0:
        return None
    edges = np.arange(np.floor(np.nanmin(lo) / bin_pts) * bin_pts, np.ceil(np.nanmax(hi) / bin_pts) * bin_pts + bin_pts, bin_pts)
    acc = np.zeros(len(edges) - 1)
    for a, b, v in zip(lo, hi, vol):
        if not (np.isfinite(a) and np.isfinite(b)) or v <= 0:
            continue
        i0 = max(0, int((a - edges[0]) // bin_pts)); i1 = min(len(acc) - 1, int((b - edges[0]) // bin_pts))
        acc[i0:i1 + 1] += v / (i1 - i0 + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    ip = int(np.argmax(acc)); poc = float(mids[ip])
    tot = acc.sum(); inc = acc[ip]; lo_i = hi_i = ip
    while inc < 0.70 * tot and (lo_i > 0 or hi_i < len(acc) - 1):
        up = acc[hi_i + 1] if hi_i < len(acc) - 1 else -1
        dn = acc[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1; inc += up
        else:
            lo_i -= 1; inc += dn
    return mids, acc, poc, float(mids[hi_i]), float(mids[lo_i])
