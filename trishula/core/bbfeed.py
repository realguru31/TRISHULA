"""v0.36.0 — slim tastytrade feed for the standalone SPX BB app (spxbb.py).

Only what SPX BB needs, on its own DXLink session (TRISHULA's recorder no longer quotes the far strikes):
  · SPX trade + summary (spot, prev close)
  · Quote (bid / ask) on EVERY SPXW (PM) strike of the two SPX BB expiries
  · SPX 1-minute candles (last 4 days) for the charts
Expiries follow SPX BB's own 21:00 ET roll: before 21:00 today + next, from 21:00 the next two.
The session reconnects at 21:00 (roll) and every RECONNECT_HOURS (fresh tokens). Same interface the Tracker and the
tab use on the full Recorder: quotes, bb_meta, legs, exps, all_exps, spot_now(), candles_df(), state, errors.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import threading
import time
import traceback
from collections import deque

import pandas as pd

from . import expiry as EX
from .timeutil import now_et
from .version import VERSION

BB_ROLL = dt.time(21, 0)
RECONNECT_HOURS = 6
SUB_BATCH = 500


def _f(x) -> float:
    try:
        return float(x) if x is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _ok(v: float) -> bool:
    return v == v and v > 0


class BBFeed:
    def __init__(self, client_secret: str, refresh_token: str):
        self.cs, self.rt = client_secret, refresh_token
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.state = "starting"
        self.errors: deque = deque(maxlen=40)
        self.version = VERSION
        self.last_event_ms = 0
        self._stop = False
        self.all_exps: list[str] = []
        self.exps: list[dt.date] = []
        self.quotes: dict[str, tuple[float, float, int]] = {}
        self.bb_meta: dict[str, tuple[str, float, int]] = {}
        self.legs = self.bb_meta                  # synthetic spot reads legs
        self.spx = (float("nan"), 0)
        self.spx_prev_close = float("nan")
        self.candles: dict[int, tuple] = {}
        # v0.44.0: 1-minute TRADE candles for your sold strikes (MAE) — tracker asks via want_candle()
        self.ocandles: dict[str, dict[int, tuple]] = {}
        self._want: dict[str, int] = {}            # streamer symbol → from (epoch ms)
        self._subbed: set = set()

    def want_candle(self, sym: str, from_ms: int):
        if sym and (sym not in self._want or from_ms < self._want[sym]):
            self._want[sym] = int(from_ms)

    def _err(self, e: Exception, where: str):
        self.errors.append({"t": now_et().isoformat(timespec="seconds"), "where": where,
                            "err": f"{type(e).__name__}: {e}", "tb": traceback.format_exc(limit=3)})

    # ── thread ───────────────────────────────────────────────────────
    def start(self):
        if self._stop or (self.thread and self.thread.is_alive()):
            return self
        self.thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True,
                                       name=f"spxbb-feed-{VERSION}")
        self.thread.start()
        return self

    def stop(self):
        self._stop = True
        self.state = "stopped (replaced by newer version)"

    async def _main(self):
        backoff = 1
        while not self._stop:
            t0 = time.time()
            try:
                await self._run_session()
                backoff = 1
            except Exception as e:                          # noqa: BLE001
                self._err(e, "session")
                self.state = f"reconnecting ({type(e).__name__})"
            if self._stop:
                break
            if time.time() - t0 > 300:
                backoff = 1
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2)

    @staticmethod
    def _base(n: dt.datetime) -> dt.date:
        return n.date() if n.time() < BB_ROLL else n.date() + dt.timedelta(days=1)

    async def _run_session(self):
        from tastytrade import DXLinkStreamer, Session
        from tastytrade.dxfeed import Candle, Quote, Summary, Trade
        from tastytrade.instruments import get_option_chain

        self.state = "authenticating"
        sess = Session(self.cs, self.rt)
        self.state = "loading chain"
        chain_all = await get_option_chain(sess, "SPX")
        EX.register(chain_all)
        chain = {d: [o for o in opts if EX.is_pm(o)] for d, opts in chain_all.items()}
        chain = {d: v for d, v in chain.items() if v}
        n = now_et().replace(tzinfo=None)
        base = self._base(n)
        exps = sorted(d for d in chain if d >= base)[:2]
        if not exps:
            raise RuntimeError("no SPXW expiries in the chain")
        meta = {}
        for ex in exps:
            for o in chain[ex]:
                cp = 1 if str(o.option_type.value).upper().startswith("C") else -1
                meta[o.streamer_symbol] = (str(ex), float(o.strike_price), cp)
        with self.lock:
            self.all_exps = [str(d) for d in sorted(d for d in chain if d >= n.date())]
            self.exps = exps
            self.quotes = {k: v for k, v in self.quotes.items() if k in meta}
            self.bb_meta = meta
            self.legs = meta

        self._subbed = set()
        async with DXLinkStreamer(sess) as s:
            self.state = "subscribing"
            await s.subscribe(Trade, ["SPX"])
            await s.subscribe(Summary, ["SPX"])
            syms = list(meta)
            for i in range(0, len(syms), SUB_BATCH):
                await s.subscribe(Quote, syms[i:i + SUB_BATCH])
            try:
                await s.subscribe_candle(["SPX"], "1m", start_time=now_et() - dt.timedelta(days=4))
            except Exception as e:                          # noqa: BLE001
                self._err(e, "candle-subscribe")
            self.state = (f"live · {' / '.join(f'{d:%a %d %b}' for d in exps)} · {len(syms):,} strikes")
            tasks = [asyncio.create_task(c) for c in (
                self._l_quote(s, Quote), self._l_trade(s, Trade), self._l_summary(s, Summary),
                self._l_candle(s, Candle), self._roll_watch(base), self._token_watch(), self._stop_watch(),
                self._want_watch(s))]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for d in done:
                if d.exception():
                    raise d.exception()
        self.state = "reconnecting (roll / token refresh)"

    # ── watchers ─────────────────────────────────────────────────────
    async def _roll_watch(self, base: dt.date):
        while self._base(now_et().replace(tzinfo=None)) == base:
            await asyncio.sleep(20)

    async def _token_watch(self):
        await asyncio.sleep(RECONNECT_HOURS * 3600)

    async def _stop_watch(self):
        while not self._stop:
            await asyncio.sleep(1)

    async def _want_watch(self, s):
        """Subscribe 1-minute candles for any sold strike the tracker asked for (history from its from_ms)."""
        while True:
            for sym, fm in list(self._want.items()):
                if sym in self._subbed:
                    continue
                self._subbed.add(sym)
                try:
                    st_ = dt.datetime.fromtimestamp(fm / 1000, tz=now_et().tzinfo)
                    await s.subscribe_candle([sym], "1m", start_time=st_)
                except Exception as e:                      # noqa: BLE001
                    self._err(e, f"candle {sym}")
            await asyncio.sleep(2)

    # ── listeners ────────────────────────────────────────────────────
    async def _l_quote(self, s, Quote):
        async for e in s.listen(Quote):
            ms = int(time.time() * 1000)
            self.quotes[e.event_symbol] = (_f(e.bid_price), _f(e.ask_price), ms)
            self.last_event_ms = ms

    async def _l_trade(self, s, Trade):
        async for e in s.listen(Trade):
            if e.event_symbol == "SPX" and _ok(_f(e.price)):
                tms = int(e.time or 0)                     # trade time: a replayed old print counts as stale
                self.spx = (_f(e.price), tms if tms > 0 else int(time.time() * 1000))

    async def _l_summary(self, s, Summary):
        async for e in s.listen(Summary):
            if e.event_symbol == "SPX":
                self.spx_prev_close = _f(e.prev_day_close_price)

    async def _l_candle(self, s, Candle):
        async for c in s.listen(Candle):
            if not c.time or c.close is None:
                continue
            base = str(c.event_symbol).partition("{")[0]
            if base != "SPX":
                if base in self._want:
                    hi = _f(c.high)
                    if _ok(hi):
                        self.ocandles.setdefault(base, {})[int(c.time)] = (hi, _f(c.close))
                continue
            cl = _f(c.close)
            if _ok(cl):
                with self.lock:
                    self.candles[int(c.time)] = (_f(c.open), _f(c.high), _f(c.low), cl)
                    if len(self.candles) > 8000:
                        for k in sorted(self.candles)[:len(self.candles) - 8000]:
                            self.candles.pop(k, None)

    # ── spot ─────────────────────────────────────────────────────────
    def synthetic_spot(self, ref: float | None = None) -> float:
        """Put-call parity on the first NOT-expired expiry (today's 0DTE is dead after 16:00)."""
        n = now_et().replace(tzinfo=None)
        live = [d for d in self.exps if n < EX.end(str(d))]
        if not live:
            return float("nan")
        e0 = str(live[0])
        calls, puts = {}, {}
        for sym, (ex, k, cp) in list(self.bb_meta.items()):
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

    def candles_df(self) -> pd.DataFrame:
        with self.lock:
            rows = [{"ts_ms": k, "open": v[0], "high": v[1], "low": v[2], "close": v[3]}
                    for k, v in self.candles.items()]
        return pd.DataFrame(rows).sort_values("ts_ms") if rows else pd.DataFrame()
