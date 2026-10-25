"""TRISHULA recorder — a background thread inside the Streamlit app.

Started once per app container (st.cache_resource). Holds ONE DXLink
connection, records the SPX 0DTE + 1DTE tape, quotes, greeks, OI and spot,
keeps the whole day in memory for the tabs, and flushes new rows to the
trishula-data GitHub repo every FLUSH_MIN minutes. On a container restart it
reloads today's rows from the repo first, so at most the unflushed minutes
plus the downtime are lost. Gaps are logged.

The app must stay awake: keep one browser tab open on the app (VPS).
"""
from __future__ import annotations

import asyncio
import math
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import date, time as dtime

import pandas as pd

from . import signs
from .classify import aggr, bucket
from .store import DataRepo, LocalRepo
from .timeutil import now_et, recording_window
from .version import VERSION

FLUSH_MIN = 5
SNAP_SEC = 60          # chain snapshot cadence
SPOT_SEC = 5           # spot row cadence
STRIKES_EACH_SIDE = 60   # ±300 pts ≈ ±4% at SPX 7600
EXTRA_STRIKES = 60       # on-demand expiries (weekly / monthly picked in the UI)
STRIKE_STEP = 5.0
QUOTE_FALLBACK_SEC = 2.0
ROLL_TIME = dtime(16, 15)
CANDLE_BATCH = 90         # tastytrade: 100 Candle subscriptions max (SPX 1m uses one)
SWEEP_EACH, SWEEP_SEC = 14, 300   # v0.18.0 L20h: 1-min candle sweep, 0DTE+1DTE, ±14 strikes (~±70 pts), every 5 min
BACKFILL_EACH = 45         # L16d: 1-min option-candle backfill, strikes each side of spot (0DTE, C+P → ≤ 182 contracts)
REPLAY_QUIET_SEC = 6      # replay considered complete after this long without replayed prints
COMPACT_EVERY = 5000      # prints buffered as dicts, compacted into DataFrame chunks
RECONNECT_HOURS = 6      # fresh session + DXLink quote token well before the 24 h expiry


