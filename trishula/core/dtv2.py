"""DT v2 (v0.17.0) — the DT settings that held up out of sample on 11 sessions (6–20 Oct 2026, research/l24).

Squares (repositioning tape), per strike, participant net = calls + / puts −, bought + / sold − (contracts):
  · ADAPTIVE BAND = max(floor, ALPHA × that strike's own last-30-min volume)  — the classic "5 % of dot" band was
    inert (overnight dots are small, the 200 floor always won) and busy ATM strikes sprayed ~150 squares/h;
    adaptive → ~12/h and 2–3× more settings robust in both test weeks
  · watch the WATCH strikes nearest spot within ±PROX % · counted from 09:30 · per-strike COOLDOWN minutes
Signals (each with a 10-min cooldown between signals of the same type):
  · FOLLOW ▲/▼   ≥ NEED net strikes printing the same colour within 3 min  (+1.8 / +2.7 pts per signal over 20 min,
                 week 6–13 / 14–20 Oct, 9 of 11 days positive)
  · GEX gate     the arrow is "in play" only when naive dealer GEX (morning OI, re-evaluated at the minute's spot)
                 is POSITIVE — in −GEX, following DT lost 2–5 pts per signal; the textbook switch (fade in +GEX) failed
  · INITIATION ● 10-min net flow ≥ 5 % of volume near spot (±50) AND price moved ≥ 4 pts the same way → follow
                 (+1.1 / +2.6, every test day of week 2 positive)
Scorecard: every signal with the SPX move 10 / 20 / 30 min later (signed in the signal's direction).
Not advice: small edges (1–3 pts / 20 min before costs, 55–60 % right), 11 days — the scorecard is how to verify live.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from scipy.stats import norm

ALPHA, FLOOR, PROX, WATCH, COOLDOWN, NEED, WIN = 0.25, 200.0, 0.30, 15, 10, 2, 3
INIT_SHARE, INIT_PTS, INIT_NEAR = 0.05, 4.0, 50.0
SIG_COOL = 10


def minute_frames(mt: pd.DataFrame, minutes: pd.DatetimeIndex):
    """mt (m, sym, strike, cp, size, net) → participant net per strike, volume per strike (minute × strike)."""
    if mt is None or mt.empty:
        return pd.DataFrame(index=minutes), pd.DataFrame(index=minutes)
    m = mt.assign(nf=np.where(mt["cp"] == 1, 1.0, -1.0) * mt["net"])
    nf = m.pivot_table(index="m", columns="strike", values="nf", aggfunc="sum").reindex(minutes).fillna(0.0)
    vol = m.pivot_table(index="m", columns="strike", values="size", aggfunc="sum").reindex(minutes).reindex(columns=nf.columns).fillna(0.0)
    return nf, vol


def squares(nf, vol, spot: pd.Series, dot: pd.Series | None = None, alpha=ALPHA, floor=FLOOR, prox=PROX, watch=WATCH,
            cooldown=COOLDOWN):
    """Adaptive-band DT squares → DataFrame t, k, s (+1 blue / −1 magenta), filled (bool)."""
    if nf is None or nf.empty or spot is None or not len(spot):
        return pd.DataFrame(columns=["t", "k", "s", "filled"])
    K = nf.columns.values.astype(float)
    cum = nf.cumsum().values
    rv = vol.rolling(30, min_periods=5).sum().fillna(0.0).values
    S = spot.reindex(nf.index).ffill().values
    dd = dot.reindex(K).fillna(0.0).values if dot is not None else np.zeros(len(K))
    seen = np.zeros(len(K)); last = np.full(len(K), -10_000); out = []
    for i, t in enumerate(nf.index):
        if not S[i] == S[i]:
            continue
        d = np.abs(K - S[i]); w = np.where(d <= S[i] * prox / 100.0)[0]; w = w[np.argsort(d[w])][:int(watch)]
        if not len(w):
            continue
        band = np.maximum(alpha * rv[i, w], floor)
        mv = cum[i, w]; n = np.floor(np.abs(mv) / band)
        new = np.maximum(n - seen[w], 0); seen[w] = np.maximum(seen[w], n)
        for j, nn, m_ in zip(w, new, mv):
            if nn > 0 and i - last[j] >= cooldown:
                last[j] = i
                filled = abs(dd[j]) < floor or np.sign(dd[j]) == np.sign(m_)
                out.append((t, K[j], 1 if m_ > 0 else -1, bool(filled)))
    return pd.DataFrame(out, columns=["t", "k", "s", "filled"])


WARMUP = 10                     # no signals in the first 10 minutes after 09:30 (as tested)


def _cool(sig: pd.Series, cool=SIG_COOL, warmup=WARMUP) -> pd.Series:
    """keep the first non-zero signal, then nothing for `cool` minutes; nothing before 09:30 + warm-up."""
    out = pd.Series(0, index=sig.index); last = -10_000
    for i, (t, v) in enumerate(sig.items()):
        if v and pd.Timestamp(t).time() < (dt.datetime.combine(dt.date.today(), dt.time(9, 30)) + dt.timedelta(minutes=warmup)).time():
            continue
        if v and i - last >= cool:
            out.iat[i] = int(np.sign(v)); last = i
    return out


def follow(sq: pd.DataFrame, minutes: pd.DatetimeIndex, need=NEED, win=WIN) -> pd.Series:
    """+1 / −1 at minutes where ≥ need net distinct strikes printed the same colour within `win` minutes."""
    if sq is None or sq.empty:
        return pd.Series(0, index=minutes)
    net = np.zeros(len(minutes))
    tt = sq["t"].values
    for i, t in enumerate(minutes):
        h = sq[(tt > np.datetime64(t - pd.Timedelta(minutes=win))) & (tt <= np.datetime64(t))]
        net[i] = h[h["s"] > 0]["k"].nunique() - h[h["s"] < 0]["k"].nunique()
    raw = pd.Series(np.where(net >= need, 1, np.where(net <= -need, -1, 0)), index=minutes)
    return _cool(raw)


def initiation(nf, vol, spot: pd.Series, share=INIT_SHARE, pts=INIT_PTS, near=INIT_NEAR) -> pd.Series:
    if nf is None or nf.empty:
        return pd.Series(0, index=spot.index if spot is not None else [])
    K = nf.columns.values.astype(float)
    S = spot.reindex(nf.index).ffill()
    N = np.abs(K[None, :] - S.values[:, None]) <= near
    net = pd.Series((nf.values * N).sum(1), index=nf.index)
    tot = pd.Series((vol.values * N).sum(1), index=nf.index)
    sh = net.rolling(10, min_periods=1).sum() / (tot.rolling(10, min_periods=1).sum() + 1.0)
    dp = S.diff(10)
    raw = pd.Series(np.where((sh >= share) & (dp >= pts), 1, np.where((sh <= -share) & (dp <= -pts), -1, 0)), index=nf.index)
    return _cool(raw)


def gex_path(legs: pd.DataFrame, spot: pd.Series, expiry_close: dt.datetime, iv: float) -> pd.Series:
    """Naive dealer GEX ($ per 1 %) from morning OI (calls +, puts −), re-evaluated at each minute's spot."""
    if legs is None or legs.empty or spot is None or not len(spot):
        return pd.Series(dtype=float)
    K = legs["strike"].values.astype(float); sg = np.where(legs["cp"].values == 1, 1.0, -1.0)
    oi = pd.to_numeric(legs["oi"], errors="coerce").fillna(0.0).values
    out = []
    for t, s in spot.items():
        if not s == s:
            out.append(np.nan); continue
        T = max((pd.Timestamp(expiry_close) - pd.Timestamp(t)).total_seconds() / (365 * 86400), 300 / (365 * 86400))
        d1 = (np.log(s / K) + 0.5 * iv * iv * T) / (iv * np.sqrt(T))
        g = norm.pdf(d1) / (s * iv * np.sqrt(T))
        out.append(float((sg * oi * g).sum() * 100 * s * s * 0.01))
    return pd.Series(out, index=spot.index)


