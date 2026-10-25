"""As-of view of the recorder for the universal replay player.

Every tab reads the recorder through the same methods (spot_now, live_chain,
chain_df, prints_df, candles_df, spot_df, dsign_table, vix_df, greeks …).
In replay, AsOf answers each of them as of the selected snapshot time t:
the chain snapshot at t, prints/candles/spot ≤ t, dealer signs from the tape
≤ t. Anything not overridden passes through to the live recorder.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import signs


def view(rec, ts_ms: int | None):
    return rec if ts_ms is None else AsOf(rec, int(ts_ms))


class AsOf:
    def __init__(self, rec, ts_ms: int):
        self._rec = rec
        self.ts_ms = ts_ms
        self.replay = True

    def __getattr__(self, name):              # exps, all_exps, legs, lock, ui_state, oi_log, …
        return getattr(self._rec, name)

    # ── time-sliced reads ───────────────────────────────────────────
    def chain_df(self) -> pd.DataFrame:
        h = self._rec.chain_df()
        return h[h["ts_ms"] <= self.ts_ms] if len(h) else h

    def _snap(self) -> pd.DataFrame:
        h = self.chain_df()
        if h.empty:
            return h
        return h[h["ts_ms"] == h["ts_ms"].max()]

    def live_chain(self, exp: str | None = None) -> pd.DataFrame:
        s = self._snap()
        if exp and len(s):
            s = s[s["exp"] == exp]
        return s.reset_index(drop=True)

    def spot_now(self):
        s = self.spot_df()
        if len(s) and s["spot"].notna().any():
            r = s.dropna(subset=["spot"]).iloc[-1]
            return float(r["spot"]), f"{r.get('spot_src', 'spot')}@replay"
        c = self.candles_df()
        if len(c):
            return float(c["close"].iloc[-1]), "candle@replay"
        sn = self._snap()
        if len(sn) and sn["spot"].notna().any():
            return float(sn["spot"].dropna().iloc[0]), "snapshot@replay"
        return float("nan"), "replay"

    def opt1m_df(self) -> pd.DataFrame:
        d = self._rec.opt1m_df()
        return d[d["ts_ms"] <= self.ts_ms] if len(d) else d

    def prints_df(self, exp: str | None = None) -> pd.DataFrame:
        p = self._rec.prints_df(exp)
        return p[p["ts_ms"] <= self.ts_ms] if len(p) else p

    def candles_df(self) -> pd.DataFrame:
        c = self._rec.candles_df()
        return c[c["ts_ms"] <= self.ts_ms] if len(c) else c

    def spot_df(self) -> pd.DataFrame:
        s = self._rec.spot_df()
        return s[s["ts_ms"] <= self.ts_ms] if len(s) else s

    def spy_df(self) -> pd.DataFrame:
        v = self._rec.spy_df()
        return v[v["ts_ms"] <= self.ts_ms] if len(v) else v

    def vix_df(self) -> pd.DataFrame:
        v = self._rec.vix_df()
        return v[v["ts_ms"] <= self.ts_ms] if len(v) else v

    @property
    def greeks(self) -> dict:
        s = self._snap()
        if s.empty:
            return {}
        return {r.sym: (r.iv, r.delta, r.gamma, r.theta, r.vega, int(r.ts_ms)) for r in s.itertuples()}

    @property
    def n_prints(self) -> int:
        return len(self.prints_df())

    def dsign_table(self, exp: str, single_leg: bool = False) -> pd.DataFrame:
        key = ("asof", exp, single_leg, self.ts_ms, self._rec.n_prints, len(self._rec.c5))
        c = self._rec.ui_state.setdefault("_asof_ds", {})
        if key in c:
            return c[key]
        with self._rec.lock:
            legs = dict(self._rec.legs)
        t = signs.dsign_table(self.prints_df(), self._rec.candles5_df(), legs, exp, self.ts_ms,
                              single_leg, self._rec._session())
        while len(c) >= 16:
            c.pop(next(iter(c)))
        c[key] = t
        return t

    def status(self) -> dict:
        s = dict(self._rec.status())
        s["replay_at_ms"] = self.ts_ms
        return s


def frames(rec) -> list[int]:
    """All snapshot times the recorder holds (ascending) — the player's timeline."""
    h = rec.chain_df()
    if h.empty:
        return []
    return sorted(int(t) for t in np.unique(h["ts_ms"].values))


def now_ms() -> int:
    return int(time.time() * 1000)