def _f(x) -> float:
    try:
        v = float(x)
        return v if not math.isnan(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _ok(v: float) -> bool:
    return v == v and v > 0


def _concat_cat(chunks, cats) -> pd.DataFrame:
    """concat that keeps text columns categorical (plain concat turns mixed categories into
    object/str = several × the memory)."""
    chunks = [c for c in chunks if c is not None and len(c)]
    if not chunks:
        return pd.DataFrame()
    if len(chunks) == 1:
        d = chunks[0]
        for c in cats:
            if c in d and not isinstance(d[c].dtype, pd.CategoricalDtype):
                d = d.assign(**{c: d[c].astype("category")})
        return d
    from pandas.api.types import union_categoricals
    uni = {}
    for c in cats:
        if all(c in x for x in chunks):
            parts = [x[c] if isinstance(x[c].dtype, pd.CategoricalDtype) else x[c].astype("category") for x in chunks]
            uni[c] = union_categoricals(parts, ignore_order=True)
    d = pd.concat([x.drop(columns=[c for c in uni if c in x]) for x in chunks], ignore_index=True)
    for c, v in uni.items():
        d[c] = pd.Categorical(v)
    cols = [c for c in chunks[0].columns if c in d] + [c for c in d.columns if c not in chunks[0].columns]
    return d[cols]


class Frames:
    """Append-only list of DataFrame chunks with a cached concatenation."""

    CAT = ("exp", "sym", "spot_src")

    def __init__(self, chunks=None):
        self.chunks = list(chunks or [])
        self._cache = None

    def append(self, df: pd.DataFrame):
        if df is None or not len(df):
            return
        df = df.copy()
        for c in self.CAT:
            if c in df:
                df[c] = df[c].astype("category")
        self.chunks.append(df)
        self._cache = None
        if len(self.chunks) > 240:                       # fold old chunks every ~4 h of snapshots
            self.chunks = [pd.concat(self.chunks, ignore_index=True)]

    def __len__(self):
        return sum(len(c) for c in self.chunks)

    def df(self) -> pd.DataFrame:
        if self._cache is None:
            d = _concat_cat(self.chunks, self.CAT)
            self.chunks = [d] if len(d) else []
            self._cache = d
        return self._cache

    def since(self, n: int) -> pd.DataFrame:
        return self.df().iloc[n:]


class Recorder:
    def __init__(self, client_secret: str, refresh_token: str,
                 data_repo: str | None = None, gh_token: str | None = None):
        self.cs, self.rt = client_secret, refresh_token
        self.repo = DataRepo(data_repo, gh_token) if (data_repo and gh_token) else LocalRepo()
        self.repo_kind = "github" if (data_repo and gh_token) else "local"
        self.cid = uuid.uuid4().hex[:6]                    # container id, part-name suffix
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        # status
        self.state = "starting"
        self.errors: deque = deque(maxlen=40)
        self.started_at = time.time()
        self.last_event_ms = 0
        self.last_flush = None
        self.last_flush_error = None
        self.token_refreshes = 0
        self._stop = False
        self.version = VERSION
        self.all_exps: list[str] = []                   # every listed SPX expiry
        self.exp_types: dict[str, str] = {}             # exp -> Weekly / Regular / Quarterly / End-Of-Month
        self._wanted: set[str] = set()                  # expiries requested by the UI
        self._subscribed: set[str] = set()
        self.recovered = 0
        self.oi_log: dict = {}            # {ET date: {sym: settled OI}} — ΔOI for GEX³ panel 3
        self.ui_state: dict = {}
        self.es_sym: str | None = None          # shared screen state: 09:35 lock, premarket anchor, caches
        self._connect_ms = int(time.time() * 1000)
        self._reset_day()

    # ── day state ────────────────────────────────────────────────────
    def _reset_day(self):
        with self.lock:
            self.exps: list[date] = []
            self.legs: dict[str, tuple[str, float, int]] = {}   # sym -> (exp, strike, cp)
            self.quotes: dict[str, tuple[float, float, int]] = {}  # bid, ask, ms
            self.greeks: dict[str, tuple] = {}                   # iv, delta, gamma, theta, vega, ms
            self.oi: dict[str, float] = {}
            self.dayvol: dict[str, float] = {}
            self.spx = (float("nan"), 0)
            self.spx_prev_close = float("nan")
            self._pbuf: list[dict] = []                         # new prints (dicts)
            self._pchunks: list[pd.DataFrame] = []              # compacted prints
            self._pcache = (0, pd.DataFrame())
            self.c5: dict[tuple, tuple] = {}                     # (sym, ts_ms) -> (vol, bidv, askv) 5-min candles
            self.c1m: dict[tuple, tuple] = {}                    # (sym, ts_ms) -> (close, vol, bidv, askv) 1-min option candles (L16d backfill)
            self.seed = {"state": "pending", "replay_n": 0, "replay_last": 0.0, "candle_legs": 0,
                         "candle_batches": 0, "started": None, "done_at": None}
            self.chain_rows = Frames()                          # chain snapshots (DataFrame chunks)
            self.spot_rows: list[dict] = []
            self.gaps: list[dict] = []
            self._seen: set = set()
            self._fl = {"prints": 0, "chain": 0, "spot": 0, "gaps": 0}
            self.loaded_exp: str | None = None
            self.vix5: dict[int, float] = {}                     # VIX 5m closes
            self.spy1m: dict[int, tuple] = {}                    # SPY 1m (o, h, l, c, volume) — VRVP
            self.es1m: dict[int, tuple] = {}                     # /ES front month 1m (o, h, l, c) — overnight price backfill
            self.candles: dict[int, tuple] = {}          # SPX 1m: time_ms -> (o, h, l, c)

    def _err(self, e: Exception, where: str):
        self.errors.append({"t": now_et().isoformat(timespec="seconds"), "v": VERSION, "where": where,
                            "err": f"{type(e).__name__}: {e}",
                            "tb": traceback.format_exc(limit=3)})

    # ── thread ───────────────────────────────────────────────────────
    def start(self):
        if self._stop or (self.thread and self.thread.is_alive()):
            return
        self.thread = threading.Thread(target=lambda: asyncio.run(self._main()),
                                       daemon=True, name=f"trishula-recorder-{VERSION}")
        self.thread.start()

    def stop(self):
        """Ask the thread to end cleanly (used when a newer version takes over)."""
        self._stop = True
        self.state = "stopped (replaced by newer version)"

    async def _stop_watch(self):
        while not self._stop:
            await asyncio.sleep(1)

    @staticmethod
    def _quiet(loop, ctx):
        """Swallow shutdown noise from cancelled DXLink listeners."""
        msg = str(ctx.get("message", "")) + repr(ctx.get("exception", ""))
        if "destroyed but it is pending" in msg or "aclose()" in msg or "athrow" in msg:
            return
        loop.default_exception_handler(ctx)

    async def _main(self):
        asyncio.get_running_loop().set_exception_handler(self._quiet)
        backoff = 1
        while not self._stop:
            t0 = time.time()
            try:
                await self._run_session()
            except Exception as e:                          # noqa: BLE001
                if "expired" in repr(e).lower() or "expired" in str(getattr(e, "exceptions", "")).lower():
                    self.recovered += 1
                    backoff = 1
                self._err(e, "session")
                self.state = f"reconnecting ({type(e).__name__})"
                with self.lock:
                    self.gaps.append({"start_ms": self.last_event_ms or int(time.time() * 1000),
                                      "end_ms": None, "reason": f"{type(e).__name__}: {e}"[:200]})
            try:
                await asyncio.to_thread(self.flush)
            except Exception as e:                          # noqa: BLE001
                self._err(e, "flush-after-session")
            if self._stop:
                break
            if time.time() - t0 > 300:
                backoff = 1
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2)

    # ── one session = one expiry pair, until roll or error ───────────
    async def _run_session(self):
        from tastytrade import DXLinkStreamer, Session
        from tastytrade.dxfeed import Greeks, Quote, Summary, TimeAndSale, Trade
        from tastytrade.instruments import get_option_chain

        self.state = "authenticating"
        sess = Session(self.cs, self.rt)
        self.state = "loading chain"
        chain = await get_option_chain(sess, "SPX")
        n = now_et()
        today = n.date()
        exps = sorted(d for d in chain if d > today or (d == today and n.time() < ROLL_TIME))
        e0, e1 = exps[0], exps[1]
        self.all_exps = [str(d) for d in exps]
        self.exp_types = {str(d): str(getattr(chain[d][0], "expiration_type", "") or "") for d in exps}
        self._chain = chain

        if self.exps and self.exps[0] != e0:               # new trading session
            await asyncio.to_thread(self.flush)
            self._reset_day()
        if self.loaded_exp != str(e0):
            self.state = "reloading today from data repo"
            await asyncio.to_thread(self._reload, str(e0))
        with self.lock:
            self.exps = [e0, e1]
            for g in self.gaps:                             # close an open gap
                if g["end_ms"] is None:
                    g["end_ms"] = int(time.time() * 1000)

        if not self.oi_log and self.repo:
            try:
                self.oi_log = self.repo.get_json("oi_log.json") or {}
            except Exception as e:                          # noqa: BLE001
                self._err(e, "oi-log-load")
        self.seed.update(state="pending", replay_n=0, candle_batches=0, done_at=None)
        self._candle_lock = asyncio.Lock()
        async with DXLinkStreamer(sess) as s:
            self.state = "finding spot"
            spot = await self._initial_spot(s, Trade, Summary)
            if not _ok(spot):
                ks = sorted({float(o.strike_price) for o in chain[e0]})
                spot = ks[len(ks) // 2]
            legs = {}
            for ex in (e0, e1):
                ks = sorted({float(o.strike_price) for o in chain[ex]})
                atm = min(range(len(ks)), key=lambda i: abs(ks[i] - spot))
                keep = set(ks[max(0, atm - STRIKES_EACH_SIDE): atm + STRIKES_EACH_SIDE + 1])
                for o in chain[ex]:
                    if float(o.strike_price) in keep:
                        cp = 1 if str(o.option_type.value).upper().startswith("C") else -1
                        legs[o.streamer_symbol] = (str(ex), float(o.strike_price), cp)
            with self.lock:
                self.legs = legs
            syms = list(legs)
            self.state = "subscribing"
            # TimeAndSale WITH history: replays the prior RTH + overnight (seed) and
            # anything missed since (gap backfill), capped at 1,000 prints per leg;
            # duplicates are dropped by (sym, index, type).
            await s.subscribe(TimeAndSale, [])
            self._connect_ms = int(time.time() * 1000)
            await self._tas_replay(s, syms)
            self.seed.update(state="replaying", started=now_et().isoformat(timespec="seconds"),
                             replay_last=time.time())
            await s.subscribe(Quote, syms)
            await s.subscribe(Greeks, syms)
            await s.subscribe(Summary, syms)
            await s.subscribe(Trade, syms)
            self._subscribed = {str(e0), str(e1)}
            self._spot_ref = spot
            try:
                from datetime import timedelta
                await s.subscribe_candle(["SPX"], "1m", start_time=now_et() - timedelta(days=4))
                await s.subscribe_candle(["VIX"], "5m", start_time=now_et() - timedelta(days=4))
                await s.subscribe_candle(["SPY"], "1m", start_time=now_et() - timedelta(days=4))   # VRVP volume
            except Exception as e:                          # noqa: BLE001
                self._err(e, "candle-subscribe")
            try:                                            # /ES front month: overnight price path
                from tastytrade.instruments import Future
                futs = await Future.get(sess, product_codes=["ES"])
                futs = [f for f in futs if getattr(f, "streamer_symbol", None)]
                act = [f for f in futs if getattr(f, "active_month", False)] or \
                    sorted([f for f in futs if f.expiration_date >= today], key=lambda f: f.expiration_date)[:1]
                if act:
                    self.es_sym = act[0].streamer_symbol
                    await s.subscribe_candle([self.es_sym], "1m", start_time=now_et() - timedelta(days=4),
                                             extended_trading_hours=True)
            except Exception as e:                          # noqa: BLE001
                self._err(e, "es-subscribe")
            self.state = f"recording 0DTE {e0:%m/%d} · 1DTE {e1:%m/%d} (seed) · {len(syms)} legs"

            tasks = [asyncio.create_task(c) for c in (
                self._l_tas(s, TimeAndSale), self._l_quote(s, Quote),
                self._l_greeks(s, Greeks), self._l_summary(s, Summary),
                self._l_trade(s, Trade), self._snap_loop(), self._flush_loop(),
                self._roll_watch(e0), self._token_watch(), self._l_candle(s),
                self._extra_loop(s, Quote, Greeks, Summary, Trade), self._stop_watch(),
                self._candle_seed(s, syms), self._c1m_sweep(s))]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            await asyncio.gather(*pending, return_exceptions=True)   # no "Task was destroyed" noise
            for d in done:
                if d.exception():
                    raise d.exception()
        self.state = "rolling to next expiry"

    async def _initial_spot(self, s, Trade, Summary) -> float:
        await s.subscribe(Trade, ["SPX"])
        await s.subscribe(Summary, ["SPX"])
        try:
            t = await asyncio.wait_for(s.get_event(Trade), 8)
            if _ok(_f(t.price)):
                with self.lock:
                    self.spx = (_f(t.price), int(time.time() * 1000))
                return _f(t.price)
        except asyncio.TimeoutError:
            pass
        try:
            sm = await asyncio.wait_for(s.get_event(Summary), 5)
            self.spx_prev_close = _f(sm.prev_day_close_price)
            return self.spx_prev_close
        except asyncio.TimeoutError:
            return float("nan")

    # ── on-demand expiries (weekly / monthly picked in the UI) ───────
    def request_expiry(self, exp: str):
        if exp and exp not in self._subscribed:
            self._wanted.add(exp)

    async def _extra_loop(self, s, Quote, Greeks, Summary, Trade):
        from datetime import date as _d
        while True:
            await asyncio.sleep(1.5)
            todo = [e for e in list(self._wanted) if e not in self._subscribed]
            for exp in todo:
                opts = self._chain.get(_d.fromisoformat(exp), [])
                if not opts:
                    self._wanted.discard(exp)
                    continue
                spot, _ = self.spot_now()
                ref = spot if _ok(spot) else self._spot_ref
                ks = sorted({float(o.strike_price) for o in opts})
                atm = min(range(len(ks)), key=lambda i: abs(ks[i] - ref))
                keep = set(ks[max(0, atm - EXTRA_STRIKES): atm + EXTRA_STRIKES + 1])
                new = {}
                for o in opts:
                    if float(o.strike_price) in keep:
                        cp = 1 if str(o.option_type.value).upper().startswith("C") else -1
                        new[o.streamer_symbol] = (exp, float(o.strike_price), cp)
                syms = list(new)
                with self.lock:
                    self.legs.update(new)
                for cls in (Quote, Greeks, Summary, Trade):
                    await s.subscribe(cls, syms)
                await self._tas_replay(s, syms)
                self._subscribed.add(exp)
                self._wanted.discard(exp)
                await self._candle_batches(s, syms)
                self._wanted.discard(exp)

    async def _l_candle(self, s):
        from tastytrade.dxfeed import Candle
        async for c in s.listen(Candle):
            if not c.time:
                continue
            base, _, spec = str(c.event_symbol).partition("{")
            if base == "SPX":
                if c.close is None:
                    continue
                o, h, l, cl = _f(c.open), _f(c.high), _f(c.low), _f(c.close)
                if _ok(cl):
                    with self.lock:
                        self.candles[int(c.time)] = (o, h, l, cl)
            elif base.startswith("/ES"):
                if c.close is not None and _ok(_f(c.close)):
                    with self.lock:
                        self.es1m[int(c.time)] = (_f(c.open), _f(c.high), _f(c.low), _f(c.close))
            elif base == "SPY":
                if c.close is not None and _ok(_f(c.close)):
                    v = _f(c.volume)
                    with self.lock:
                        self.spy1m[int(c.time)] = (_f(c.open), _f(c.high), _f(c.low), _f(c.close), v if v == v else 0.0)
            elif base == "VIX":
                if c.close is not None and _ok(_f(c.close)):
                    with self.lock:
                        self.vix5[int(c.time)] = _f(c.close)
            elif (spec.startswith("=m") or spec.startswith("=1m")) and base in self.legs:   # v0.18.1: dxfeed sends 1-min as "{=m}"
                v, bv, av = _f(c.volume), _f(c.bid_volume), _f(c.ask_volume)
                cl = _f(c.close)
                if v == v and v > 0:
                    with self.lock:
                        self.c1m[(base, int(c.time))] = (cl, v, bv if bv == bv else 0.0, av if av == av else 0.0)
            elif "=5m" in spec and base in self.legs:
                v, bv, av = _f(c.volume), _f(c.bid_volume), _f(c.ask_volume)
                if v == v and v > 0:
                    with self.lock:
                        self.c5[(base, int(c.time))] = (v, bv if bv == bv else 0.0, av if av == av else 0.0)

    def _session(self) -> str | None:
        return str(self.exps[0]) if self.exps else None

    async def _tas_replay(self, s, syms):
        """TimeAndSale with fromTime = seed start (raw FEED_SUBSCRIPTION, proven in Colab)."""
        ch = s._channels["TimeAndSale"]
        sess = self._session()
        for i in range(0, len(syms), 500):
            await s._websocket.send_json({"type": "FEED_SUBSCRIPTION", "channel": ch, "add": [
                {"type": "TimeAndSale", "symbol": x,
                 "fromTime": signs.seed_from_ms(self.legs[x][0], sess)} for x in syms[i:i + 500]]})
        self.seed["replay_last"] = time.time()

    async def _candle_seed(self, s, syms):
        await self._candle_batches(s, syms)
        await self._backfill_1m(s)
        # replay completion: quiet for REPLAY_QUIET_SEC after the last replayed print
        while time.time() - self.seed["replay_last"] < REPLAY_QUIET_SEC:
            await asyncio.sleep(1)
        self.seed.update(state="done", done_at=now_et().isoformat(timespec="seconds"))
        await asyncio.Event().wait()                         # keep the task alive (session ends on others)

    async def _backfill_1m(self, s):
        """L16d: after a (re)start the TimeAndSale replay keeps only the last 1,000 prints per contract, so
        busy strikes lose their morning. 1-minute option candles are uncapped: fetch them once for the 0DTE
        contracts within BACKFILL_EACH strikes of spot, from the session open (20:15 ET the evening before),
        in batches of CANDLE_BATCH (tastytrade: ≤100 candle subscriptions), then unsubscribe."""
        from datetime import datetime as _dt, timedelta as _td
        from . import session as S
        from .timeutil import ET
        try:
            # L20: right after a restart spot / legs may not be in yet — wait (up to 120 s) instead of silently
            # skipping (that left the morning to the 1,000-print replay and flooded the ridges after a reboot)
            t_w = time.time()
            spot, cand = float("nan"), []
            while time.time() - t_w < 120:
                if self.exps:
                    e0 = str(self.exps[0])
                    spot, _ = self.spot_now()
                    with self.lock:
                        cand = [(sym, k, cp) for sym, (ex, k, cp) in self.legs.items() if ex == e0]
                    if cand and spot == spot:
                        break
                await asyncio.sleep(3)
            if cand and not spot == spot:                  # still no spot: centre on the middle of the listed strikes
                ks_all = sorted({k for _, k, _ in cand})
                spot = float(ks_all[len(ks_all) // 2])
            if not cand:
                self.seed["backfill_1m"] = dict(contracts=0, rows=0, at=now_et().isoformat(timespec="seconds"),
                                                note="no 0DTE legs after 120 s — skipped")
                return
            ks = sorted({k for _, k, _ in cand}, key=lambda k: abs(k - spot))[:2 * BACKFILL_EACH + 1]
            syms = [sym for sym, k, _ in cand if k in ks]
            day = _dt.fromisoformat(e0).date()
            start = _dt.combine(day - _td(days=1), S.GTH_START, tzinfo=ET)       # GTH opens 20:15 ET the evening before
            async with self._candle_lock:
                await self._bf_batches(s, syms, start)
            n_have = len({k[0] for k in list(self.c1m)})
            if n_have < 0.5 * len(syms):                      # thin result: one retry for the missing contracts
                with self.lock:
                    got = {k[0] for k in self.c1m}
                miss = [x for x in syms if x not in got]
                await asyncio.sleep(20)
                async with self._candle_lock:
                    await self._bf_batches(s, miss, start)
            got = {k[0] for k in list(self.c1m)}
            self.seed["backfill_1m"] = dict(contracts=len(syms), filled=len(got & set(syms)), rows=len(self.c1m),
                                            at=now_et().isoformat(timespec="seconds"))
        except asyncio.CancelledError:
            raise
        except Exception as e:                            # noqa: BLE001
            self.seed["backfill_1m"] = dict(contracts=0, rows=len(self.c1m), note=f"error {type(e).__name__}")
            self._err(e, "backfill-1m")

    async def _c1m_sweep(self, s):
        """v0.18.0 (L20h, ridges after a reboot): the ridges' PAST comes from 1-minute option candles, never
        from the 1,000-print replay. Every SWEEP_SEC, for 0DTE AND 1DTE contracts within SWEEP_EACH strikes
        of spot: a contract with no candles yet is fetched from the session open (20:15 ET the evening
        before) — this rebuilds the whole session after any restart — and the others are topped up from
        the last 20 min. Prints then only cover the newest minutes (the live edge)."""
        from datetime import datetime as _dt, timedelta as _td
        from . import session as S
        from .timeutil import ET
        await asyncio.sleep(45)
        while True:
            try:
                if self.exps:
                    spot, _ = self.spot_now()
                    if not spot == spot:
                        spot = getattr(self, "_spot_ref", float("nan"))
                    ex2 = [str(e) for e in self.exps[:2]]
                    with self.lock:
                        cand = [(sym, ex, k) for sym, (ex, k, cp) in self.legs.items() if ex in ex2]
                        last = {}
                        for (sym, ts) in self.c1m.keys():
                            if ts > last.get(sym, 0):
                                last[sym] = ts
                    if cand and spot == spot:
                        ks = sorted({k for _, _, k in cand}, key=lambda k: abs(k - spot))[:2 * SWEEP_EACH + 1]
                        syms = [x for x, _, k in cand if k in ks]
                        day = _dt.fromisoformat(str(self.exps[0])).date()
                        open_ = _dt.combine(day - _td(days=1), S.GTH_START, tzinfo=ET)
                        new = [x for x in syms if x not in last]
                        old = [x for x in syms if x in last]
                        async with self._candle_lock:
                            if new:
                                await self._bf_batches(s, new, open_)
                            if old:
                                top = max(open_, now_et() - _td(seconds=SWEEP_SEC + 15 * 60))   # overlap: last 20 min
                                await self._bf_batches(s, old, top)
                        with self.lock:
                            have = {k[0] for k in self.c1m}
                        self.seed["sweep_1m"] = dict(contracts=len(syms), filled=len(have & set(syms)),
                                                     new=len(new), at=now_et().isoformat(timespec="seconds"))
            except asyncio.CancelledError:
                raise
            except Exception as e:                            # noqa: BLE001
                self._err(e, "sweep-1m")
            await asyncio.sleep(SWEEP_SEC)

    async def _bf_batches(self, s, syms, start):
        for i in range(0, len(syms), CANDLE_BATCH):
            b = syms[i:i + CANDLE_BATCH]
            await s.subscribe_candle(b, "1m", start_time=start, extended_trading_hours=True)
            t0, n_start = time.time(), len(self.c1m)
            n0, t_last = n_start, time.time()
            while time.time() - t0 < 90:                  # L20: wait ≤ 30 s for the first rows, then stop after
                await asyncio.sleep(1)                    # 5 s with nothing new (was: gave up after 6 s)
                n = len(self.c1m)
                if n != n0:
                    n0, t_last = n, time.time()
                elif n > n_start and time.time() - t_last > 5:
                    break
                elif n == n_start and time.time() - t0 > 30:
                    break
            for x in b:
                try:
                    await s.unsubscribe_candle(x, "1m", extended_trading_hours=True)
                except Exception:                         # noqa: BLE001
                    pass

    def _oi_cov(self) -> str:
        """L10h: how many 0DTE contracts have open interest (Tetris needs prior-close OI every morning;
        Summary OI arrives with the session subscription at the 16:15 roll and refreshes when OCC publishes)."""
        try:
            e0 = str(self.exps[0]) if self.exps else None
            with self.lock:
                legs = [s_ for s_, v in self.legs.items() if v[0] == e0]
                n = sum(1 for s_ in legs if (self.oi.get(s_) or 0) > 0)
            return f"{n}/{len(legs)}"
        except Exception:                                   # noqa: BLE001
            return "?"

    def opt1m_df(self) -> pd.DataFrame:
        """1-minute option candles from the backfill: m (naive ET), sym, strike, cp, size, prem, net, close."""
        with self.lock:
            rows = [(k[0], k[1]) + v for k, v in self.c1m.items()]
            legs = dict(self.legs)
        if not rows:
            return pd.DataFrame(columns=["m", "sym", "strike", "cp", "size", "prem", "net", "close", "ts_ms", "bidv", "askv"])
        d = pd.DataFrame(rows, columns=["sym", "ts_ms", "close", "size", "bidv", "askv"])
        d["strike"] = d["sym"].map(lambda x: legs.get(x, (None, float("nan"), 0))[1])
        d["cp"] = d["sym"].map(lambda x: legs.get(x, (None, float("nan"), 0))[2])
        from .timeutil import ET
        d["m"] = pd.to_datetime(d["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
        d["prem"] = d["size"] * d["close"] * 100.0
        d["net"] = d["askv"] - d["bidv"]
        return d[["m", "sym", "strike", "cp", "size", "prem", "net", "close", "ts_ms", "bidv", "askv"]]

    async def _candle_batches(self, s, syms):
        """5-min candles carry bidVolume/askVolume (uncapped): the signed volume the
        1,000-print replay cannot reach. Batches of CANDLE_BATCH (tastytrade cap 100)."""
        from datetime import datetime as _dt
        async with self._candle_lock:
          try:
            sess = self._session()
            start = _dt.fromtimestamp(min(signs.seed_from_ms(self.legs[x][0], sess) for x in syms) / 1000)
            for i in range(0, len(syms), CANDLE_BATCH):
                b = syms[i:i + CANDLE_BATCH]
                await s.subscribe_candle(b, "5m", start_time=start, extended_trading_hours=True)
                t0, n0 = time.time(), len(self.c5)
                while time.time() - t0 < 20:
                    await asyncio.sleep(2)
                    if len(self.c5) == n0 and time.time() - t0 > 4:
                        break
                    n0 = len(self.c5)
                for x in b:
                    await s.unsubscribe_candle(x, "5m", extended_trading_hours=True)
                self.seed["candle_batches"] += 1
            self.seed["candle_legs"] = len({k[0] for k in self.c5})
          except asyncio.CancelledError:
            raise
          except Exception as e:                            # noqa: BLE001
            self._err(e, "candle-seed")

    def _candle_spot(self, ms: int) -> float:
        """SPX close of the 1-minute bar containing ms (replayed prints)."""
        c = self.candles.get(ms - ms % 60_000)
        return c[3] if c else float("nan")

    def es_df(self) -> pd.DataFrame:
        with self.lock:
            rows = [(k,) + tuple(v) for k, v in sorted(self.es1m.items())]
        return pd.DataFrame(rows, columns=["ts_ms", "open", "high", "low", "close"])

    def spy_df(self) -> pd.DataFrame:
        with self.lock:
            rows = [(k,) + tuple(v) for k, v in sorted(self.spy1m.items())]
        return pd.DataFrame(rows, columns=["ts_ms", "open", "high", "low", "close", "volume"])

    def vix_df(self) -> pd.DataFrame:
        with self.lock:
            rows = sorted(self.vix5.items())
        return pd.DataFrame(rows, columns=["ts_ms", "close"])

    def candles_df(self) -> pd.DataFrame:
        with self.lock:
            rows = [{"ts_ms": k, "open": v[0], "high": v[1], "low": v[2], "close": v[3]}
                    for k, v in self.candles.items()]
        return pd.DataFrame(rows).sort_values("ts_ms") if rows else pd.DataFrame()

    async def _token_watch(self):
        """End the session cleanly every RECONNECT_HOURS so the outer loop opens a
        new one with a fresh access token and DXLink quote token (expires 24 h)."""
        await asyncio.sleep(RECONNECT_HOURS * 3600)
        self.state = "refreshing tokens"
        self.token_refreshes += 1

    async def _roll_watch(self, e0: date):
        while True:
            n = now_et()
            if n.date() > e0 or (n.date() == e0 and n.time() >= ROLL_TIME):
                return
            await asyncio.sleep(30)

    # ── listeners ────────────────────────────────────────────────────
    async def _l_tas(self, s, TimeAndSale):
        async for e in s.listen(TimeAndSale):
            sym = e.event_symbol
            meta = self.legs.get(sym)
            if meta is None:
                continue
            flags = int(e.event_flags or 0)
            if flags & 0x02:                    # REMOVE_EVENT marker: no trade
                continue
            key = hash((sym, int(e.index or 0), str(e.type)))
            if key in self._seen:
                continue
            ms = int(e.time or e.event_time or time.time() * 1000)
            p, b, a = _f(e.price), _f(e.bid_price), _f(e.ask_price)
            qsrc = 0
            if not (_ok(b) and _ok(a) and a >= b):
                q = self.quotes.get(sym)
                if q and abs(ms - q[2]) <= QUOTE_FALLBACK_SEC * 1000:
                    b, a, qsrc = q[0], q[1], 1
                else:
                    qsrc = 2
            bk = bucket(p, b, a)
            side = str(e.aggressor_side or "").split(".")[-1].upper()
            replay = ms < self._connect_ms - 5000
            g = None if replay else self.greeks.get(sym)       # live greeks are not the print's greeks
            if replay:
                spot, ssrc = self._candle_spot(ms), "candle1m"
            else:
                spot, ssrc = self.spot_now()
            row = {"ts_ms": ms, "seq": int(e.sequence or 0), "sym": sym, "exp": meta[0],
                   "strike": meta[1], "cp": meta[2], "idx": int(e.index or 0),
                   "ev_type": str(e.type), "px": p, "size": int(e.size or 0),
                   "bid": b, "ask": a, "quote_src": qsrc, "bucket": bk,
                   "aggr": aggr(bk, p, b, a, 1.0, side), "aggr_side": side,
                   "src": "replay" if replay else "live",
                   "spread_leg": bool(e.spread_leg), "eth": bool(e.extended_trading_hours),
                   "valid": bool(e.valid_tick) if e.valid_tick is not None else True,
                   "exch": str(e.exchange_code or ""), "cond": str(e.exchange_sale_conditions or ""),
                   "spot": spot, "spot_src": ssrc,
                   "iv": g[0] if g else float("nan"), "delta": g[1] if g else float("nan"),
                   "gamma": g[2] if g else float("nan"),
                   "greeks_age_s": (ms - g[5]) / 1000 if g else float("nan")}
            with self.lock:
                self._seen.add(key)
                self._pbuf.append(row)
                if row["src"] == "replay":
                    self.seed["replay_n"] += 1
                    self.seed["replay_last"] = time.time()
                if len(self._pbuf) >= COMPACT_EVERY:
                    self._compact()
                self.last_event_ms = int(time.time() * 1000)

    async def _l_quote(self, s, Quote):
        async for e in s.listen(Quote):
            self.quotes[e.event_symbol] = (_f(e.bid_price), _f(e.ask_price), int(time.time() * 1000))
            self.last_event_ms = int(time.time() * 1000)

    async def _l_greeks(self, s, Greeks):
        async for e in s.listen(Greeks):
            self.greeks[e.event_symbol] = (_f(e.volatility), _f(e.delta), _f(e.gamma),
                                           _f(e.theta), _f(e.vega), int(time.time() * 1000))

    async def _l_summary(self, s, Summary):
        async for e in s.listen(Summary):
            if e.event_symbol == "SPX":
                self.spx_prev_close = _f(e.prev_day_close_price)
            elif e.open_interest is not None:
                self.oi[e.event_symbol] = _f(e.open_interest)

    async def _l_trade(self, s, Trade):
        async for e in s.listen(Trade):
            if e.event_symbol == "SPX":
                if _ok(_f(e.price)):
                    # stamp with the TRADE's time, not receipt time: on connect DXLink re-sends the last
                    # trade (Friday's close overnight), which must count as stale, not live
                    tms = int(e.time or 0)
                    self.spx = (_f(e.price), tms if tms > 0 else int(time.time() * 1000))
            elif e.day_volume is not None:
                self.dayvol[e.event_symbol] = _f(e.day_volume)

    # ── spot ─────────────────────────────────────────────────────────
    def synthetic_spot(self, ref: float | None = None) -> float:
        if not self.exps:
            return float("nan")
        e0 = str(self.exps[0])
        calls, puts = {}, {}
        for sym, (ex, k, cp) in self.legs.items():
            if ex != e0:
                continue
            q = self.quotes.get(sym)
            if not q or not (_ok(q[0]) and _ok(q[1])):
                continue
            (calls if cp == 1 else puts)[k] = (q[0] + q[1]) / 2
        ks = sorted(set(calls) & set(puts))
        if not ks:
            return float("nan")
        ref = ref if (ref and _ok(ref)) else ks[len(ks) // 2]
        near = sorted(ks, key=lambda k: abs(k - ref))[:3]
        return sum(k + calls[k] - puts[k] for k in near) / len(near)

    def spot_now(self) -> tuple[float, str]:
        px, ms = self.spx
        if _ok(px) and time.time() * 1000 - ms < 60_000:
            return px, "spx"
        syn = self.synthetic_spot(px if _ok(px) else None)
        if _ok(syn):
            return syn, "synth"
        return (px, "spx_stale") if _ok(px) else (self.spx_prev_close, "prev_close")

    # ── snapshots ────────────────────────────────────────────────────
    def live_chain(self, exp: str | None = None) -> pd.DataFrame:
        """Current state of every recorded leg (no waiting for a snapshot)."""
        spot, ssrc = self.spot_now()
        ts = int(time.time() * 1000)
        rows = []
        with self.lock:
            for sym, (ex, k, cp) in self.legs.items():
                if exp and ex != exp:
                    continue
                q = self.quotes.get(sym, (float("nan"), float("nan"), 0))
                g = self.greeks.get(sym, (float("nan"),) * 5 + (0,))
                rows.append({"ts_ms": ts, "exp": ex, "sym": sym, "strike": k, "cp": cp,
                             "bid": q[0], "ask": q[1], "iv": g[0], "delta": g[1], "gamma": g[2],
                             "theta": g[3], "vega": g[4], "oi": self.oi.get(sym, float("nan")),
                             "day_volume": self.dayvol.get(sym, float("nan")),
                             "spot": spot, "spot_src": ssrc})
        return pd.DataFrame(rows)

    async def _snap_loop(self):
        last_chain = 0.0
        while True:
            await asyncio.sleep(SPOT_SEC)
            live = recording_window()
            spot, ssrc = self.spot_now()
            if live:
                with self.lock:
                    self.spot_rows.append({"ts_ms": int(time.time() * 1000), "spx": self.spx[0],
                                           "spot": spot, "spot_src": ssrc})
            # chain snapshots always: every 60 s in the trading window, every 5 min when closed
            if time.time() - last_chain >= (SNAP_SEC if live else 300):
                last_chain = time.time()
                with self.lock:
                    day = self.oi_log.setdefault(str(now_et().date()), {})
                    day.update({k: v for k, v in self.oi.items() if v == v})
                    for k in sorted(self.oi_log)[:-6]:
                        self.oi_log.pop(k, None)
                df = self.live_chain()
                try:
                    ds = {}
                    for ex in {v[0] for v in list(self.legs.values())}:
                        t = self.dsign_table(ex)
                        ds.update(dict(zip(t["sym"], t["dsign"])))
                    df["dsign"] = df["sym"].map(ds)
                except Exception as e:                      # noqa: BLE001
                    self._err(e, "snapshot-dsign")
                with self.lock:
                    self.chain_rows.append(df)
                self._mem_guard()

    def _mem_guard(self):
        """M1: trim freed heap every snapshot; thin old snapshots above the soft limit."""
        from . import mem
        mem.trim(0)
        r = mem.rss_mb()
        self.rss_mb = r
        self.rss_peak = max(getattr(self, "rss_peak", 0.0), r if r == r else 0.0)
        if r == r and r > mem.HARD_MB and self.exps:     # v0.18.0: also fold old prints of later expiries
            with self.lock:
                df = self._all_prints()
                f, saved = mem.fold_prints(df, str(self.exps[0]), int(time.time() * 1000) - 2 * 3600_000)
                if saved > 0:
                    f = _concat_cat([f], self.PCAT)
                    self._pchunks, self._pbuf = [f], []
                    self._pcache = (self.n_prints, f)
                    self._pexp = {}
                    self._fl["prints"] = min(self._fl.get("prints", 0), len(f))
            mem.trim(0)
            self._err(RuntimeError(f"memory {r:.0f} MB > {mem.HARD_MB} MB: folded {saved:,} old later-expiry prints "
                                   f"→ {mem.rss_mb():.0f} MB"), "mem-guard")
        if r == r and r > mem.SOFT_MB:
            with self.lock:
                n = mem.thin_snapshots(self.chain_rows)
            mem.trim(0)
            self.mem_events = getattr(self, "mem_events", 0) + 1
            self._err(RuntimeError(f"memory {r:.0f} MB > {mem.SOFT_MB} MB: thinned {n:,} old snapshot rows "
                                   f"→ {mem.rss_mb():.0f} MB"), "mem-guard")

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(FLUSH_MIN * 60)
            try:
                await asyncio.to_thread(self.flush)
            except Exception as e:                          # noqa: BLE001
                self._err(e, "flush")

    # ── persistence ──────────────────────────────────────────────────
    def flush(self):
        if not self.repo or not self.exps:
            return
        exp = str(self.exps[0])
        stamp = now_et().strftime("%Y%m%d-%H%M%S") + "-" + self.cid
        allp = self._all_prints()
        with self.lock:
            batches = {"prints": allp.iloc[self._fl["prints"]:],
                       "chain": self.chain_rows.since(self._fl["chain"]),
                       "spot": self.spot_rows[self._fl["spot"]:]}
            ends = {"prints": len(allp), "chain": len(self.chain_rows),
                    "spot": len(self.spot_rows)}
        try:
            for kind, rows in batches.items():
                if len(rows):
                    self.repo.put_parquet(f"sessions/{exp}/{kind}/part-{stamp}.parquet",
                                          pd.DataFrame(rows), f"{exp} {kind} {stamp}")
                    self._fl[kind] = ends[kind]
            with self.lock:
                gaps = list(self.gaps)
                oi = [{"sym": k, "oi": v} for k, v in self.oi.items()]
            self.repo.put_json(f"sessions/{exp}/meta.json",
                               {"expiries": [str(e) for e in self.exps], "legs": len(self.legs),
                "subscribed_expiries": sorted(self._subscribed), "listed_expiries": len(self.all_exps),
                "candles": len(self.candles),
                                "rows": ends, "gaps": gaps, "updated": now_et().isoformat()},
                               f"{exp} meta {stamp}")
            if oi:
                self.repo.put_parquet(f"sessions/{exp}/oi.parquet", pd.DataFrame(oi),
                                      f"{exp} oi {stamp}")
            self.last_flush = now_et()
            self.last_flush_error = None
            self.repo.put_json("health.json", self.status(), f"health {stamp}")
            with self.lock:
                ol = {k: dict(v) for k, v in self.oi_log.items()}
            self.repo.put_json("oi_log.json", ol, f"oi log {stamp}")
        except Exception as e:                              # noqa: BLE001
            self.last_flush_error = f"{type(e).__name__}: {e}"
            self._err(e, "flush")

    def _reload(self, exp: str):
        """Load today's already-flushed rows so a restart keeps the day."""
        if not self.repo:
            self.loaded_exp = exp
            return
        try:
            p = self.repo.read_parquet_dir(f"sessions/{exp}/prints")
            c = self.repo.read_parquet_dir(f"sessions/{exp}/chain")
            sp = self.repo.read_parquet_dir(f"sessions/{exp}/spot")
            meta = self.repo.get_json(f"sessions/{exp}/meta.json") or {}
            with self.lock:
                if len(p):
                    p = p.drop_duplicates(subset=["sym", "idx", "ev_type"])
                    self._pchunks, self._pbuf = [p], []
                    self._seen = {hash((a, int(b), str(c))) for a, b, c in
                                  zip(p["sym"], p["idx"], p["ev_type"])}
                self.chain_rows = Frames([c] if len(c) else [])
                self.spot_rows = sp.to_dict("records") if len(sp) else []
                self.gaps = meta.get("gaps", [])
                self._fl = {"prints": self.n_prints, "chain": len(self.chain_rows),
                            "spot": len(self.spot_rows), "gaps": len(self.gaps)}
                if len(p) or self.spot_rows:          # restart inside a session = a gap
                    last = max([r["ts_ms"] for r in self.spot_rows[-1:]] +
                               ([int(p["ts_ms"].max())] if len(p) else []))
                    self.gaps.append({"start_ms": int(last), "end_ms": None,
                                      "reason": "app restart"})
            self.loaded_exp = exp
        except Exception as e:                              # noqa: BLE001
            self._err(e, "reload")
            self.loaded_exp = exp

    # ── prints storage ───────────────────────────────────────────────
    def _compact(self):
        """Move buffered dict rows into a compact DataFrame chunk (call under lock)."""
        if not self._pbuf:
            return
        df = pd.DataFrame(self._pbuf)
        for c in ("sym", "exp", "aggr_side", "exch", "cond", "spot_src", "ev_type", "src"):
            if c in df:
                df[c] = df[c].astype("category")
        self._pchunks.append(df)
        self._pbuf = []

    @property
    def n_prints(self) -> int:
        return sum(len(c) for c in self._pchunks) + len(self._pbuf)

    PCAT = ("sym", "exp", "aggr_side", "exch", "cond", "spot_src", "ev_type", "src")

    def _all_prints(self) -> pd.DataFrame:
        """All prints as ONE compact frame (v0.18.0 L26): text columns stay categorical
        (≈40 % of the str size), chunks are merged with unified categories, and the merged
        frame IS the store (no second copy). Cached on the print count."""
        with self.lock:
            self._compact()
            n = self.n_prints
            if self._pcache[0] == n:
                return self._pcache[1]
            df = _concat_cat(self._pchunks, self.PCAT)
            self._pchunks = [df] if len(df) else []
            self._pcache = (n, df)
            self._pexp = {}                               # per-expiry slices for this count
            return df

    def candles5_df(self) -> pd.DataFrame:
        with self.lock:
            rows = [(k[0], k[1], v[0], v[1], v[2]) for k, v in self.c5.items()]
        return pd.DataFrame(rows, columns=["sym", "ts_ms", "vol", "bidv", "askv"])

    def dsign_table(self, exp: str, single_leg: bool = False) -> pd.DataFrame:
        """Flow-signed dealer table for exp (seed + live), cached on data counts."""
        key = (exp, single_leg, self.n_prints, len(self.c5), len(self.legs))
        c = getattr(self, "_dcache", {})
        if key in c:
            return c[key]
        with self.lock:
            legs = dict(self.legs)
        t = signs.dsign_table(self._all_prints(), self.candles5_df(), legs, exp,
                              int(time.time() * 1000), single_leg, self._session())
        self._dcache = {key: t}
        return t

    # ── read API for the tabs ────────────────────────────────────────
    def status(self) -> dict:
        age = (time.time() * 1000 - self.last_event_ms) / 1000 if self.last_event_ms else None
        return {"version": VERSION, "state": self.state, "container": self.cid,
                "alive": bool(self.thread and self.thread.is_alive()),
                "expiries": [str(e) for e in self.exps], "legs": len(self.legs),
                "subscribed_expiries": sorted(self._subscribed), "listed_expiries": len(self.all_exps),
                "candles": len(self.candles),
                "prints": self.n_prints, "chain_rows": len(self.chain_rows),
                "seed": dict(self.seed, candles5=len(self.c5)),
                "spot_rows": len(self.spot_rows), "quotes": len(self.quotes),
                "greeks": len(self.greeks), "oi": len(self.oi),
                "last_event_age_s": age,
                "last_flush": self.last_flush.isoformat(timespec="seconds") if self.last_flush else None,
                "flush_error": self.last_flush_error, "repo": self.repo_kind,
                "uptime_min": round((time.time() - self.started_at) / 60, 1),
                "token_refreshes": self.token_refreshes, "auto_recovered": self.recovered,
                "errors": len(self.errors),
                "oi_0dte_legs": self._oi_cov(),
                "rss_mb": round(getattr(self, "rss_mb", 0.0) or 0.0), "rss_peak_mb": round(getattr(self, "rss_peak", 0.0)),
                "mem_thins": getattr(self, "mem_events", 0)}

    def prints_df(self, exp: str | None = None) -> pd.DataFrame:
        """Prints (all or one expiry). One cached slice per expiry per print count, shared by
        every tab and every browser session — no per-tab copies (v0.18.0 L26)."""
        df = self._all_prints()
        if not exp or not len(df):
            return df
        with self.lock:
            c = getattr(self, "_pexp", None)
            if c is None or self._pcache[1] is not df:
                c = self._pexp = {}
            if exp not in c:
                c[exp] = df[df["exp"] == exp].reset_index(drop=True)
            return c[exp]

    def spot_df(self) -> pd.DataFrame:
        with self.lock:
            return pd.DataFrame(self.spot_rows)

    def chain_df(self) -> pd.DataFrame:
        with self.lock:
            return self.chain_rows.df()