def scorecard(sigs: dict, spot: pd.Series, gex: pd.Series | None = None) -> pd.DataFrame:
    """sigs: name → ±1 series. One row per signal: t, type, dir, px, gex>0, fw10/20/30 (signed, pts; NaN if not matured)."""
    rows = []
    s = spot.dropna()
    for name, ser in sigs.items():
        for t, d in ser[ser != 0].items():
            if t not in s.index:
                continue
            px = float(s.loc[t]); r = {}
            for h in (10, 20, 30):
                t2 = t + pd.Timedelta(minutes=h)
                r[h] = (float(s.loc[t2]) - px) * d if t2 in s.index else np.nan
            g = float(gex.get(t, np.nan)) if gex is not None and len(gex) else np.nan
            rows.append(dict(t=t, type=name, dir="▲ up" if d > 0 else "▼ down", px=px, gex_pos=bool(g > 0) if g == g else None,
                             fw10=r[10], fw20=r[20], fw30=r[30]))
    return pd.DataFrame(rows, columns=["t", "type", "dir", "px", "gex_pos", "fw10", "fw20", "fw30"])


def summarize(card: pd.DataFrame) -> pd.DataFrame:
    if card is None or card.empty:
        return pd.DataFrame(columns=["signal", "fired", "matured (20 min)", "right at 20 min", "avg pts 10", "avg pts 20", "avg pts 30"])
    rows = []
    groups = [(n, g) for n, g in card.groupby("type")]
    fol = card[card["type"] == "follow"]
    if len(fol):
        groups.append(("follow · GEX > 0 only", fol[fol["gex_pos"] == True]))   # noqa: E712
    for n, g in groups:
        m = g.dropna(subset=["fw20"])
        rows.append({"signal": n, "fired": len(g), "matured (20 min)": len(m),
                     "right at 20 min": f"{(m['fw20'] > 0).mean():.0%}" if len(m) else "—",
                     "avg pts 10": round(g["fw10"].mean(), 2) if g["fw10"].notna().any() else None,
                     "avg pts 20": round(m["fw20"].mean(), 2) if len(m) else None,
                     "avg pts 30": round(g["fw30"].mean(), 2) if g["fw30"].notna().any() else None})
    return pd.DataFrame(rows)
