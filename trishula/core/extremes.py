"""v0.42.0 Fade or follow at the day's extremes (from the "zero" write-up: in chop, money leaning AGAINST a new high/low
wins → fade; in trend, money pushing THROUGH it wins → follow; when neither has been working → sit out).

Event   SPX makes a new session high or low (from 10:00 ET; same side at most once per COOL min).
Money   single-leg 0DTE options lean over the last WIN minutes, (bull − bear) / (bull + bear):
          X = K × the standard deviation of the lean so far today (adaptive: the 15-min lean is usually within
          ±0.04, so a fixed cut is too blunt)
          against = new high with lean < −X, or new low with lean > +X  → the trade is FADE
          through = new high with lean > +X, or new low with lean < −X  → the trade is FOLLOW
          (|lean| ≤ X → no event)
Result  SPX points FWD minutes later in the trade's direction (known only once FWD minutes have passed).
Score   the last NHIST finished events of each kind (earlier days + today so far): % right, average points.
        Verdict = the kind with average > 0 and ≥ 55 % right (the better one if both); neither → SIT OUT.
Nothing here is fitted: all settings fixed below, written before any scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd

WIN, K, FWD, COOL, NHIST = 15, 0.5, 30, 15, 15
START = pd.Timedelta("10h")


def events(d: dict) -> pd.DataFrame:
    """One day (lean-history dict: rows + spx) → events with kind, side, time, price, lean, result."""
    from . import lean as LN
    b = LN.bars(d, "0DTE", "single-leg", 1)
    cols = ["t", "side", "kind", "px", "lean", "dir", "pts", "sess_ok"]
    if len(b) < 40:
        return pd.DataFrame(columns=cols)
    net, tot = (b.b - b.r).rolling(WIN, min_periods=5).sum(), (b.b + b.r).rolling(WIN, min_periods=5).sum()
    lean = (net / tot.where(tot > 0)).fillna(0.0)
    ses = ((b.b - b.r).cumsum() / (b.b + b.r).cumsum().where(lambda x: x > 0)).fillna(0.0).values   # session lean
    sdv = lean.expanding(min_periods=10).std().fillna(lean.abs().max() or 1.0).clip(lower=0.005).values
    lean = lean.values
    h, l, c, t = b.h.values, b.l.values, b.c.values, b.index
    day = t[0].normalize()
    hi, lo = h[0], l[0]
    last = {"high": None, "low": None}
    out = []
    for i in range(1, len(b)):
        for side, new in (("high", h[i] > hi), ("low", l[i] < lo)):
            if not new or t[i] < day + START:
                continue
            if last[side] is not None and (t[i] - last[side]) < pd.Timedelta(minutes=COOL):
                continue
            lv = lean[i]
            X = K * sdv[i]
            sgn = 1 if side == "high" else -1                 # +1 = breakout up
            if lv * sgn < -X:
                kind, dr = "fade", -sgn                       # money leaning against the extreme
            elif lv * sgn > X:
                kind, dr = "follow", sgn                      # money pushing through it
            else:
                continue
            last[side] = t[i]
            j = i + FWD
            pts = (c[j] - c[i]) * dr if j < len(b) else np.nan
            out.append((t[i], side, kind, float(h[i] if side == "high" else l[i]), float(lv), dr, pts,
                        bool(np.sign(ses[i]) == dr)))
        hi, lo = max(hi, h[i]), min(lo, l[i])
    return pd.DataFrame(out, columns=cols)


_hist: dict = {}


def history(today: str, max_days: int = 20) -> pd.DataFrame:
    """Events of the saved days before `today` (cached per day)."""
    from . import lean as LN
    days = [x for x in LN.saved_days() if x < today][:max_days]
    out = []
    for x in days:
        if x not in _hist:
            d = LN.load_day(x)
            _hist[x] = events(d) if d else pd.DataFrame()
        e = _hist[x]
        if len(e):
            out.append(e.assign(day=x))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def score(ev: pd.DataFrame, sess: bool = False) -> dict:
    """Last NHIST finished events of each kind → {kind: (n, right, avg)} + verdict. sess = only events where the
    session's money (since 09:30) points the same way as the trade (zero's "SES" driver; 10 days: follow 61 % / +4.4)."""
    if sess and len(ev) and "sess_ok" in ev:
        ev = ev[ev["sess_ok"].fillna(False).astype(bool)]
    res = {}
    for k in ("fade", "follow"):
        e = ev[(ev["kind"] == k) & ev["pts"].notna()].sort_values("t").tail(NHIST) if len(ev) else pd.DataFrame()
        res[k] = (len(e), float((e["pts"] > 0).mean()) if len(e) else np.nan, float(e["pts"].mean()) if len(e) else np.nan)
    ok = {k: v for k, v in res.items() if v[0] >= 5 and v[2] > 0 and v[1] >= 0.55}
    verdict = max(ok, key=lambda k: ok[k][2]).upper() if ok else "SIT OUT"
    return dict(res, verdict=verdict)


def grade(ev: pd.DataFrame, chain: pd.DataFrame, exp1: str, now_ms: int) -> pd.DataFrame:
    """Paper-grade today's events on a real contract at the live quotes (zero: "buy at the ask, sell at the bid"):
    1DTE, one strike (5 pts) in the money — call for a long, put for a short. Entry = ask at the first chain snapshot
    at/after the event, exit = bid FWD min later (or the latest snapshot while the trade is still open)."""
    cols = ["t", "kind", "trade", "contract", "entry", "exit", "pct", "spx_pts", "open"]
    if ev is None or not len(ev) or chain is None or not len(chain):
        return pd.DataFrame(columns=cols)
    from .timeutil import ET
    c = chain[chain["exp"].astype(str) == exp1][["ts_ms", "strike", "cp", "bid", "ask", "spot"]]
    if not len(c):
        return pd.DataFrame(columns=cols)
    c = c.sort_values("ts_ms")
    out = []
    for r in ev.itertuples():
        t_ms = int(pd.Timestamp(r.t).tz_localize(ET).value // 10**6)
        cp = 1 if r.dir > 0 else -1
        k = (np.floor((r.px - 5) / 5) * 5) if cp > 0 else (np.ceil((r.px + 5) / 5) * 5)
        leg = c[(c["cp"] == cp) & (c["strike"] == k)]
        if not len(leg):
            continue
        a = leg[leg["ts_ms"] >= t_ms].head(1)
        if not len(a) or a["ts_ms"].iloc[0] - t_ms > 6 * 60_000:      # snapshots thin to 5 min under memory pressure
            continue
        entry = float(a["ask"].iloc[0])
        t_out = t_ms + FWD * 60_000
        is_open = now_ms < t_out
        b = leg[leg["ts_ms"] <= min(t_out, now_ms)].tail(1)
        ex = float(b["bid"].iloc[0]) if len(b) else np.nan
        out.append((r.t, r.kind, "LONG" if cp > 0 else "SHORT", f"{exp1[5:]} {k:.0f}{'C' if cp > 0 else 'P'}", entry, ex,
                    (ex / entry - 1) if entry > 0 and ex == ex else np.nan, r.pts, is_open))
    return pd.DataFrame(out, columns=cols)
