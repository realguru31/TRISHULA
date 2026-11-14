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
    from . import expiry as EX                      # v0.28.0: real expiry time (half days 13:00, AM 09:30)
    end = pd.Timestamp(EX.end(exp))
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


def surfaces_strike(legs: pd.DataFrame, c1: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp, exp: str, beta: bool,
                    lo: float, hi: float, spot_by_min: pd.Series, every_min: int = 5):
    """v0.28.0 — TASTIER surfaces BY STRIKE (the Tastier layout: bright bands at the big strikes).
    For every bucket t: dealer position per contract q(t) = pre-open sign × morning OI − contracts customers bought net
    since the open (ask − bid volume from the 1-min candles, up to t). Plotted per strike: that strike's dealer γ and
    vanna at SPX(t) — so a strike lights up where dealers hold size AND it is near enough to price to matter.
    The pre-open sign (seed_dsign) is used for the start position so today's flow is counted ONCE (v0.19.3 used the
    live sign, which already contains today's flow, and then subtracted today's flow again).
    Also returns the price-grid total γ (2-pt grid) for the 0γ flip line.
    legs: sym, strike, cp, oi, iv, seed_dsign (beta) · c1: m, sym, bidv, askv (, iv) · spot_by_min: SPX close by minute."""
    if legs is None or legs.empty or c1 is None or c1.empty or spot_by_min is None or not len(spot_by_min):
        return None
    L = legs.dropna(subset=["strike"]).drop_duplicates("sym").reset_index(drop=True)
    L["oi"] = pd.to_numeric(L["oi"], errors="coerce").fillna(0.0)
    L["iv"] = pd.to_numeric(L["iv"], errors="coerce")
    L["iv"] = L["iv"].where(L["iv"] > 0, L.groupby("cp")["iv"].transform("median")).fillna(0.2)
    idx = pd.date_range(pd.Timestamp(t0).floor(f"{every_min}min"), pd.Timestamp(t1).floor(f"{every_min}min"),
                        freq=f"{every_min}min")
    if len(idx) < 2:
        return None
    c = c1[c1["sym"].astype(str).isin(set(L["sym"])) & (c1["m"] >= t0) & (c1["m"] <= t1)].copy()
    c["sym"] = c["sym"].astype(str)
    c["b"] = c["m"].dt.floor(f"{every_min}min")
    c["net"] = c["askv"].fillna(0) - c["bidv"].fillna(0)
    net = (c.pivot_table(index="b", columns="sym", values="net", aggfunc="sum", observed=True).reindex(idx).fillna(0.0)
           .cumsum().reindex(columns=L["sym"]).fillna(0.0).values)
    if "iv" in c and c["iv"].notna().any():
        ivp = (c.pivot_table(index="b", columns="sym", values="iv", aggfunc="last", observed=True).reindex(idx).ffill()
               .reindex(columns=L["sym"]).values)
    else:
        ivp = np.full((len(idx), len(L)), np.nan)
    if beta:
        sd = pd.to_numeric(L["seed_dsign"], errors="coerce").values if "seed_dsign" in L else np.full(len(L), np.nan)
        naive = np.where(L["cp"].values == 1, 1.0, -1.0)
        sg = np.where(np.isfinite(sd), sd, naive * 0.2)
    else:
        sg = np.where(L["cp"].values == 1, 1.0, -1.0)
    base = sg * L["oi"].values
    sp = pd.Series(spot_by_min).sort_index()
    sp = sp[~sp.index.duplicated(keep="last")].reindex(idx, method="ffill").bfill().values
    Kv = L["strike"].values
    ks = np.unique(Kv[(Kv >= lo) & (Kv <= hi)])
    if not len(ks):
        return None
    col = pd.Index(ks).get_indexer(Kv)                      # leg → strike row (−1 = outside the window)
    inside = col >= 0
    P = np.arange(lo, hi + 2.0, 2.0)
    G, V, DG = (np.zeros((len(ks), len(idx))) for _ in range(3))
    GP = np.zeros((len(P), len(idx)))
    for j, t in enumerate(idx):
        S = float(sp[j])
        if not S == S:
            continue
        T = _t_years(exp, t)
        iv = np.where(np.isfinite(ivp[j]) & (ivp[j] > 0), ivp[j], L["iv"].values)
        q = base - net[j]
        g = _gamma(np.array([S]), Kv, T, iv) * 100 * S * S * 0.01            # $ γ per 1 % move, per contract
        va = _vanna(np.array([S]), Kv, T, iv) * 0.01 * 100 * S                # $ Δ per +1 vol, per contract
        G[:, j] = np.bincount(col[inside], weights=(g * q)[inside], minlength=len(ks))
        V[:, j] = np.bincount(col[inside], weights=(va * q)[inside], minlength=len(ks))
        DG[:, j] = np.bincount(col[inside], weights=(g * -net[j])[inside], minlength=len(ks))
        gp = _gamma(P[:, None], Kv[None, :], T, iv[None, :]) * 100 * (P ** 2)[:, None] * 0.01
        GP[:, j] = (gp * q[None, :]).sum(axis=1)
    return dict(t=list(idx), P=ks.astype(float), gamma=G, vanna=V, dgamma=DG, Pgrid=P, gamma_grid=GP,
                spot=sp, source="tape", axis="strike")


