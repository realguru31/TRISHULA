"""v0.29.0 — SPX BB: 0.05-bid liquidity edges on the 0DTE / 1DTE SPXW chain + Telegram alerts.

  CALL EDGE = highest call strike at/above spot still bid >= min bid · PUT EDGE = lowest put strike at/below spot.
  Data      = recorder quotes on EVERY strike of the recorder's two expiries (rec.bb_meta) + rec.spot_now()
              (SPX, or the option-implied synthetic spot pre-market / after the close).
  Labels    = SPX BB rolls at 21:00 ET (only this tab): before 21:00 "0DTE" = today, "1DTE" = next expiry; from
              21:00 the next expiry becomes 0DTE. After 16:00 today's 0DTE shows EXPIRED with its edges frozen.
  Alerts    = v0.31.0: 0DTE always, 1DTE only 15:00–21:00 ET — both whatever the view toggle shows, each with its
              own on/off and jump size. An edge alerts when it is >= threshold points BEYOND the last
              alerted strike, away from spot (high-water mark — inward moves never re-trigger). Plus ONE warning
              when an edge reaches one of your sold strikes (once per strike and expiry — no repeats).
              No alerts on stale quotes (> 120 s) or in the 09:15–09:30 ET session gap.
  Secrets   = TG_BOT_TOKEN / TG_CHAT_ID from Streamlit secrets (never in the code).
  Config    = shared (one app, one trader): toggle, min bid, per-expiry alerts + jumps, sold strikes — saved to
              state/bb_config.json on the trishula-state branch so a reboot keeps it.
"""
from __future__ import annotations

import datetime as dt
import threading
import time

from . import expiry as EX
from . import state as ST
from .timeutil import now_et

BB_ROLL = dt.time(21, 0)
THRESHOLDS = [5, 10, 15, 20, 25, 30, 40, 50]
CHECK_S = 5                 # v0.33.0: was 15
CFG_PATH = "state/bb_config.json"
HIST_PATH = "state/bb_history.json"       # v0.34.0: edge-change points + alerts + alert levels (survive reboots)
SAVE_EVERY_S = 60
DEFAULTS = {"mode": "0DTE", "min_bid": 0.05, "sold_call": 0.0, "sold_put": 0.0,
            "alert0": True, "thr0": 10, "alert1": True, "thr1": 10,       # v0.31.0: per-expiry alerts
            "ask_alert": 0.50,                                            # v0.32.0: sold-strike ask alert level
            "sold_call_exp": "", "sold_put_exp": ""}                      # v0.41.0: expiry each sold strike is for
ONE_DTE_FROM, ONE_DTE_TO = dt.time(15, 0), BB_ROLL                       # 1DTE alerts only 15:00–21:00 ET


