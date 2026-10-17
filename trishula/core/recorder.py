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

from .classify import aggr, bucket
from .store import DataRepo, LocalRepo
from .timeutil import now_et, recording_window
from .version import VERSION

FLUSH_MIN = 5
SNAP_SEC = 60          # chain snapshot cadence
SPOT_SEC = 5           # spot row cadence
STRIKES_EACH_SIDE = 40
STRIKE_STEP = 5.0
QUOTE_FALLBACK_SEC = 2.0
ROLL_TIME = dtime(16, 15)


def _f(x) -> float:
    try:
        v = float(x)
        return v if not math.isnan(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _ok(v: float) -> bool:
    return v == v and v > 0


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
            self.prints: list[dict] = []
            self.chain_rows: list[dict] = []
            self.spot_rows: list[dict] = []
            self.gaps: list[dict] = []
            self._seen: set = set()
            self._fl = {"prints": 0, "chain": 0, "spot": 0, "gaps": 0}
            self.loaded_exp: str | None = None

    def _err(self, e: Exception, where: str):
        self.errors.append({"t": now_et().isoformat(timespec="seconds"), "v": VERSION, "where": where,
                            "err": f"{type(e).__name__}: {e}",
                            "tb": traceback.format_exc(limit=3)})

    # ── thread ───────────────────────────────────────────────────────
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=lambda: asyncio.run(self._main()),
                                       daemon=True, name="trishula-recorder")
        self.thread.start()

    async def _main(self):
        backoff = 1
        while True:
            t0 = time.time()
            try:
                await self._run_session()
            except Exception as e:                          # noqa: BLE001
                self._err(e, "session")
                self.state = f"reconnecting ({type(e).__name__})"
                with self.lock:
                    self.gaps.append({"start_ms": self.last_event_ms or int(time.time() * 1000),
                                      "end_ms": None, "reason": f"{type(e).__name__}: {e}"[:200]})
            try:
                await asyncio.to_thread(self.flush)
            except Exception as e:                          # noqa: BLE001
                self._err(e, "flush-after-session")
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
            await s.subscribe(TimeAndSale, syms)
            await s.subscribe(Quote, syms)
            await s.subscribe(Greeks, syms)
            await s.subscribe(Summary, syms)
            await s.subscribe(Trade, syms)
            self.state = f"recording {e0} + {e1} · {len(syms)} legs"

            tasks = [asyncio.create_task(c) for c in (
                self._l_tas(s, TimeAndSale), self._l_quote(s, Quote),
                self._l_greeks(s, Greeks), self._l_summary(s, Summary),
                self._l_trade(s, Trade), self._snap_loop(), self._flush_loop(),
                self._roll_watch(e0))]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
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
            key = (sym, int(e.index or 0), str(e.type))
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
            g = self.greeks.get(sym)
            spot, ssrc = self.spot_now()
            row = {"ts_ms": ms, "seq": int(e.sequence or 0), "sym": sym, "exp": meta[0],
                   "strike": meta[1], "cp": meta[2], "idx": int(e.index or 0),
                   "ev_type": str(e.type), "px": p, "size": int(e.size or 0),
                   "bid": b, "ask": a, "quote_src": qsrc, "bucket": bk,
                   "aggr": aggr(bk, p, b, a, 0.0, side), "aggr_side": side,
                   "spread_leg": bool(e.spread_leg), "eth": bool(e.extended_trading_hours),
                   "valid": bool(e.valid_tick) if e.valid_tick is not None else True,
                   "exch": str(e.exchange_code or ""), "cond": str(e.exchange_sale_conditions or ""),
                   "spot": spot, "spot_src": ssrc,
                   "iv": g[0] if g else float("nan"), "delta": g[1] if g else float("nan"),
                   "gamma": g[2] if g else float("nan"),
                   "greeks_age_s": (ms - g[5]) / 1000 if g else float("nan")}
            with self.lock:
                self._seen.add(key)
                self.prints.append(row)
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
                    self.spx = (_f(e.price), int(time.time() * 1000))
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
                df = self.live_chain()
                with self.lock:
                    self.chain_rows.extend(df.to_dict("records"))

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
        with self.lock:
            batches = {"prints": self.prints[self._fl["prints"]:],
                       "chain": self.chain_rows[self._fl["chain"]:],
                       "spot": self.spot_rows[self._fl["spot"]:]}
            ends = {"prints": len(self.prints), "chain": len(self.chain_rows),
                    "spot": len(self.spot_rows)}
        try:
            for kind, rows in batches.items():
                if rows:
                    self.repo.put_parquet(f"sessions/{exp}/{kind}/part-{stamp}.parquet",
                                          pd.DataFrame(rows), f"{exp} {kind} {stamp}")
                    self._fl[kind] = ends[kind]
            with self.lock:
                gaps = list(self.gaps)
                oi = [{"sym": k, "oi": v} for k, v in self.oi.items()]
            self.repo.put_json(f"sessions/{exp}/meta.json",
                               {"expiries": [str(e) for e in self.exps], "legs": len(self.legs),
                                "rows": ends, "gaps": gaps, "updated": now_et().isoformat()},
                               f"{exp} meta {stamp}")
            if oi:
                self.repo.put_parquet(f"sessions/{exp}/oi.parquet", pd.DataFrame(oi),
                                      f"{exp} oi {stamp}")
            self.last_flush = now_et()
            self.last_flush_error = None
            self.repo.put_json("health.json", self.status(), f"health {stamp}")
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
                    self.prints = p.to_dict("records")
                    self._seen = set(zip(p["sym"], p["idx"].astype(int), p["ev_type"].astype(str)))
                self.chain_rows = c.to_dict("records") if len(c) else []
                self.spot_rows = sp.to_dict("records") if len(sp) else []
                self.gaps = meta.get("gaps", [])
                self._fl = {"prints": len(self.prints), "chain": len(self.chain_rows),
                            "spot": len(self.spot_rows), "gaps": len(self.gaps)}
                if self.prints or self.spot_rows:     # restart inside a session = a gap
                    last = max([r["ts_ms"] for r in self.spot_rows[-1:]] +
                               [r["ts_ms"] for r in self.prints[-1:]])
                    self.gaps.append({"start_ms": int(last), "end_ms": None,
                                      "reason": "app restart"})
            self.loaded_exp = exp
        except Exception as e:                              # noqa: BLE001
            self._err(e, "reload")
            self.loaded_exp = exp

    # ── read API for the tabs ────────────────────────────────────────
    def status(self) -> dict:
        age = (time.time() * 1000 - self.last_event_ms) / 1000 if self.last_event_ms else None
        return {"version": VERSION, "state": self.state, "container": self.cid,
                "alive": bool(self.thread and self.thread.is_alive()),
                "expiries": [str(e) for e in self.exps], "legs": len(self.legs),
                "prints": len(self.prints), "chain_rows": len(self.chain_rows),
                "spot_rows": len(self.spot_rows), "quotes": len(self.quotes),
                "greeks": len(self.greeks), "oi": len(self.oi),
                "last_event_age_s": age,
                "last_flush": self.last_flush.isoformat(timespec="seconds") if self.last_flush else None,
                "flush_error": self.last_flush_error, "repo": self.repo_kind,
                "uptime_min": round((time.time() - self.started_at) / 60, 1),
                "errors": len(self.errors)}

    def prints_df(self, exp: str | None = None) -> pd.DataFrame:
        with self.lock:
            df = pd.DataFrame(self.prints)
        if exp and len(df):
            df = df[df["exp"] == exp]
        return df

    def spot_df(self) -> pd.DataFrame:
        with self.lock:
            return pd.DataFrame(self.spot_rows)

    def chain_df(self) -> pd.DataFrame:
        with self.lock:
            return pd.DataFrame(self.chain_rows)