def surfaces_tape(legs: pd.DataFrame, c1: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp, exp: str, beta: bool,
                  lo: float, hi: float, step: float = 2.0, every_min: int = 5):
    """v0.19.3 L45: price × time surfaces from data that SURVIVES A REBOOT (1-minute option candles), causal.
    For every bucket t: dealer position q(t) = sign × morning OI − (contracts bought − sold by customers since the
    open, up to t) — a customer buying at the ask leaves the dealer short. γ and vanna of q(t) at every price level P,
    with each contract's IV as recorded in that minute's candle (fallback: chain IV). Also "Δ today" = the part of γ
    that comes from today's flow alone (gamma ADDED > 0 / REMOVED < 0 for dealers).
    legs: sym, strike, cp, oi, iv (+ dsign) · c1: m, sym, bidv, askv (, iv)."""
    if legs is None or legs.empty or c1 is None or c1.empty:
        return None
    L = legs.dropna(subset=["strike"]).drop_duplicates("sym").reset_index(drop=True)
    L["oi"] = pd.to_numeric(L["oi"], errors="coerce").fillna(0.0)
    L["iv"] = pd.to_numeric(L["iv"], errors="coerce")
    L["iv"] = L["iv"].where(L["iv"] > 0, L.groupby("cp")["iv"].transform("median")).fillna(0.2)
    idx = pd.date_range(pd.Timestamp(t0).floor(f"{every_min}min"), pd.Timestamp(t1).floor(f"{every_min}min"),
                        freq=f"{every_min}min")
    if len(idx) < 2:
        return None
    c = c1[c1["sym"].astype(str).isin(set(L["sym"])) & (c1["m"] >= t0) & (c1["m"] <= t1)].copy()
    c["sym"] = c["sym"].astype(str)
    c["b"] = c["m"].dt.floor(f"{every_min}min")
    c["net"] = c["askv"].fillna(0) - c["bidv"].fillna(0)
    net = c.pivot_table(index="b", columns="sym", values="net", aggfunc="sum", observed=True).reindex(idx).fillna(0.0).cumsum()
    net = net.reindex(columns=L["sym"]).fillna(0.0).values                      # buckets × legs, customer net bought
    if "iv" in c and c["iv"].notna().any():
        ivp = (c.pivot_table(index="b", columns="sym", values="iv", aggfunc="last", observed=True).reindex(idx).ffill()
               .reindex(columns=L["sym"]).values)
    else:
        ivp = np.full((len(idx), len(L)), np.nan)
    base = signs(L, beta) * L["oi"].values
    P = np.arange(lo, hi + step, step)
    K = L["strike"].values[None, :]
    G, V, DG = [], [], []
    for j, t in enumerate(idx):
        T = _t_years(exp, t)
        iv = np.where(np.isfinite(ivp[j]) & (ivp[j] > 0), ivp[j], L["iv"].values)[None, :]
        PP = P[:, None]
        g = _gamma(PP, K, T, iv) * 100 * (P ** 2)[:, None] * 0.01
        va = _vanna(PP, K, T, iv) * 0.01 * 100 * P[:, None]
        q = base - net[j]
        G.append((g * q[None, :]).sum(axis=1)); V.append((va * q[None, :]).sum(axis=1))
        DG.append((g * (-net[j])[None, :]).sum(axis=1))
    return dict(t=list(idx), P=P, gamma=np.array(G).T, vanna=np.array(V).T, dgamma=np.array(DG).T, source="tape")