class Tracker:
    def __init__(self, rec, tg_token: str = "", tg_chat: str = ""):
        self.rec, self.tg_token, self.tg_chat = rec, tg_token or "", str(tg_chat or "")
        self.cfg = dict(DEFAULTS)
        self.series: dict[str, list] = {}          # exp → rows (t, spot, src, ce, ce_b, ce_a, pe, pe_b, pe_a)
        self.alerts: list = []                     # (t, exp, side, strike) — chart markers
        self.strad: dict[str, list] = {}           # v0.43.0: exp → (t minute, ATM strike, straddle mid) once a minute
        self.strad_bf: dict[str, list] = {}        # v0.45.0: straddle backfilled from 1-minute trade candles
        self._bf_min: dict[str, str] = {}
        self.mae: dict[str, dict] = {}             # v0.44.0: "exp|side|strike" → worst trade / ask since 09:30
        self.marks: dict = {}                      # (exp, side) → last alerted strike
        self.warned: dict = {}                     # (exp, side, sold) → warned once
        self.seen: set = set()
        self.status = {"last": None, "error": None, "tg": None}
        self.t = None
        self._stop = False                         # v0.36.0: a newer version's tracker stops this one
        self._dirty, self._saved_at = False, 0.0
        try:                                       # v0.34.0: edge history survives reboots
            h = ST.read_file(HIST_PATH)
            if isinstance(h, dict):
                today = now_et().date()
                for k, v in (h.get("series") or {}).items():
                    if dt.date.fromisoformat(k[:10]) >= today - dt.timedelta(days=4):
                        self.series[k] = [tuple(r) for r in v]
                        self.seen.add(k)
                self.alerts = [tuple(a) for a in (h.get("alerts") or []) if a[1] in self.series]
                self.mae = {k: v for k, v in (h.get("mae") or {}).items() if k.split("|")[0] in self.series}
                self.strad = {k: [tuple(r) for r in v] for k, v in (h.get("strad") or {}).items() if k in self.series}
                # v0.38.0: alert levels are NOT reloaded — every day / every restart starts from the live edge
        except Exception:                          # noqa: BLE001
            pass
        try:
            saved = ST.read_file(CFG_PATH)
            if isinstance(saved, dict):
                self.cfg.update({k: saved[k] for k in DEFAULTS if k in saved})
                if "threshold" in saved and "thr0" not in saved:      # pre-0.31 single threshold → both
                    self.cfg["thr0"] = self.cfg["thr1"] = int(saved["threshold"])
        except Exception:                          # noqa: BLE001
            pass
        self._roll_base = None                     # v0.38.0: view resets to 0DTE at the 21:00 roll

    # ── config / telegram ─────────────────────────────────────────────────────────
    @property
    def tg_ok(self) -> bool:
        return bool(self.tg_token and self.tg_chat)

    def set(self, **kw):
        ch = {k: v for k, v in kw.items() if k in DEFAULTS and self.cfg.get(k) != v}
        if not ch:
            return
        self.cfg.update(ch)
        try:
            ST.save_file(CFG_PATH, self.cfg, "SPX BB settings")
        except Exception:                          # noqa: BLE001
            pass

    def send(self, text: str) -> bool:
        if not self.tg_ok:
            self.status["tg"] = "not configured"
            return False
        try:
            import requests
            r = requests.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                              data={"chat_id": self.tg_chat, "text": text, "disable_web_page_preview": True},
                              timeout=10)
            self.status["tg"] = "ok" if r.ok else f"error {r.status_code}: {r.text[:120]}"
            return r.ok
        except Exception as e:                     # noqa: BLE001
            self.status["tg"] = f"error {type(e).__name__}"
            return False

    # ── expiries (SPX BB's own 21:00 roll) ────────────────────────────────────────
    def expiries(self, now=None):
        """[(label, exp_str, expired)] for 0DTE and 1DTE."""
        now = (now or now_et()).replace(tzinfo=None)
        for e in (self.rec.all_exps or []):
            self.seen.add(str(e))
        dates = sorted(self.seen)
        base = now.date() if now.time() < BB_ROLL else now.date() + dt.timedelta(days=1)
        fut = [d for d in dates if dt.date.fromisoformat(d) >= base]
        out = []
        for lab, d in zip(("0DTE", "1DTE"), fut[:2]):
            out.append((lab, d, now >= EX.end(d)))
        return out

    def exp_for(self, mode: str):
        for lab, d, x in self.expiries():
            if lab == mode:
                return d, x
        return None, True

    # ── edges ───────────────────────────────────────────────────────────────────
    def edges(self, exp: str, spot: float, min_bid: float):
        rec = self.rec
        meta = dict(getattr(rec, "bb_meta", {}) or {}) or dict(rec.legs)
        for _ in range(3):
            try:
                qs = list(rec.quotes.items())
                break
            except RuntimeError:
                time.sleep(0.01)
        else:
            return None
        ce = pe = None
        newest = 0
        for sym, q in qs:
            m = meta.get(sym)
            if not m or m[0] != exp:
                continue
            b, a, ms = q
            newest = max(newest, ms or 0)
            if not (b == b) or b < min_bid - 1e-9:
                continue
            k, cp = m[1], m[2]
            if cp > 0 and k >= spot and (ce is None or k > ce[0]):
                ce = (k, b, a)
            elif cp < 0 and k <= spot and (pe is None or k < pe[0]):
                pe = (k, b, a)
        return dict(ce=ce, pe=pe, newest_ms=newest)

    def quote(self, exp: str, strike: float, cp: int):
        meta = getattr(self.rec, "bb_meta", {}) or {}
        for sym, m in list(meta.items()):
            if m[0] == exp and abs(m[1] - strike) < 1e-6 and m[2] == cp:
                q = self.rec.quotes.get(sym)
                return (q[0], q[1]) if q else (float("nan"), float("nan"))
        return (float("nan"), float("nan"))

    # ── one check ───────────────────────────────────────────────────────────────
    def step(self):
        now = now_et().replace(tzinfo=None)
        base = now.date() if now.time() < BB_ROLL else now.date() + dt.timedelta(days=1)
        if self._roll_base is not None and base != self._roll_base:
            self.set(mode="0DTE")                  # v0.38.0: a new BB day always starts on 0DTE
        self._roll_base = base
        self._sold_expiry(now)
        spot, src = self.rec.spot_now()
        if not spot == spot:
            return
        mb = float(self.cfg["min_bid"])
        for lab, exp, expired in self.expiries(now):
            if expired:
                continue
            e = self.edges(exp, spot, mb)
            if not e or (e["ce"] is None and e["pe"] is None):
                continue
            ce, pe = e["ce"] or (None, None, None), e["pe"] or (None, None, None)
            rows = self.series.setdefault(exp, [])
            row = (now.isoformat(timespec="seconds"), round(spot, 2), src, *ce, *pe)
            last = rows[-1] if rows else None
            # v0.34.0: store a point ONLY when the call or put edge STRIKE changes (bid/ask and spot moves don't);
            # the charts draw steps carried to now and take SPX from the 1-minute candles
            if last is None or row[3] != last[3] or row[6] != last[6]:
                rows.append(row)
                self._dirty = True
            if len(rows) > 12000:
                del rows[:len(rows) - 12000]
            self._straddle(exp, spot, now)
            self._strad_backfill(exp, now)
            self._mae(exp, now)
            self._alerts(lab, exp, spot, src, e, now)       # v0.31.0: both expiries, whatever the view toggle
            self._ask_alerts(lab, exp, spot, src, e, now)       # v0.41.0: only for the sold strikes' own expiry
        live_exps = {d for _, d, _ in self.expiries(now)}
        for k in [k for k in self.marks if k[0] not in live_exps]:
            self.marks.pop(k, None)
        for k in [k for k in self.series if k not in self.seen]:
            self.series.pop(k, None)
        for k in [k for k in self.mae if k.split("|")[0] not in live_exps]:
            self.mae.pop(k, None)
        for k in [k for k in self.strad if k not in self.series]:
            self.strad.pop(k, None)
        while len(self.series) > 3:
            self.series.pop(sorted(self.series)[0], None)
        self.status["last"] = now.strftime("%H:%M:%S")
        if self._dirty and time.time() - self._saved_at >= SAVE_EVERY_S:
            self._dirty, self._saved_at = False, time.time()
            try:
                ST.save_file(HIST_PATH, {"series": self.series, "alerts": self.alerts, "strad": self.strad, "mae": self.mae}, "SPX BB history")
            except Exception:                      # noqa: BLE001
                self._dirty = True

    def straddle(self, exp: str, spot: float):
        """ATM straddle = call mid + put mid at the strike nearest spot that has two-sided quotes on both legs."""
        meta = dict(getattr(self.rec, "bb_meta", {}) or {}) or dict(self.rec.legs)
        q = self.rec.quotes
        legs: dict = {}
        for sym, (ex, k, cp) in meta.items():
            if ex != exp or abs(k - spot) > 60:
                continue
            v = q.get(sym)
            if v and v[0] == v[0] and v[1] == v[1] and v[0] > 0 and v[1] >= v[0]:
                legs.setdefault(k, {})[cp] = (v[0] + v[1]) / 2
        ks = [k for k, d in legs.items() if 1 in d and -1 in d]
        if not ks:
            return None
        k = min(ks, key=lambda x: abs(x - spot))
        return k, legs[k][1] + legs[k][-1]

    def _straddle(self, exp, spot, now):
        """v0.43.0: one ATM straddle point per minute per expiry (for the width chart overlay)."""
        tm = now.replace(second=0, microsecond=0).isoformat(timespec="minutes")
        rows = self.strad.setdefault(exp, [])
        if rows and rows[-1][0] == tm:
            return
        try:
            r = self.straddle(exp, spot)
        except Exception:                          # noqa: BLE001
            r = None
        if r:
            rows.append((tm, r[0], round(r[1], 2)))
            if len(rows) > 3000:
                del rows[:len(rows) - 3000]
            self._dirty = True

    def sym_for(self, exp: str, k: float, cp: int):
        meta = getattr(self.rec, "bb_meta", {}) or {}
        for sym, (ex, kk, c) in list(meta.items()):
            if ex == exp and c == cp and abs(kk - k) < 1e-6:
                return sym
        return None

    def _mae(self, exp, now):
        """v0.44.0: worst price against your sold strikes for this expiry — highest TRADE (1-minute candles from
        tastytrade, back to 09:30 or the 15:00 1DTE window if sold after the close) and highest ASK seen live in RTH."""
        for side, cp in (("call", 1), ("put", -1)):
            k = self.sold_for(side, exp)
            if k <= 0:
                continue
            sym = self.sym_for(exp, k, cp)
            if not sym:
                continue
            day = now.date()
            exp_d = dt.date.fromisoformat(exp[:10])
            w0 = dt.datetime.combine(day, dt.time(9, 30)) if exp_d == day else \
                dt.datetime.combine(day, dt.time(15, 0))
            w0_ms = int(w0.replace(tzinfo=now_et().tzinfo).timestamp() * 1000)
            want = getattr(self.rec, "want_candle", None)
            if want:
                want(sym, w0_ms)
            key = f"{exp}|{side}|{k:.0f}"
            m = self.mae.setdefault(key, {})
            oc = (getattr(self.rec, "ocandles", {}) or {}).get(sym) or {}
            hits = [(v[0], t) for t, v in list(oc.items()) if t >= w0_ms]
            if hits:
                hi, t_ = max(hits)
                if hi > float(m.get("trade") or 0):
                    m["trade"] = hi
                    m["trade_t"] = dt.datetime.fromtimestamp(t_ / 1000, tz=now_et().tzinfo).strftime("%H:%M")
                    self._dirty = True
            if now.weekday() < 5 and dt.time(9, 30) <= now.time() < dt.time(16, 0):
                b, a = self.quote(exp, k, cp)
                if a == a and a > float(m.get("ask") or 0):
                    m["ask"], m["ask_t"] = a, now.strftime("%H:%M")
                    self._dirty = True

    def mae_for(self, exp: str, side: str, k: float):
        return self.mae.get(f"{exp}|{side}|{k:.0f}") or {}

    def _strad_backfill(self, exp, now):
        """v0.45.0: rebuild today's 0DTE ATM straddle from 09:30 out of tastytrade 1-minute TRADE candles (strikes
        across today's SPX range ± 30, calls + puts), so the line starts at the open whenever the app is loaded.
        Live mid readings take priority where they exist. Runs once a minute."""
        import bisect
        if dt.date.fromisoformat(exp[:10]) != now.date() or now.time() < dt.time(9, 31):
            return
        tm = now.strftime("%H:%M")
        if self._bf_min.get(exp) == tm:
            return
        self._bf_min[exp] = tm
        want = getattr(self.rec, "want_candle", None)
        oc_all = getattr(self.rec, "ocandles", None)
        if want is None or oc_all is None:
            return
        tz = now_et().tzinfo
        w0 = int(dt.datetime.combine(now.date(), dt.time(9, 30)).replace(tzinfo=tz).timestamp() * 1000)
        w1 = int(dt.datetime.combine(now.date(), dt.time(16, 0)).replace(tzinfo=tz).timestamp() * 1000)
        try:
            spx = sorted((t, v[3]) for t, v in list(self.rec.candles.items()) if w0 <= t < w1 and v[3] == v[3])
        except Exception:                          # noqa: BLE001
            return
        if not spx:
            return
        lo = int((min(c for _, c in spx) - 30) // 5 * 5)
        hi = int(-(-(max(c for _, c in spx) + 30) // 5) * 5)
        idx = {}
        for sym, (ex, k, cp) in list((getattr(self.rec, "bb_meta", {}) or {}).items()):
            if ex == exp and lo <= k <= hi:
                idx[(k, cp)] = sym
        for sym in idx.values():
            want(sym, w0)
        legs = {}
        for key, sym in idx.items():
            d = oc_all.get(sym) or {}
            pts = sorted((t, v[1]) for t, v in list(d.items()) if t >= w0 and v[1] == v[1])
            if pts:
                legs[key] = ([t for t, _ in pts], [c for _, c in pts])
        ks = sorted({k for (k, cp) in legs if (k, 1) in legs and (k, -1) in legs})
        if not ks:
            return
        out = []
        for t, s_ in spx:
            k = min(ks, key=lambda x: abs(x - s_))
            v = 0.0
            for cp in (1, -1):
                ts, cs = legs[(k, cp)]
                i = bisect.bisect_right(ts, t) - 1
                if i < 0:
                    v = None
                    break
                v += cs[i]
            if v:
                out.append((dt.datetime.fromtimestamp(t / 1000, tz).replace(tzinfo=None).isoformat(timespec="minutes"),
                            k, round(v, 2)))
        self.strad_bf[exp] = out

    def strad_frame(self, exp: str):
        """Live mid readings + the candle backfill for minutes the live recording does not have."""
        import pandas as pd
        live = pd.DataFrame(self.strad.get(exp) or [], columns=["t", "k", "strad"])
        bf = pd.DataFrame(self.strad_bf.get(exp) or [], columns=["t", "k", "strad"])
        if len(bf) and len(live):
            bf = bf[~bf["t"].isin(set(live["t"]))]
        df = pd.concat([x for x in (bf, live) if len(x)]) if (len(bf) or len(live)) else live
        if len(df):
            df["t"] = pd.to_datetime(df["t"])
            df = df.sort_values("t").reset_index(drop=True)
        return df

    def _sold_expiry(self, now):
        """v0.41.0: a sold strike belongs to the expiry it was entered for — cleared once that expiry has ended
        (16:00 / its real stop time). One saved without an expiry (pre-0.41) is given today's 0DTE."""
        exps = self.expiries(now)
        for side in ("call", "put"):
            k = float(self.cfg.get(f"sold_{side}") or 0)
            ex = str(self.cfg.get(f"sold_{side}_exp") or "")
            if k <= 0:
                if ex:
                    self.set(**{f"sold_{side}_exp": ""})
                continue
            if not ex:
                if exps:
                    self.set(**{f"sold_{side}_exp": exps[0][1]})
                continue
            try:
                done = now >= EX.end(ex)
            except Exception:                      # noqa: BLE001
                done = now.date() > dt.date.fromisoformat(ex[:10])
            if done:
                self.set(**{f"sold_{side}": 0.0, f"sold_{side}_exp": ""})

    def sold_for(self, side: str, exp: str) -> float:
        """The sold strike if it was entered for THIS expiry, else 0."""
        k = float(self.cfg.get(f"sold_{side}") or 0)
        return k if k > 0 and str(self.cfg.get(f"sold_{side}_exp") or "") == exp else 0.0

    def alert_window(self, lab, now) -> bool:
        """v0.38.0 — 0DTE: 09:30–16:00 ET weekdays · 1DTE: 15:00–21:00 ET. Outside it the alert level copies the edge,
        so each window starts clean from where the edge is when it opens (nothing carried from earlier / overnight)."""
        if lab == "1DTE":
            return ONE_DTE_FROM <= now.time() < ONE_DTE_TO
        return now.weekday() < 5 and dt.time(9, 30) <= now.time() < dt.time(16, 0)

    def _alerts(self, lab, exp, spot, src, e, now):
        """v0.38.0: outside its window (or switched off / stale quotes) the level COPIES the edge both ways, so the first
        alert counts from the edge at 09:30 (0DTE) / 15:00 (1DTE). Inside: one alert per ≥ thr jump outward, no repeats."""
        n = "0" if lab == "0DTE" else "1"
        live = (bool(self.cfg.get(f"alert{n}")) and self.alert_window(lab, now)
                and not (e["newest_ms"] and time.time() * 1000 - e["newest_ms"] > 120_000))
        thr = float(self.cfg.get(f"thr{n}") or 10)
        dlab = f"{lab} {dt.date.fromisoformat(exp):%a %d %b}"
        for side, edge, sgn in (("call", e["ce"], 1), ("put", e["pe"], -1)):
            if edge is None:
                continue
            k, b, a = edge
            last = self.marks.get((exp, side))
            if last is None:
                self.marks[(exp, side)] = k
            elif not live:
                self.marks[(exp, side)] = k            # copy the edge, both ways
            elif sgn * (k - last) >= thr - 1e-9:
                self.marks[(exp, side)] = k
                self.alerts.append((now.isoformat(timespec="seconds"), exp, side, k))
                self.alerts = self.alerts[-300:]
                self.send(f"{'🟢' if side == 'call' else '🔴'} SPX {dlab} {side.upper()} EDGE "
                          f"{'↑' if sgn > 0 else '↓'} {last:.0f} → {k:.0f} ({k - last:+.0f} pts)\n"
                          f"{k:.0f}{'C' if side == 'call' else 'P'} bid {b:.2f} / ask {a:.2f} "
                          f"(min bid {self.cfg['min_bid']:.2f})\n"
                          f"spot {spot:,.2f}{'' if src == 'spx' else ' (' + src + ')'} · {side} dist "
                          f"{abs(k - spot):.0f} · {now:%H:%M:%S} ET")
            sold = self.sold_for(side, exp)
            if sold > 0 and live:                               # v0.41.0: the expiry the strike was sold for
                through = (k >= sold) if side == "call" else (k <= sold)
                key = (now.date(), exp, side, sold)              # once per day
                if through and not self.warned.get(key):
                    self.warned[key] = True
                    sb, sa = self.quote(exp, sold, sgn)
                    self.send(f"⚠️ SPX {dlab} 0.05 {side.upper()} EDGE REACHED YOUR SOLD {sold:.0f}"
                              f"{'C' if side == 'call' else 'P'}\nedge {k:.0f} · your strike bid {sb:.2f} / ask {sa:.2f}"
                              f" · spot {spot:,.2f} · {now:%H:%M:%S} ET")

    def _ask_alerts(self, lab, exp, spot, src, e, now):
        """v0.32.0: Telegram once when the ASK of your sold C / sold P reaches cfg['ask_alert'] (default 0.50).
        Regular hours only (09:30–16:00 ET, weekdays) — overnight asks are too wide to mean anything. Empty sold box
        (0) = not watched. Once per (expiry, side, strike, level); a new strike or level arms it again."""
        lvl = float(self.cfg.get("ask_alert") or 0)
        if lvl <= 0 or now.weekday() >= 5 or not (dt.time(9, 30) <= now.time() < dt.time(16, 0)):
            return
        dlab = f"{lab} {dt.date.fromisoformat(exp):%a %d %b}"
        for side, cp in (("call", 1), ("put", -1)):
            k = self.sold_for(side, exp)
            if k <= 0:
                continue
            b, a = self.quote(exp, k, cp)
            key = ("ask", now.date(), exp, side, k, lvl)
            if a == a and a >= lvl - 1e-9 and not self.warned.get(key):
                self.warned[key] = True
                edge = (e.get("ce") if side == "call" else e.get("pe")) or (float("nan"),)
                self.send(f"⚠️ SPX {dlab} · your sold {k:.0f}{'C' if side == 'call' else 'P'} ASK {a:.2f}"
                          f" (bid {b:.2f}) ≥ {lvl:.2f}\nspot {spot:,.2f}{'' if src == 'spx' else ' (' + src + ')'}"
                          f" · {side} edge {edge[0]:.0f} · {now:%H:%M:%S} ET")

    # ── thread ──────────────────────────────────────────────────────────────────
    def start(self):
        if not self._stop and (self.t is None or not self.t.is_alive()):
            self.t = threading.Thread(target=self._run, daemon=True, name="trishula-bb")
            self.t.start()
        return self

    def stop(self):
        self._stop = True

    def _run(self):
        while not self._stop:
            try:
                self.step()
                self.status["error"] = None
            except Exception as e:                 # noqa: BLE001
                self.status["error"] = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(CHECK_S)

    def frame(self, exp: str):
        import pandas as pd
        rows = self.series.get(exp) or []
        cols = ["t", "spot", "src", "ce", "ce_bid", "ce_ask", "pe", "pe_bid", "pe_ask"]
        df = pd.DataFrame(rows, columns=cols)
        if len(df):
            df["t"] = pd.to_datetime(df["t"])
        return df
