"""v0.24.0 — LEAN candles: SPX 1-min candles painted by the options-flow lean (research L47/L48).

Flow per minute, from the recorder's prints (100 % of the day, live — the tastytrade replay only reaches ~13 %):
    bull = calls bought at the ask + puts sold at the bid · bear = puts bought + calls sold        (delta $)
    delta $ = |delta| × size × 100 × spot  (the print's live delta; replayed prints: Black-Scholes at the print's spot)
kept twice: SINGLE-LEG (spread / complex legs removed) and ALL prints, for the 0DTE and the 1DTE expiry.

Saved for research on the app repo's side branch `trishula-state` (same token as the 09:35 lock):
    state/lean/YYYY-MM-DD.json = {"day", "rows": [[minute_ms, g, sl_bull, sl_bear, all_bull, all_bear], …],
                                  "spx": [[minute_ms, o, h, l, c], …]}    g = 0 (0DTE) / 1 (1DTE), $M
written every 15 min and at the 16:15 roll (from the recorder's flush), ~30 KB a day. Survives reboots.

LOCKED TEST (pre-registered 5 Nov 2026 04:49 ET, before any single-leg day exists — see RESEARCH_LOG §12):
    A  1-min · 0DTE · rolling 15 m · sticky 8 % · 2-bar break · cooldown 10 · grey holds
    B  1-min · 0+1DTE · rolling 20 m · sticky 1 % · cooldown 5 · grey holds
    C  5-min · 0+1DTE · rolling 10 m · band 8 % · 2-bar break · cooldown 5 · grey holds
    D  1-min · 0DTE · per bar 15 % · cooldown 10 · grey holds
  each traded at every colour change, 0.5 SPX pt per round trip, single-leg flow. PASS = ≥ 15 days, total > 0, both
  halves > 0, above the 95th percentile of 200 time-shifted-flow runs, and the same rule on ALL prints is worse.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import threading
import time

import numpy as np
import pandas as pd

COST = 0.5
SAVE_EVERY_S = 15 * 60

LOCKED = {
    "A": dict(bar=1, flow="0DTE", src="roll", win=15, mode="sticky", X=0.08, conf=True, cool=10, skip=0, hold=True),
    "B": dict(bar=1, flow="0+1DTE", src="roll", win=20, mode="sticky", X=0.01, conf=False, cool=5, skip=0, hold=True),
    "C": dict(bar=5, flow="0+1DTE", src="roll", win=10, mode="band", X=0.08, conf=True, cool=5, skip=0, hold=True),
    "D": dict(bar=1, flow="0DTE", src="bar", win=1, mode="band", X=0.15, conf=False, cool=10, skip=0, hold=True),
}
DEFAULT = dict(LOCKED["A"], flow_kind="single-leg")


# ── per-minute flow from the recorder ────────────────────────────────────────────────────────────────────────────
def _bs_delta(spot, k, t_years, cp, iv=0.18):
    from scipy.special import ndtr
    t = np.maximum(t_years, 1e-6)
    d1 = (np.log(np.maximum(spot, 1e-9) / k) + 0.5 * iv * iv * t) / (iv * np.sqrt(t))
    nd = ndtr(d1)
    return np.abs(np.where(cp > 0, nd, nd - 1))


def minutes(rec, exps: list[str]) -> pd.DataFrame:
    """Per minute × expiry group: sl_b, sl_r, al_b, al_r in $M. Incremental on the print store (like print_minutes)."""
    cols = ["m", "g", "sl_b", "sl_r", "al_b", "al_r"]
    df = rec._all_prints()
    key = tuple(exps)
    with rec.lock:
        st_ = getattr(rec, "_lean", None)
        gen = getattr(rec, "_pgen", 0)
        if st_ is None or st_["key"] != key or st_["gen"] != gen or st_["n"] > len(df):
            st_ = {"key": key, "gen": gen, "n": 0, "agg": None}
        n0 = st_["n"]
    if len(df) > n0:
        new = df.iloc[n0:]
        ex = new["exp"].astype(str).values
        keep = np.isin(ex, list(exps)) & (new["ev_type"].astype(str).values != "2")
        if "eth" in new:
            keep &= ~new["eth"].values.astype(bool)
        if "valid" in new:
            keep &= new["valid"].values.astype(bool)
        new = new[keep]
        if len(new):
            ex = new["exp"].astype(str).values
            g = np.where(ex == exps[0], 0, 1)
            ag = new["aggr"].values.astype(float)
            cp = new["cp"].values.astype(float)
            spot = new["spot"].values.astype(float)
            dl = np.abs(new["delta"].values.astype(float))
            miss = ~np.isfinite(dl)
            if miss.any():
                cl = {e: pd.Timestamp(f"{e} 16:00").tz_localize("America/New_York").value // 10 ** 6 for e in set(ex[miss])}
                close = pd.Series(ex[miss]).map(cl).values.astype(float)
                tyr = (close - new["ts_ms"].values[miss]) / (365.25 * 86400e3)
                dl[miss] = _bs_delta(spot[miss], new["strike"].values.astype(float)[miss], tyr, cp[miss])
            usd = dl * new["size"].values.astype(float) * 100 * np.where(np.isfinite(spot), spot, 0) / 1e6
            bull = np.where(((cp > 0) & (ag > 0)) | ((cp < 0) & (ag < 0)), usd * np.abs(ag), 0.0)
            bear = np.where(((cp < 0) & (ag > 0)) | ((cp > 0) & (ag < 0)), usd * np.abs(ag), 0.0)
            sl = ~new["spread_leg"].values.astype(bool) if "spread_leg" in new else np.ones(len(new), bool)
            a = pd.DataFrame({"m": (new["ts_ms"].values // 60000) * 60000, "g": g,
                              "sl_b": np.where(sl, bull, 0.0), "sl_r": np.where(sl, bear, 0.0), "al_b": bull, "al_r": bear})
            agg = a if st_["agg"] is None else pd.concat([st_["agg"], a], ignore_index=True)
            st_["agg"] = agg.groupby(["m", "g"], as_index=False, sort=True).sum()
        st_ = dict(st_, n=len(df))
        with rec.lock:
            rec._lean = st_
    return st_["agg"] if st_["agg"] is not None else pd.DataFrame(columns=cols)


def spx_minutes(rec) -> pd.DataFrame:
    c = rec.candles_df()
    if c is None or not len(c):
        return pd.DataFrame(columns=["m", "o", "h", "l", "c"])
    c = c.rename(columns={"ts_ms": "m", "open": "o", "high": "h", "low": "l", "close": "c"})
    c["m"] = (c["m"] // 60000) * 60000
    return c.drop_duplicates("m", keep="last")[["m", "o", "h", "l", "c"]]


def live_day(rec) -> dict | None:
    if not getattr(rec, "exps", None):
        return None
    exps = [str(e) for e in rec.exps[:2]]
    return {"day": exps[0], "rows": minutes(rec, exps).round(4).values.tolist(), "spx": spx_minutes(rec).values.tolist()}


# ── persistence (side branch) ───────────────────────────────────────────────────────────────────────────────────
_save = {"at": 0.0, "day": None, "last": None, "err": None}


def maybe_save(rec, force: bool = False) -> None:
    """Called from the recorder's flush (every 5 min + at the 16:15 roll). Writes at most every 15 min, after RTH
    only once more, and always when forced."""
    from . import state as ST
    if not ST.status.get("configured"):
        return
    now = time.time()
    if not force and now - _save["at"] < SAVE_EVERY_S:
        return
    d = live_day(rec)
    if not d or not d["rows"]:
        return
    _save["at"] = now
    try:
        ST.save_file(f"state/lean/{d['day']}.json", d, f"lean {d['day']} {len(d['rows'])} rows", wait=True)
        _save.update(day=d["day"], last=time.strftime("%H:%M:%S"), err=None)
    except Exception as e:                                # noqa: BLE001
        _save["err"] = f"{type(e).__name__}: {str(e)[:120]}"


def saved_days() -> list[str]:
    from . import state as ST
    return sorted((n[:-5] for n in ST.list_dir("state/lean") if n.endswith(".json")), reverse=True)


_dcache: dict = {}
_dlock = threading.Lock()


def load_day(day: str) -> dict | None:
    from . import state as ST
    with _dlock:
        if day in _dcache:
            return _dcache[day]
    d = ST.read_file(f"state/lean/{day}.json")
    if d:
        with _dlock:
            _dcache[day] = d
    return d


# ── bars + rules ────────────────────────────────────────────────────────────────────────────────────────────────
def bars(d: dict, flow: str = "0DTE", kind: str = "single-leg", bar: int = 1) -> pd.DataFrame:
    """SPX o/h/l/c + bull/bear ($M) per bar, RTH only (09:30–15:59 ET)."""
    sp = pd.DataFrame(d.get("spx") or [], columns=["m", "o", "h", "l", "c"])
    rw = pd.DataFrame(d.get("rows") or [], columns=["m", "g", "sl_b", "sl_r", "al_b", "al_r"])
    if not len(sp):
        return pd.DataFrame(columns=["o", "h", "l", "c", "b", "r"])
    sp["t"] = pd.to_datetime(sp["m"], unit="ms", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    sp = sp.set_index("t").sort_index()
    day = sp.index[-1].normalize()
    sp = sp[(sp.index >= day + pd.Timedelta("9h30min")) & (sp.index <= day + pd.Timedelta("15h59min"))][["o", "h", "l", "c"]]
    if len(rw):
        if flow == "0DTE":
            rw = rw[rw.g == 0]
        p = "sl" if kind == "single-leg" else "al"
        rw = rw.assign(t=pd.to_datetime(rw["m"], unit="ms", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None))
        f = rw.groupby("t")[[f"{p}_b", f"{p}_r"]].sum()
        f.columns = ["b", "r"]
        sp = sp.join(f)
    sp[["b", "r"]] = sp.reindex(columns=["b", "r"]).fillna(0.0)
    if bar > 1 and len(sp):
        g = sp.groupby(sp.index.floor(f"{bar}min"))
        sp = pd.DataFrame(dict(o=g.o.first(), h=g.h.max(), l=g.l.min(), c=g.c.last(), b=g.b.sum(), r=g.r.sum()))
    return sp


def lean_series(b: pd.DataFrame, src: str, win: int) -> np.ndarray:
    net = (b.b - b.r).values; tot = (b.b + b.r).values
    if src == "bar":
        return np.where(tot > 0, net / np.where(tot > 0, tot, 1), 0.0)
    if src == "open":
        cn, ct = np.cumsum(net), np.cumsum(tot)
    else:
        cn = pd.Series(net).rolling(max(1, win), min_periods=1).sum().values
        ct = pd.Series(tot).rolling(max(1, win), min_periods=1).sum().values
    return np.where(ct > 0, cn / np.where(ct > 0, ct, 1), 0.0)


def colours(b: pd.DataFrame, src="roll", win=15, mode="sticky", X=0.08, conf=True, cool=10, skip=0, bar=1, **_) -> tuple[np.ndarray, np.ndarray]:
    """Causal: bar i's colour uses only bars ≤ i. win / skip in MINUTES (converted to bars)."""
    lean = lean_series(b, src, max(1, int(win) // bar))
    h, l, c = b.h.values, b.l.values, b.c.values
    n = len(c); col = np.zeros(n, int); stk = 0; last = 0; g = 99; sk = int(skip) // bar
    for i in range(n):
        v = lean[i]
        s = 1 if v >= X else (-1 if v <= -X else 0)
        if mode == "sticky":
            if s:
                stk = s
            w = stk
        else:
            w = s
        if i < sk:
            w = 0
        if w and conf:
            if i < 2 or (w > 0 and not c[i] > max(h[i - 1], h[i - 2])) or (w < 0 and not c[i] < min(l[i - 1], l[i - 2])):
                w = 0
        if w and cool and last and w == -last and g < cool:
            w = 0
        col[i] = w
        if w:
            g, last = 0, w
        else:
            g += 1
    return col, lean


def trades(b: pd.DataFrame, col: np.ndarray, hold=True, cost=COST) -> pd.DataFrame:
    """Enter at the close of the bar whose colour differs from the position; grey holds (hold=True) or flattens;
    flat at the last bar."""
    c = b.c.values; t = b.index; out = []; pos = 0; px = 0.0; t0 = None
    for i in range(len(c)):
        w = col[i]
        tgt = 0 if i == len(c) - 1 else ((pos if w == 0 else w) if hold else w)
        if tgt != pos:
            if pos:
                out.append(dict(entry=t0, exit=t[i], side="LONG" if pos > 0 else "SHORT", px_in=px, px_out=c[i],
                                pts=(c[i] - px) * pos, net=(c[i] - px) * pos - cost))
            pos, px, t0 = tgt, c[i], t[i]
    return pd.DataFrame(out, columns=["entry", "exit", "side", "px_in", "px_out", "pts", "net"])


def run_rule(d: dict, rule: dict, kind: str = "single-leg", shift: int = 0) -> pd.DataFrame:
    b = bars(d, rule["flow"], kind, rule["bar"])
    if len(b) < 20:
        return pd.DataFrame(columns=["net"])
    if shift:
        b = b.copy(); b[["b", "r"]] = np.roll(b[["b", "r"]].values, shift, axis=0)
    col, _ = colours(b, **rule)
    return trades(b, col, rule["hold"])


def locked_test(days: list[dict], n_null: int = 200, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed); rows = []
    for name, r in LOCKED.items():
        per = [run_rule(d, r).net.sum() for d in days]
        per_all = [run_rule(d, r, "all").net.sum() for d in days]
        if not per:
            continue
        tot = float(np.sum(per)); h = len(per) // 2
        nulls = []
        for _ in range(n_null):
            s = 0.0
            for d in days:
                n = len(bars(d, r["flow"], "single-leg", r["bar"]))
                s += run_rule(d, r, shift=int(rng.integers(n // 4, max(n // 4 + 1, 3 * n // 4)))).net.sum() if n >= 20 else 0
            nulls.append(s)
        p95 = float(np.percentile(nulls, 95)) if nulls else float("nan")
        ok = (len(per) >= 15 and tot > 0 and np.mean(per[:h]) > 0 and np.mean(per[h:]) > 0 and tot > p95 and tot > sum(per_all))
        rows.append({"rule": name, "days": len(per), "single-leg total": round(tot, 1), "per day": round(tot / len(per), 2),
                     "days up": f"{sum(x > 0 for x in per)}/{len(per)}",
                     "1st half / 2nd half": f"{np.mean(per[:h]) if h else float('nan'):+.1f} / {np.mean(per[h:]):+.1f}",
                     "null 95th pct": round(p95, 1), "all-prints total": round(float(sum(per_all)), 1),
                     "PASS": "✅" if ok else ("…" if len(per) < 15 else "❌")})
    return pd.DataFrame(rows)
