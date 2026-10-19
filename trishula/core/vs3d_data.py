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
    if "volume" not in c:
        c["volume"] = c["day_volume"] if "day_volume" in c else 0.0
    return c


def naive_et(ms) -> dt.datetime:
    return dt.datetime.fromtimestamp(int(ms) / 1000, ET).replace(tzinfo=None)


def et_ms(d: dt.date, t: dt.time) -> int:
    return int(dt.datetime.combine(d, t, tzinfo=ET).timestamp() * 1000)


def session_date(rec) -> dt.date:
    """The session the screen is about.
    GTH on: the trading day the clock (or the replay frame) belongs to — from 20:15 ET the
    evening before, the next session is live (overnight prints, synthetic spot).
    GTH off: today's 0DTE date, or the last traded day when no candle exists yet for it."""
    from . import session as S
    asof = getattr(rec, "ts_ms", None)
    if S.gth():
        now = naive_et(asof) if asof else dt.datetime.now(ET).replace(tzinfo=None)
        return S.trading_day_for(now)
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
    """1-minute SPX bars for the session view: SPX candles where they exist (RTH), and
    overnight (GTH) bars resampled from the recorder's 5-s spot (synthetic parity when the
    index doesn't print). Column 'src' = candle / spot."""
    from . import session as S
    cols = ["t", "o", "h", "l", "c", "ts_ms", "src"]
    lo, hi = S.bounds_ms(day)
    if upto_ms:
        hi = min(hi, int(upto_ms) + 1)
    parts = []
    c = rec.candles_df()
    if len(c):
        c = c[(c["ts_ms"] >= lo) & (c["ts_ms"] < hi)]
        if len(c):
            parts.append(pd.DataFrame({"ts_ms": c["ts_ms"].values, "o": c["open"].values, "h": c["high"].values,
                                       "l": c["low"].values, "c": c["close"].values, "src": "candle"}))
    sp = rec.spot_df()
    if len(sp) and "spot" in sp:
        sp = sp[(sp["ts_ms"] >= lo) & (sp["ts_ms"] < hi)].dropna(subset=["spot"])
        if len(sp):
            m = (sp["ts_ms"] // 60000) * 60000
            g = sp.groupby(m)["spot"].agg(["first", "max", "min", "last"]).reset_index()
            g.columns = ["ts_ms", "o", "h", "l", "c"]
            g["src"] = "spot"
            have = set(parts[0]["ts_ms"]) if parts else set()
            g = g[~g["ts_ms"].isin(have)]
            if parts and len(parts[0]):                 # candles own RTH; spot fills only the gaps outside it
                first_c = int(parts[0]["ts_ms"].min())
                last_c = int(parts[0]["ts_ms"].max())
                g = g[(g["ts_ms"] < first_c) | (g["ts_ms"] > last_c)]
            parts.append(g)
    if not parts:
        return pd.DataFrame(columns=cols)
    b = pd.concat(parts, ignore_index=True).sort_values("ts_ms")
    b = b[b["c"].notna() & (b["c"] > 0)]
    b["t"] = pd.to_datetime(b["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return b[cols].reset_index(drop=True)


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
    if len(b):
        b = b[b["t"] >= dt.datetime.combine(day, dt.time(9, 30))]
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
    asof = getattr(rec, "ts_ms", None)                   # replay: a lock that formed after t does not exist yet
    if key in rec.ui_state:
        lk = rec.ui_state[key]
        return None if (asof is not None and lk["ts_ms"] > asof) else lk
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


def peak_track(rec, exp, day):
    """[(naive ET datetime, strike)] — per stored snapshot, the strike of its own
    peak positive signed gamma (vs3dgbt peak_track; computed once per ts)."""
    from . import terrain as T
    h = rec.chain_df()
    if h.empty:
        return []
    from . import session as S
    lo_, hi_ = S.bounds_ms(day)
    h = h[(h["exp"] == exp) & (h["ts_ms"] >= lo_) & (h["ts_ms"] <= hi_)]
    pt = rec.ui_state.setdefault(f"peak_track_{exp}", {})
    for t, g in h.groupby("ts_ms"):
        if t not in pt:
            s = _typed(g)
            sp = float(s["spot"].dropna().iloc[0]) if s["spot"].notna().any() else float("nan")
            pt[t] = T.peak_strike_of(s, sp)
    asof = getattr(rec, "ts_ms", None)
    return [(naive_et(t), v) for t, v in sorted(pt.items()) if v is not None and (asof is None or t <= asof)]


def read_inputs(rec, exps, ts_ms):
    """Everything vs3dgbt's read_verdict pulled from session state, rebuilt from snapshots ≤ t."""
    from . import read as RD
    from . import terrain as T
    ch, spot, now = frame(rec, exps, ts_ms)
    if ch.empty or not spot == spot:
        return None
    e0 = exps[0]
    ch0 = ch[ch["exp"] == e0]
    times = snapshot_times(rec, e0)
    upto = ts_ms or int(dt.datetime.now(ET).timestamp() * 1000)
    times = [t for t in times if t <= upto]
    prev = None
    cand = [t for t in times if t < (ts_ms or upto + 1)]
    if ts_ms is not None:
        cand = [t for t in times if t < ts_ms]
    if cand:
        pc, ps, pt = frame(rec, [e0], cand[-1])
        if len(pc) and ps == ps:
            prev = (pc, ps, pt)
    day = now.date()
    cache = rec.ui_state.setdefault("_gmag", {})
    hist, last = [], 0
    for t in times:
        if naive_et(t).date() != day or t - last < 5 * 60_000:
            continue
        last = t
        k = (e0, t)
        if k not in cache:
            c, s, n = frame(rec, [e0], t)
            try:
                cache[k] = RD.gmag_at(c, s, e0, n) if len(c) and s == s else None
            except Exception:                               # noqa: BLE001
                cache[k] = None
        if cache[k] is not None:
            hist.append(cache[k])
    so = open_straddle(rec, exps, day)
    lbl = "open 09:30"
    if not so:
        first = [t for t in times if naive_et(t).date() == day]
        if len(first) >= 2:
            c, s, _ = frame(rec, [e0], first[0])
            so = T.terrain_straddle(c, s) if len(c) else None
            lbl = "1st snap"
    v = rec.vix_df()
    vix = float(v["close"].iloc[-1]) if len(v) else None
    return dict(ch=ch, ch0=ch0, spot=spot, now=now, prev=prev, gmag_hist=hist, strad_open=so, open_lbl=lbl,
                vix=vix, n_snaps=len(times), e0=e0)
