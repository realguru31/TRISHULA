"""v0.29.0 — SPX BB: 0.05-bid liquidity edges on the 0DTE / 1DTE SPXW chain + Telegram alerts.

  CALL EDGE = highest call strike at/above spot still bid >= min bid · PUT EDGE = lowest put strike at/below spot.
  Data      = recorder quotes on EVERY strike of the recorder's two expiries (rec.bb_meta) + rec.spot_now()
              (SPX, or the option-implied synthetic spot pre-market / after the close).
  Labels    = SPX BB rolls at 21:00 ET (only this tab): before 21:00 "0DTE" = today, "1DTE" = next expiry; from
              21:00 the next expiry becomes 0DTE. After 16:00 today's 0DTE shows EXPIRED with its edges frozen.
  Alerts    = for the selected toggle's expiry only. An edge alerts when it is >= threshold points BEYOND the last
              alerted strike, away from spot (high-water mark — inward moves never re-trigger). Plus ONE warning
              when an edge reaches one of your sold strikes (once per strike and expiry — no repeats).
              No alerts on stale quotes (> 120 s) or in the 09:15–09:30 ET session gap.
  Secrets   = TG_BOT_TOKEN / TG_CHAT_ID from Streamlit secrets (never in the code).
  Config    = shared (one app, one trader): toggle, threshold, min bid, alerts on/off, sold strikes — saved to
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
CHECK_S = 15
CFG_PATH = "state/bb_config.json"
DEFAULTS = {"mode": "0DTE", "threshold": 10, "min_bid": 0.05, "alerts": True, "sold_call": 0.0, "sold_put": 0.0}


class Tracker:
    def __init__(self, rec, tg_token: str = "", tg_chat: str = ""):
        self.rec, self.tg_token, self.tg_chat = rec, tg_token or "", str(tg_chat or "")
        self.cfg = dict(DEFAULTS)
        self.series: dict[str, list] = {}          # exp → rows (t, spot, src, ce, ce_b, ce_a, pe, pe_b, pe_a)
        self.alerts: list = []                     # (t, exp, side, strike) — chart markers
        self.marks: dict = {}                      # (exp, side) → last alerted strike
        self.warned: dict = {}                     # (exp, side, sold) → warned once
        self.seen: set = set()
        self.status = {"last": None, "error": None, "tg": None}
        self._mk = None
        self.t = None
        try:
            saved = ST.read_file(CFG_PATH)
            if isinstance(saved, dict):
                self.cfg.update({k: saved[k] for k in DEFAULTS if k in saved})
        except Exception:                          # noqa: BLE001
            pass

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
            rows.append((now.isoformat(timespec="seconds"), round(spot, 2), src, *ce, *pe))
            if len(rows) > 6000:
                del rows[:len(rows) - 6000]
            if lab == self.cfg["mode"]:
                self._alerts(lab, exp, spot, src, e, now)
        for k in [k for k in self.series if k not in self.seen]:
            self.series.pop(k, None)
        while len(self.series) > 3:
            self.series.pop(sorted(self.series)[0], None)
        self.status["last"] = now.strftime("%H:%M:%S")

    def _alerts(self, lab, exp, spot, src, e, now):
        mk = (lab, exp)
        if mk != self._mk:                         # toggle / expiry changed → fresh high-water marks
            self._mk, self.marks = mk, {}
        if not self.cfg.get("alerts"):
            return
        if dt.time(9, 15) <= now.time() < dt.time(9, 30):
            return
        if e["newest_ms"] and time.time() * 1000 - e["newest_ms"] > 120_000:
            return
        thr = float(self.cfg["threshold"])
        dlab = f"{lab} {dt.date.fromisoformat(exp):%a %d %b}"
        for side, edge, sgn in (("call", e["ce"], 1), ("put", e["pe"], -1)):
            if edge is None:
                continue
            k, b, a = edge
            last = self.marks.get((exp, side))
            if last is None:
                self.marks[(exp, side)] = k
            elif sgn * (k - last) >= thr - 1e-9:
                self.marks[(exp, side)] = k
                self.alerts.append((now.isoformat(timespec="seconds"), exp, side, k))
                self.alerts = self.alerts[-300:]
                self.send(f"{'🟢' if side == 'call' else '🔴'} SPX {dlab} {side.upper()} WALL "
                          f"{'↑' if sgn > 0 else '↓'} {last:,.0f} → {k:,.0f} ({k - last:+,.0f} pts)\n"
                          f"{k:,.0f}{'C' if side == 'call' else 'P'} bid {b:.2f} / ask {a:.2f} "
                          f"(min bid {self.cfg['min_bid']:.2f})\n"
                          f"spot {spot:,.2f}{'' if src == 'spx' else ' (' + src + ')'} · {side} dist "
                          f"{abs(k - spot):,.0f} · {now:%H:%M:%S} ET")
            sold = float(self.cfg.get(f"sold_{side}") or 0)
            if sold > 0:
                through = (k >= sold) if side == "call" else (k <= sold)
                key = (exp, side, sold)
                if through and not self.warned.get(key):
                    self.warned[key] = True
                    sb, sa = self.quote(exp, sold, sgn)
                    self.send(f"⚠️ SPX {dlab} 0.05 {side.upper()} EDGE REACHED YOUR SOLD {sold:,.0f}"
                              f"{'C' if side == 'call' else 'P'}\nedge {k:,.0f} · your strike bid {sb:.2f} / ask {sa:.2f}"
                              f" · spot {spot:,.2f} · {now:%H:%M:%S} ET")

    # ── thread ──────────────────────────────────────────────────────────────────
    def start(self):
        if self.t is None or not self.t.is_alive():
            self.t = threading.Thread(target=self._run, daemon=True, name="trishula-bb")
            self.t.start()
        return self

    def _run(self):
        while True:
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
