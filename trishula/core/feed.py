"""v0.20.0 — signals feed for NinjaTrader (Signals view S1, S3–S7 only; no DT v2 marks).

A background thread (started once per app version) recomputes the Signals marks every 60 s during RTH, for every
sensitivity (fewer / middle / more) × tape (0DTE / 0+1DTE), and writes ONE JSON file into the app's `static/` folder:

    https://<app>.streamlit.app/app/static/dtsignals_<SIGNALS_KEY>.json

Static files cannot sit behind the app password (NinjaTrader cannot log in), so the file name carries a long random
key from Streamlit secrets (SIGNALS_KEY). Read-only signals, nothing else.

Every mark carries the SPX level AND the ES level (user 27 Oct): es = spx × (ES / SPX) at that minute (ratio, not an
additive basis), from the recorder's /ES front-month 1-min candles and SPX 1-min candles."""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import traceback

import numpy as np
import pandas as pd

from . import signals as SG
from .timeutil import ET, now_et

EVERY_SEC = 60
FEED_VERSION = 1
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def _ratio_series(rec, minutes: pd.DatetimeIndex, spx: pd.Series) -> pd.Series:
    """ES / SPX per minute (ffill ≤ 5 min, then the last known ratio)."""
    try:
        e = rec.es_df()
    except Exception:                                          # noqa: BLE001
        e = pd.DataFrame()
    if e is None or e.empty or "close" not in e:
        return pd.Series(np.nan, index=minutes)
    t = pd.to_datetime(e["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    es = pd.Series(e["close"].astype(float).values, index=t).groupby(level=0).last().sort_index()
    es = es.reindex(minutes, method="ffill", tolerance=pd.Timedelta(minutes=5))
    r = (es / spx.reindex(minutes)).replace([np.inf, -np.inf], np.nan)
    r = r.where((r > 0.9) & (r < 1.1))
    return r.ffill().bfill()


def _es_series(rec, minutes: pd.DatetimeIndex) -> pd.Series:
    try:
        e = rec.es_df()
    except Exception:                                          # noqa: BLE001
        return pd.Series(np.nan, index=minutes)
    if e is None or e.empty:
        return pd.Series(np.nan, index=minutes)
    t = pd.to_datetime(e["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    es = pd.Series(e["close"].astype(float).values, index=t).groupby(level=0).last().sort_index()
    return es.reindex(minutes, method="ffill", tolerance=pd.Timedelta(minutes=5))


def build(rec) -> dict:
    """The feed payload as of now (no Streamlit calls — runs in a background thread).
    v0.20.2: also the OVERNIGHT session (Cboe GTH 20:15 → 09:30) — same rules and settings, marked session="GTH",
    tested=false (the walk-forward covered RTH only; user tests overnight live). RTH marks: session="RTH", tested=true."""
    from . import interval as IV
    from . import session as S
    from . import vs3d_data as D
    from tabs import agrev3d as R3
    now = now_et().replace(tzinfo=None)
    out = dict(feed_version=FEED_VERSION, generated=now_et().isoformat(timespec="seconds"), session=None,
               status="idle", note="", es_symbol=getattr(rec, "es_sym", None), marks=[], record=[])
    if not rec.exps:
        out["note"] = "recorder not ready"; return out
    day = rec.exps[0]
    out["session"] = str(day)
    g0 = pd.Timestamp(S.open_dt(day))                                    # 20:15 ET the evening before
    o_ = pd.Timestamp(dt.datetime.combine(day, dt.time(9, 30)))
    bars = D.bars_for(rec, day)
    if bars is None or bars.empty:
        out["note"] = "no SPX bars yet"; return out
    last = min(pd.Timestamp(bars["t"].max()), pd.Timestamp(dt.datetime.combine(day, dt.time(15, 59))))
    if last < g0 + pd.Timedelta(minutes=15):
        out["status"] = "pre-open"; out["note"] = "overnight signals start ~20:30 ET"; return out
    allm = pd.date_range(g0, last, freq="1min")
    spx = pd.Series(bars["c"].astype(float).values, index=pd.to_datetime(bars["t"]).dt.floor("1min"))
    spx = spx[~spx.index.duplicated(keep="last")].reindex(allm).ffill()
    ratio = _ratio_series(rec, allm, spx)
    es_dir = _es_series(rec, allm)
    windows = [("GTH", pd.date_range(g0, min(last, o_ - pd.Timedelta(minutes=1)), freq="1min"))]
    if last >= o_ + pd.Timedelta(minutes=15):
        windows.append(("RTH", pd.date_range(o_, last, freq="1min")))
    spot_now, _ = rec.spot_now()
    with rec.lock:
        legs = dict(rec.legs)
    e0 = str(day)
    for mode in ("0DTE", "0+1DTE"):
        use = R3.ridge_exps(rec, e0, "0+1DTE") if mode == "0+1DTE" else [e0]
        ps = []
        for e_ in use:
            q = rec.print_minutes(e_)                                   # v0.21.2: incremental, no store copy
            if len(q):
                ps.append(q[S.mask(q["t"], day)])
        p = pd.concat(ps, ignore_index=True) if ps else None
        c1 = R3.candles_for(rec, use, day)
        o = SG.minute_flow(c1, p, legs)
        wf = SG.wf_table(mode)
        for pos in SG.POSITIONS:
            ok = {r.code: bool(r.PASS) for r in wf[wf["position"] == pos].itertuples()}
            for r in wf[wf["position"] == pos].itertuples():
                out["record"].append(dict(mode=mode, position=pos, code=r.code, passed=bool(r.PASS),
                                          edge20=None if pd.isna(r.edge20) else float(r.edge20),
                                          t=None if pd.isna(r.t) else float(r.t),
                                          per_day=None if pd.isna(r.per_day) else float(r.per_day)))
            for sess, win in windows:
                if len(win) < 15:
                    continue
                sp = spx.reindex(win)
                ev = SG.compute_picks(o, sp, win, day, SG.picks_for(pos, wf), mode)
                for e in ev.itertuples():
                    px = float(spx.get(e.t, np.nan)); rt = float(ratio.get(e.t, np.nan)); ed = float(es_dir.get(e.t, np.nan))
                    if sess == "GTH" and ed == ed:
                        es = round(ed * 4) / 4                                   # overnight SPX is derived FROM ES
                    elif px == px and rt == rt:
                        es = round(px * rt * 4) / 4                              # RTH: SPX × ES/SPX of that minute
                    else:
                        es = None
                    out["marks"].append(dict(
                        id=f"{e.t:%Y%m%d-%H%M}-{e.code}-{mode}-{pos}",
                        t=pd.Timestamp(e.t).tz_localize(ET).isoformat(), code=e.code, name=SG.SIG[e.code][0],
                        dir=int(e.d), mode=mode, position=pos, session=sess, tested=(sess == "RTH"),
                        passed=bool(ok.get(e.code, False)) and sess == "RTH",
                        rth_passed=bool(ok.get(e.code, False)),         # did this signal × setting pass the RTH test
                        spx=None if px != px else round(px, 2), es=es, ratio=None if rt != rt else round(rt, 6)))
    out["status"] = "live" if (now - last) < pd.Timedelta(minutes=5) else "closed"
    out["marks"].sort(key=lambda m: m["t"])
    return out


def book_payload(rec) -> dict | None:
    """v0.21.0: the VS3D Book's key levels + flow-signed strike profile (0DTE), SPX and ES.
    levels: before the 09:35 lock = PREVIEW (yesterday's book), after = LOCKED for the session (as the Book tab).
    straddle band = spot ± ATM straddle (moves with spot). profile = dealer NET CONTRACTS per strike (inferred sign ×
    OI, opacity = confidence) — chart 1 of the Book. ES = SPX × (ES / SPX) of the latest minute."""
    from . import book as B
    from . import vs3d_data as D
    if not rec.exps:
        return None
    target = rec.exps[0]
    day = D.session_date(rec)
    is_today = day == target
    e0 = str(target)
    ch, spot, now = D.frame(rec, [e0], None)
    if ch.empty or not spot == spot or not ch["gamma"].notna().any():
        return None
    ch0 = ch[ch["exp"] == e0]
    strad = B.mid_straddle(ch0, spot)
    ds = rec.dsign_table(e0)
    seed_rows = B.seed_dot_rows(ch, ds)
    rows = B.signed_book_rows(ch, spot, units="contracts")
    if rows is None or rows.empty:
        return None
    try:
        e = rec.es_df()
        es_last = float(e["close"].iloc[-1]) if len(e) else float("nan")
    except Exception:                                          # noqa: BLE001
        es_last = float("nan")
    ratio = es_last / spot if (es_last == es_last and 0.9 < es_last / spot < 1.1) else float("nan")

    def es(x):
        return None if (x is None or not ratio == ratio) else round(float(x) * ratio * 4) / 4

    lock = D.card_lock(rec, [e0], day, strad) if is_today else None
    state, lv = "none", None
    if isinstance(lock, dict) and lock.get("levels"):
        state, lv = "locked", lock["levels"]
    else:
        ref, _ = D.method_ref(rec, spot, target, now)
        out = {}
        B.key_levels_lines(rows, spot, strad, "w", "g", "r", "c", "d", "y", ref_spot=ref,
                           open_strad=D.open_straddle(rec, [e0], day) if is_today else None, levels_out=out,
                           seed_rows=seed_rows)
        if out.get("ok"):
            state, lv = "preview", out.get("levels")
    levels = []
    if lv:
        if lv.get("bal"):
            levels.append(dict(name="BALANCE", kind="bal", spx=round(float(lv["bal"]["peak"]), 2), es=es(lv["bal"]["peak"])))
        for t in lv.get("ups", []):
            levels.append(dict(name="UP TEST", kind="up", spx=round(float(t["peak"]), 2), es=es(t["peak"])))
        for t in lv.get("dns", []):
            levels.append(dict(name="DN TEST", kind="dn", spx=round(float(t["peak"]), 2), es=es(t["peak"])))
    prof = rows[(rows["strike"] - spot).abs() <= 150]
    return dict(state=state, locked_at=(lock or {}).get("locked_at") if state == "locked" else None,
                lock_note=D.lock_note(lock) if state == "locked" else "",
                spx_spot=round(float(spot), 2), es_spot=None if es_last != es_last else es_last,
                ratio=None if ratio != ratio else round(ratio, 6), levels=levels,
                straddle=None if not strad else dict(value=round(float(strad), 2), up_spx=round(spot + strad, 2),
                                                      dn_spx=round(spot - strad, 2), up_es=es(spot + strad),
                                                      dn_es=es(spot - strad)),
                profile=[dict(strike=float(r.strike), es=es(r.strike), net=round(float(r.signed_pct), 1),
                              conf=round(float(getattr(r, "conf", 0.5)), 2)) for r in prof.itertuples()])


def write(payload: dict, key: str) -> str:
    os.makedirs(STATIC, exist_ok=True)
    path = os.path.join(STATIC, f"dtsignals_{key}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(tmp, path)                                      # atomic: NinjaTrader never reads half a file
    return path


class Feed:
    def __init__(self, rec, key: str):
        self.rec, self.key = rec, key
        self.last_ok = None; self.last_err = None; self.n_marks = 0
        self._stop = False
        self.thread = threading.Thread(target=self._run, name="trishula-feed", daemon=True)

    def start(self):
        if not self.thread.is_alive():
            self.thread.start()
        return self

    def stop(self):
        self._stop = True

    def _run(self):
        while not self._stop:
            t0 = time.time()
            try:
                n = now_et()
                from .session import market_state
                ms_ = market_state(n.replace(tzinfo=None), set(getattr(self.rec, "all_exps", []) or []))
                late = n.weekday() < 5 and dt.time(16, 0) <= n.time() <= dt.time(16, 10)     # final write after the close
                if ms_ in ("RTH", "GTH") or late or self.last_ok is None:
                    p = self.build_and_write()
                    from . import mem as _mem
                    _mem.trim(0)                                       # v0.21.2: hand the build's buffers back
                    print(f"[feed] {n:%H:%M:%S} {p['status']} · {len(p['marks'])} marks · {time.time() - t0:.1f}s", flush=True)
            except Exception as e:                             # noqa: BLE001
                self.last_err = f"{type(e).__name__}: {e}"
                print(f"[feed] error {self.last_err}\n{traceback.format_exc(limit=3)}", flush=True)
            time.sleep(max(5.0, EVERY_SEC - (time.time() - t0)))

    LOCK_MIN = 3        # v0.20.3: a mark older than this is FINAL — it never moves or disappears afterwards

    def build_and_write(self) -> dict:
        p = build(self.rec)
        p = self._freeze(p)
        try:
            p["book"] = book_payload(self.rec)
        except Exception as e:                                 # noqa: BLE001
            p["book"] = None
            p["book_error"] = f"{type(e).__name__}: {e}"
        write(p, self.key)
        self.last_ok = now_et(); self.n_marks = len(p["marks"]); self.last_err = None
        return p

    def _freeze(self, p: dict) -> dict:
        """v0.20.3 — NO REPAINT in the feed. The signals are recomputed over the whole session every minute, and late data
        (the 5-min candle sweep tops up the last 20 min, a restart rebuilds the morning, 10-min cooldowns chain) could move
        or remove marks already published — NinjaTrader then showed them in different places after every reload.
        Now: once a mark is ≥ LOCK_MIN minutes old it is locked as published and always re-sent unchanged; a mark that only
        appears later for an already-locked time is dropped; newer marks are sent with final=false (may still change)."""
        if not hasattr(self, "_locked") or getattr(self, "_lock_day", None) != p.get("session"):
            self._locked, self._lock_day, self._lock_upto = {}, p.get("session"), None
        cut = (now_et() - pd.Timedelta(minutes=self.LOCK_MIN)).isoformat()
        fresh = {m["id"]: m for m in p["marks"]}
        upto = self._lock_upto
        for i, m in fresh.items():                         # lock newly-final marks (only after the previous lock point)
            if m["t"] <= cut and i not in self._locked and (upto is None or m["t"] > upto):
                self._locked[i] = dict(m, final=True)
        self._lock_upto = cut if (upto is None or cut > upto) else upto
        out = list(self._locked.values())
        out += [dict(m, final=False) for m in fresh.values() if m["t"] > self._lock_upto and m["id"] not in self._locked]
        p["marks"] = sorted(out, key=lambda m: m["t"])
        p["locked_until"] = self._lock_upto
        return p
