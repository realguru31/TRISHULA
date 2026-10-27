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
            q = IV.prep_prints(rec.prints_df(e_), rec.greeks, spot_now)
            if len(q):
                ps.append(q[S.mask(q["ts"], day)])
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
                    print(f"[feed] {n:%H:%M:%S} {p['status']} · {len(p['marks'])} marks · {time.time() - t0:.1f}s", flush=True)
            except Exception as e:                             # noqa: BLE001
                self.last_err = f"{type(e).__name__}: {e}"
                print(f"[feed] error {self.last_err}\n{traceback.format_exc(limit=3)}", flush=True)
            time.sleep(max(5.0, EVERY_SEC - (time.time() - t0)))

    def build_and_write(self) -> dict:
        p = build(self.rec)
        write(p, self.key)
        self.last_ok = now_et(); self.n_marks = len(p["marks"]); self.last_err = None
        return p
