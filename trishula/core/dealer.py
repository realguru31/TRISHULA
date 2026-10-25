"""Dealer exposures for the TASTIER page (L19, 1:1 with the Tastier GEX page) — naive vs β (flow-signed).

Dealer position per contract  q = s · OI
  naive : s = +1 calls (dealers long calls), −1 puts (dealers short puts) — the classic GEX convention
  β     : s = dsign from the classified tape (seed + live: −net customer bought / total, −1 … +1);
          contracts with no tape yet fall back to naive × 0.2 (same rule as the Book / Terrain)

Per contract (Black-Scholes, r = q = 0, iv from the chain):
  GEX $ per 1 %   = q · Γ · 100 · S² · 0.01
  dealer Δ $      = q · Δ · 100 · S                     (dealers' option delta in $; their hedge is the opposite)
  vanna $ / +1vol = q · ∂Δ/∂σ · 0.01 · 100 · S
  hedge → close   = −Σ q · (Δ(T→close) − Δ(now)) · 100 · S   (charm: what dealers must trade into 16:00, spot fixed)
  IV −1 pt        = −Σ q · (Δ(σ−1pt) − Δ(σ)) · 100 · S         (vanna: what dealers trade if implied vol drops 1 pt)
Positive hedge numbers = dealers BUY, negative = SELL.
Zero gamma = the price where total dealer GEX, re-evaluated at that price, crosses zero (price grid ±3 %).
Regime score = call GEX ÷ (call GEX + |put GEX|) × 100 (the "Positive GEX 53" chip).
Net bias = Σ OI · Δ · 100 · S over calls and puts (open interest counted long: + = calls dominate in delta).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

YEAR = 365 * 24 * 3600.0


def _t_years(exp: str, now: pd.Timestamp) -> float:
    end = pd.Timestamp(f"{exp} 16:00")
    return max((end - now).total_seconds() / YEAR, 60 / YEAR)


def signs(ch: pd.DataFrame, beta: bool) -> np.ndarray:
    naive = np.where(ch["cp"].values == 1, 1.0, -1.0)
    if not beta or "dsign" not in ch:
        return naive
    ds = pd.to_numeric(ch["dsign"], errors="coerce").values
    return np.where(np.isfinite(ds), ds, naive * 0.2)


def _d1(S, K, T, iv):
    iv = np.where(iv > 0, iv, 0.2)
    return (np.log(S / K) + 0.5 * iv * iv * T) / (iv * np.sqrt(T)), iv


def _delta(S, K, T, iv, cp):
    d1, _ = _d1(S, K, T, iv)
    return np.where(cp == 1, norm.cdf(d1), norm.cdf(d1) - 1.0)


def _gamma(S, K, T, iv):
    d1, iv = _d1(S, K, T, iv)
    return norm.pdf(d1) / (S * iv * np.sqrt(T))


def _vanna(S, K, T, iv):
    d1, iv = _d1(S, K, T, iv)
    d2 = d1 - iv * np.sqrt(T)
    return -norm.pdf(d1) * d2 / iv


def prep(ch: pd.DataFrame) -> pd.DataFrame:
    c = ch.dropna(subset=["strike"]).copy()
    c["oi"] = pd.to_numeric(c["oi"], errors="coerce").fillna(0.0)
    c["iv"] = pd.to_numeric(c["iv"], errors="coerce")
    c["iv"] = c["iv"].where(c["iv"] > 0, c.groupby("cp")["iv"].transform("median")).fillna(0.2)
    return c[c["oi"] > 0]


def exposures(ch: pd.DataFrame, spot: float, exp: str, now: pd.Timestamp, beta: bool) -> pd.DataFrame:
    """Per-contract exposures at the current spot."""
    c = prep(ch)
    if c.empty or not spot == spot:
        return pd.DataFrame()
    T = _t_years(exp, now)
    K, iv, cp = c["strike"].values, c["iv"].values, c["cp"].values
    q = signs(c, beta) * c["oi"].values
    S = float(spot)
    d_now = _delta(S, K, T, iv, cp)
    c["q"] = q
    c["gex"] = q * _gamma(S, K, T, iv) * 100 * S * S * 0.01
    c["dex"] = q * d_now * 100 * S
    c["vanna"] = q * _vanna(S, K, T, iv) * 0.01 * 100 * S
    c["to_close"] = -q * (_delta(S, K, 5 * 60 / YEAR, iv, cp) - d_now) * 100 * S
    c["iv_dn"] = -q * (_delta(S, K, T, np.maximum(iv - 0.01, 0.01), cp) - d_now) * 100 * S
    c["oi_dex"] = c["oi"].values * d_now * 100 * S        # open interest counted long (Net bias)
    return c


def gex_at(c: pd.DataFrame, P: np.ndarray, T: float, beta: bool) -> np.ndarray:
    """Total dealer GEX re-evaluated at each hypothetical price P (price grid)."""
    if c.empty:
        return np.zeros(len(P))
    q = signs(c, beta) * c["oi"].values
    PP = np.asarray(P, float)[:, None]
    g = _gamma(PP, c["strike"].values[None, :], T, c["iv"].values[None, :])
    return (g * q[None, :]).sum(axis=1) * 100 * PP[:, 0] ** 2 * 0.01


def zero_gamma(ch: pd.DataFrame, spot: float, exp: str, now: pd.Timestamp, beta: bool, span=0.03):
    c = prep(ch)
    if c.empty or not spot == spot:
        return None
    P = np.arange(spot * (1 - span), spot * (1 + span), 1.0)
    v = gex_at(c, P, _t_years(exp, now), beta)
    sgn = np.sign(v)
    idx = np.where(np.diff(sgn) != 0)[0]
    if not len(idx):
        return None
    xs = [P[i] - v[i] * (P[i + 1] - P[i]) / (v[i + 1] - v[i]) for i in idx]
    return float(min(xs, key=lambda x: abs(x - spot)))


def summary(c: pd.DataFrame) -> dict:
    if c is None or c.empty:
        return {}
    calls, puts = c[c["cp"] == 1], c[c["cp"] == -1]
    cg, pg = float(calls["gex"].sum()), float(puts["gex"].sum())
    bs = c.groupby(["strike", "cp"])["gex"].sum().unstack(fill_value=0.0)
    cw = float(bs[1].idxmax()) if 1 in bs and len(bs) else None
    pw = float(bs[-1].idxmin()) if -1 in bs and len(bs) else None
    return dict(net=cg + pg, call=cg, put=pg, call_wall=cw, put_wall=pw,
                score=100 * cg / (abs(cg) + abs(pg)) if (abs(cg) + abs(pg)) > 0 else 50.0,
                dex=float(c["dex"].sum()), vanna=float(c["vanna"].sum()),
                to_close=float(c["to_close"].sum()), iv_dn=float(c["iv_dn"].sum()),
                bias=float(c["oi_dex"].sum()))


def by_strike(c: pd.DataFrame) -> pd.DataFrame:
    if c is None or c.empty:
        return pd.DataFrame(columns=["strike", "gex", "dex", "vanna"])
    return c.groupby("strike")[["gex", "dex", "vanna"]].sum().reset_index()


def history(hist: pd.DataFrame, exp: str, beta: bool, every_min: int = 5) -> pd.DataFrame:
    """Dealer Δ $ and hedge-into-close $ per chain snapshot (sampled every `every_min`)."""
    if hist is None or hist.empty:
        return pd.DataFrame(columns=["t", "dex", "to_close", "iv_dn"])
    h = hist.copy()
    h["tb"] = (h["ts_ms"] // (every_min * 60_000)) * every_min * 60_000
    keep = h.groupby("tb")["ts_ms"].transform("max") == h["ts_ms"]
    rows = []
    for ts, g in h[keep].groupby("ts_ms"):
        sp = float(g["spot"].dropna().iloc[0]) if g["spot"].notna().any() else np.nan
        if not sp == sp:
            continue
        now = pd.Timestamp(ts, unit="ms", tz="UTC").tz_convert("America/New_York").tz_localize(None)
        c = exposures(g, sp, exp, now, beta)
        if c.empty:
            continue
        rows.append((now, float(c["dex"].sum()), float(c["to_close"].sum()), float(c["iv_dn"].sum())))
    return pd.DataFrame(rows, columns=["t", "dex", "to_close", "iv_dn"])


def surfaces(hist: pd.DataFrame, exp: str, beta: bool, lo: float, hi: float, step: float = 2.0, every_min: int = 5):
    """Price × time surfaces from chain snapshots: dealer γ ($ per 1 %) and dealer vanna Δ per +1 vol,
    each re-evaluated at every price level P on the grid (what dealers would hold if SPX were at P)."""
    if hist is None or hist.empty:
        return None
    P = np.arange(lo, hi + step, step)
    h = hist.copy()
    h["tb"] = (h["ts_ms"] // (every_min * 60_000)) * every_min * 60_000
    keep = h.groupby("tb")["ts_ms"].transform("max") == h["ts_ms"]
    ts_l, G, V = [], [], []
    for ts, g in h[keep].groupby("ts_ms"):
        c = prep(g)
        if c.empty:
            continue
        now = pd.Timestamp(ts, unit="ms", tz="UTC").tz_convert("America/New_York").tz_localize(None)
        T = _t_years(exp, now)
        q = signs(c, beta) * c["oi"].values
        PP = P[:, None]
        K, iv = c["strike"].values[None, :], c["iv"].values[None, :]
        G.append((_gamma(PP, K, T, iv) * q[None, :]).sum(axis=1) * 100 * P ** 2 * 0.01)
        V.append((_vanna(PP, K, T, iv) * q[None, :]).sum(axis=1) * 0.01 * 100 * P)
        ts_l.append(now)
    if not ts_l:
        return None
    return dict(t=ts_l, P=P, gamma=np.array(G).T, vanna=np.array(V).T)
