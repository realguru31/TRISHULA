"""VS3D data layer: builds vs3dgbt-shaped frames (chain with type and dsign, spot,
bars, open, opening straddle, 09:25 lock, strip history) from the recorder."""
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
    """1-minute SPX bars for the session view, best source per minute:
      candle — SPX 1-minute candles (RTH)
      spot   — the recorder's 5-s spot (synthetic parity overnight); stale SPX prints dropped
      es     — /ES front-month 1-minute candles shifted onto SPX by the measured ES−SPX basis,
               for any minute the recorder has nothing for (overnight before a restart)."""
    from . import session as S
    cols = ["t", "o", "h", "l", "c", "ts_ms", "src"]
    lo, hi = S.bounds_ms(day)
    if upto_ms:
        hi = min(hi, int(upto_ms) + 1)
    parts = []
    c = rec.candles_df()
    cand = pd.DataFrame()
    if len(c):
        cand = pd.DataFrame({"ts_ms": c["ts_ms"].values, "o": c["open"].values, "h": c["high"].values,
                             "l": c["low"].values, "c": c["close"].values, "src": "candle"})
        cw = cand[(cand["ts_ms"] >= lo) & (cand["ts_ms"] < hi)]
        if len(cw):
            parts.append(cw)
    have = set(parts[0]["ts_ms"]) if parts else set()
    first_c = int(parts[0]["ts_ms"].min()) if parts else None
    last_c = int(parts[0]["ts_ms"].max()) if parts else None
    spm = pd.DataFrame()
    sp = rec.spot_df()
    if len(sp) and "spot" in sp:
        sp = sp.dropna(subset=["spot"])
        if "spot_src" in sp:                         # the index doesn't print overnight: an 'spx' value
            t = pd.to_datetime(sp["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
            rth = (t.dt.time >= dt.time(9, 30)) & (t.dt.time <= dt.time(16, 15)) & (t.dt.weekday < 5)
            src = sp["spot_src"].astype(str)
            sp = sp[~src.isin(["spx_stale", "prev_close"]) & ~((src == "spx") & ~rth.values)]
        if len(sp):
            m = (sp["ts_ms"] // 60000) * 60000
            spm = sp.groupby(m)["spot"].agg(["first", "max", "min", "last"]).reset_index()
            spm.columns = ["ts_ms", "o", "h", "l", "c"]
            spm["src"] = "spot"
            g = spm[(spm["ts_ms"] >= lo) & (spm["ts_ms"] < hi) & ~spm["ts_ms"].isin(have)]
            if first_c is not None:              # candles own RTH; spot fills only the gaps outside it
                g = g[(g["ts_ms"] < first_c) | (g["ts_ms"] > last_c)]
            if len(g):
                parts.append(g)
                have |= set(g["ts_ms"])
    es = rec.es_df() if hasattr(rec, "es_df") else pd.DataFrame()
    if len(es):
        ref = pd.concat([x[["ts_ms", "c"]] for x in (cand, spm) if len(x)], ignore_index=True) if (len(cand) or len(spm)) else pd.DataFrame()
        basis = None
        if len(ref):
            j = es[["ts_ms", "close"]].merge(ref.drop_duplicates("ts_ms", keep="last"), on="ts_ms")
            j = j[j["ts_ms"] < hi].sort_values("ts_ms")
            if len(j):
                basis = float((j["close"] - j["c"]).tail(60).median())   # most recent ES − SPX difference
        if basis is not None:
            e = es[(es["ts_ms"] >= lo) & (es["ts_ms"] < hi) & ~es["ts_ms"].isin(have)]
            if len(e):
                parts.append(pd.DataFrame({"ts_ms": e["ts_ms"].values, "o": e["open"].values - basis,
                                           "h": e["high"].values - basis, "l": e["low"].values - basis,
                                           "c": e["close"].values - basis, "src": "es"}))
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


LOCK_T = dt.time(9, 25)     # v0.27.0: levels lock pre-market, like Dan's published pre-open levels


def oi_fresh(rec, ch, day, spot) -> bool | None:
    """Has today's OCC open interest arrived? Compares the near-spot 0DTE OI in `ch` with the OI the recorder logged
    on the previous day for the same contracts. True = refreshed · False = still yesterday's numbers · None = can't
    tell (no previous-day log, too few contracts)."""
    try:
        log = getattr(rec, "oi_log", {}) or {}
        prev = [k for k in log if k < str(day)]
        if not prev or ch is None or ch.empty:
            return None
        pv = log[max(prev)]
        c = ch[((ch["strike"] - spot).abs() <= spot * 0.03) & ch["oi"].notna() & (ch["oi"] > 0)]
        pairs = [(float(o), float(pv[s_])) for s_, o in zip(c["sym"], c["oi"]) if s_ in pv]
        if len(pairs) < 20:
            return None
        same = sum(1 for o, p in pairs if abs(o - p) < 0.5) / len(pairs)
        return same < 0.9
    except Exception:                                          # noqa: BLE001
        return None


def card_lock(rec, exps, day, strad_now):
    """v0.27.0 lock: Dan's Test/Anchor levels from the OPENING position (first snapshot ≥ 09:25 ET, dealer net
    contracts), centred on spot at that snapshot ± its ATM straddle, frozen for the session (shared by every viewer).
    Waits for today's OI: a snapshot still carrying yesterday's OI is skipped (rec.ui_state['oistale_<day>'] set).
    Saved to the GitHub state branch when it forms and restored after a reboot; a lock formed after 09:30 is flagged
    late (the app was not running pre-market)."""
    key = f"lock_{day}_{'|'.join(exps)}"
    asof = getattr(rec, "ts_ms", None)                   # replay: a lock that formed after t does not exist yet
    if key in rec.ui_state:
        lk = rec.ui_state[key]
        return None if (asof is not None and lk["ts_ms"] > asof) else lk
    from . import state as ST                            # the lock survives a reboot (GitHub side branch)
    lk = ST.load_lock(str(day), key)
    if lk and lk.get("levels"):
        lk = dict(lk, src="restored")
        rec.ui_state[key] = lk
        return None if (asof is not None and lk["ts_ms"] > asof) else lk
    h = rec.chain_df()
    if h.empty:
        return None
    lo, hi = et_ms(day, LOCK_T), et_ms(day, dt.time(16, 15))
    if asof is not None:
        hi = min(hi, int(asof) + 1)
    snaps = sorted(h.loc[(h["exp"] == exps[0]) & (h["ts_ms"] >= lo) & (h["ts_ms"] < hi), "ts_ms"].unique().tolist())
    scan_k = f"lockscan_{day}_{'|'.join(exps)}"
    if asof is None:                                     # live: don't re-check snapshots already found stale
        snaps = [t for t in snaps if t > rec.ui_state.get(scan_k, 0)]
    for ts in snaps:
        ch, sp, _ = frame(rec, exps, ts)
        if ch.empty or not sp == sp:
            continue
        fresh = oi_fresh(rec, ch[ch["exp"] == exps[0]], day, sp)
        if fresh is False:
            rec.ui_state[f"oistale_{day}"] = naive_et(ts).strftime("%H:%M")
            if asof is None:
                rec.ui_state[scan_k] = ts
            continue
        rows = B.signed_book_rows(ch, sp, units="contracts")
        if rows is None:
            continue
        S = B.mid_straddle(ch[ch["exp"] == exps[0]], sp) or strad_now
        lv = B.method_levels(rows, sp, S)
        if lv is None:
            continue
        rec.ui_state.pop(f"oistale_{day}", None)
        near = rows[(rows["strike"] - sp).abs() <= 200]
        lk = {"levels": lv, "locked_at": naive_et(ts).strftime("%H:%M"), "ts_ms": ts, "method": "dan",
              "src": "live", "late": bool(ts > et_ms(day, dt.time(9, 30))), "oi_check": fresh,
              # the lock's profile itself (dealer net contracts per strike) → NinjaTrader dots + TradingView P:
              "profile": [[float(k), round(float(v), 1)] for k, v in zip(near["strike"], near["signed_pct"])]}
        rec.ui_state[key] = lk
        if asof is None:
            ST.save_lock(str(day), key, lk)
        return lk
    return None


def oi_stale_note(rec, day) -> str:
    t = rec.ui_state.get(f"oistale_{day}")
    return f"OI stale (yesterday's numbers at {t}) — lock pending until today's OI arrives" if t else ""


def clean_lock(rec, e0, day, strad_now, spot, now, ref):
    """v0.22.0: SINGLE-LEG (clean-B) key levels from the single-leg book's OWN structure, locked the first time they
    are computed at/after 09:25 (v0.27.0; the feed thread does this every minute) and frozen for the session.
    Saved / restored with the main lock (GitHub state branch). The main book and its levels are untouched.
    (Chain snapshots carry no single-leg signs, so this lock is taken live, not from a snapshot.)"""
    key = f"clean_{day}_{e0}"
    asof = getattr(rec, "ts_ms", None)
    if key in rec.ui_state:
        lk = rec.ui_state[key]
        return None if (asof is not None and lk["ts_ms"] > asof) else lk
    from . import state as ST
    lk = ST.load_lock(str(day), key)
    if lk and lk.get("levels"):
        lk = dict(lk, src="restored")
        rec.ui_state[key] = lk
        return None if (asof is not None and lk["ts_ms"] > asof) else lk
    if asof is not None or now.date() != day or now.time() < LOCK_T:
        return None
    rows = B.cleanB_rows(rec.dsign_table(e0, single_leg=True), "all")
    if rows is None or rows.empty:
        return None
    lv = B.method_levels(rows, spot, strad_now)
    if lv is None:
        return None
    ts = et_ms(day, now.time().replace(second=0, microsecond=0))
    near = rows[(rows["strike"] - spot).abs() <= 200]
    lk = {"levels": lv, "locked_at": now.strftime("%H:%M"), "ts_ms": ts, "src": "live", "method": "dan",
          "late": bool(now.time() > dt.time(9, 30)),
          "profile": [[float(k), round(float(v), 1)] for k, v in zip(near["strike"], near["signed_pct"])]}
    rec.ui_state[key] = lk
    ST.save_lock(str(day), key, lk)
    return lk


def clean_preview(rows, spot, strad_now, ref):
    """Single-leg levels on the current single-leg book (before the clean lock exists)."""
    if rows is None or rows.empty:
        return None
    return B.method_levels(rows, spot, strad_now)


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
    v = v[v["ts_ms"] >= et_ms(day, dt.time(3, 0))]           # VIX trades from 03:15 ET
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


def lock_note(lk) -> str:
    """One line for the Book header / NinjaTrader status: where the lock came from."""
    if not isinstance(lk, dict):
        return ""
    parts = []
    if lk.get("late"):
        parts.append(f"⚠ LATE LOCK {lk.get('locked_at')} — app was not running at 09:25 (not the pre-market levels)")
    if lk.get("src") == "restored":
        parts.append("restored after restart")
    return " · ".join(parts)


def level_list(lv) -> list:
    """[(kind, spx)] from a levels dict: bal / ups / dns."""
    out = []
    if not isinstance(lv, dict):
        return out
    if lv.get("bal"):
        out.append(("bal", float(lv["bal"]["peak"])))
    out += [("up", float(t["peak"])) for t in lv.get("ups", [])]
    out += [("dn", float(t["peak"])) for t in lv.get("dns", [])]
    return out


def tv_line(day, spot, lock, main_preview, clk, clean_preview_lv, flow_rows, clean_rows, span=100.0) -> str:
    """v0.23.0: ONE line for the TradingView "TRISHULA Levels" script (paste per day), SPX prices:
    TRI1|YYYY-MM-DD|M:B7675,U7680,D7670|S:B7760,U7765,D7740|P:7600:4243,…|Q:7615:44,…
    M/S = main / single-leg levels LOCKED (m/s lowercase = preview) · B balance, U up test, D down test ·
    P = main profile at the lock (dealer net contracts per strike), Q = single-leg profile at its lock
    (current book when not locked yet) · strikes within ±span of spot."""
    def lv(levels):
        return ",".join(f"{dict(bal='B', up='U', dn='D')[k]}{v:g}" for k, v in level_list(levels))

    def prof(pairs):
        return ",".join(f"{k:g}:{int(round(v))}" for k, v in pairs if abs(k - spot) <= span and round(v) != 0)

    def rows_pairs(r):
        return [] if r is None or r.empty else list(zip(r["strike"].astype(float), r["signed_pct"].astype(float)))
    parts = ["TRI1", str(day)]
    if isinstance(lock, dict) and lock.get("levels"):
        parts.append("M:" + lv(lock["levels"]))
    elif main_preview:
        parts.append("m:" + lv(main_preview))
    if isinstance(clk, dict) and clk.get("levels"):
        parts.append("S:" + lv(clk["levels"]))
    elif clean_preview_lv:
        parts.append("s:" + lv(clean_preview_lv))
    parts.append("P:" + prof((lock or {}).get("profile") or rows_pairs(flow_rows)))
    parts.append("Q:" + prof((clk or {}).get("profile") or rows_pairs(clean_rows)))
    return "|".join(parts)

