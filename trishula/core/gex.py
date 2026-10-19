"""Shared GEX / charm maths for TASTIER and VS3D (one source of truth)."""
from __future__ import annotations

import math
from datetime import datetime, time

import numpy as np
import pandas as pd

from .timeutil import ET


def years_to_expiry(exp: str, at_ms: int) -> float:
    """Year fraction from at_ms to 16:00 ET on exp, floored at 1 hour."""
    end = datetime.combine(datetime.fromisoformat(exp).date(), time(16, 0), tzinfo=ET)
    t = (end.timestamp() * 1000 - at_ms) / (365 * 24 * 3600 * 1000)
    return max(t, 1 / (365 * 24))


def bs_charm(S, K, T, iv, cp):
    """Delta decay per day (BS, r=q=0)."""
    if not (S > 0 and K > 0 and T > 0 and iv > 0):
        return 0.0
    st = iv * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / st
    d2 = d1 - st
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    return -pdf * (-d2 / (2 * T)) / 365.0          # same for calls and puts when q=0


def add_exposures(ch: pd.DataFrame, spot: float | None = None) -> pd.DataFrame:
    """Per-leg dealer-convention GEX (USD per 1% move) and charm (delta/day x S)."""
    c = ch.copy()
    s = c["spot"] if spot is None else spot
    c["oi"] = c["oi"].fillna(0)
    c["gex"] = c["cp"] * c["gamma"].fillna(0) * c["oi"] * 100 * s * s * 0.01
    if "exp" in c and len(c):
        c["charm"] = [
            cp * bs_charm(sp, k, years_to_expiry(ex, ts), iv, cp) * oi * 100 * sp
            if iv == iv else 0.0
            for cp, sp, k, ex, ts, iv, oi in zip(
                c["cp"], (c["spot"] if spot is None else [spot] * len(c)), c["strike"],
                c["exp"], c["ts_ms"], c["iv"], c["oi"])]
    return c


def by_strike(ch: pd.DataFrame, spot: float) -> pd.DataFrame:
    c = add_exposures(ch, spot)
    g = c.pivot_table(index="strike", columns="cp", values="gex", aggfunc="sum").fillna(0)
    g = g.rename(columns={1: "call", -1: "put"})
    for col in ("call", "put"):
        if col not in g:
            g[col] = 0.0
    g["net"] = g["call"] + g["put"]
    return g.sort_index().reset_index()


def gamma_flip(g: pd.DataFrame, spot: float):
    if g.empty:
        return None
    k, cum = g["strike"].values, np.cumsum(g["net"].values)
    xs = [k[i] + (k[i + 1] - k[i]) * (-cum[i]) / (cum[i + 1] - cum[i])
          for i in range(len(k) - 1) if cum[i] * cum[i + 1] < 0]
    return min(xs, key=lambda x: abs(x - spot)) if xs else None


def walls(g: pd.DataFrame, spot: float):
    up, dn = g[g["strike"] > spot], g[g["strike"] < spot]
    cw = float(up.loc[up["call"].idxmax(), "strike"]) if len(up) and up["call"].max() > 0 else None
    pw = float(dn.loc[dn["put"].idxmin(), "strike"]) if len(dn) and dn["put"].min() < 0 else None
    return cw, pw


def window(df: pd.DataFrame, spot: float, mode: str, n: int, pct: float, col="strike"):
    """Strike window from the shared control: ±N strikes or ±pct % of spot."""
    if df.empty or not spot == spot:
        return df
    if mode == "% move":
        lo, hi = spot * (1 - pct / 100), spot * (1 + pct / 100)
        return df[(df[col] >= lo) & (df[col] <= hi)]
    ks = np.sort(df[col].unique())
    i = int(np.abs(ks - spot).argmin())
    keep = ks[max(0, i - n): i + n + 1]
    return df[df[col].isin(keep)]
