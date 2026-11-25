"""v0.44.0 OrderFlow · unusual options (SPX / ES / SPY), each flag on its own toggle. NO REPAINT.

ORDERS, not prints: prints on the same contract, same side, same second are one order (a 500-lot fills as 50–70
prints). Size that matters = delta notional (|Δ| × contracts × multiplier × underlying), Δ from the order's own price.

Every flag is decided the moment the order prints, against a cut-off taken from the PREVIOUS sessions for the same
half-hour of the day (09:30, 10:00 … 15:30), so a flag never appears or disappears later (v0.41–0.43 ranked the
whole day so far → early flags vanished as bigger ones came, and a replay showed only the day's eventual top N).

1 big orders     delta notional ≥ the 1-in-N cut-off of all orders in this half-hour over the last 10 sessions.
2 bursts         a strike (C+P) trading > k × its own rolling median minute (prior `win` min) and > k × the market's
                 typical busy strike-minute, AND its multiple ≥ the 1-in-N cut-off of strike-minutes in this half-hour.
3 paying up      orders that traded strictly THROUGH the quote (bought above the ask / sold below the bid) with delta
                 notional ≥ the 1-in-N cut-off of such orders in this half-hour (at-the-quote prints are ~80 % of all
                 orders — they are how the side is labelled, not urgency).
4 new positions  a contract's volume today (whole session, all prints) reaching ratio × its prior-close open interest
                 (OI ≥ min_oi) — the order that crossed, coloured by the side that traded more up to it.
drop crosses     a print at mid with size ≥ the 99.5th percentile of print sizes in this half-hour (previous sessions,
                 ≥ 50 contracts) is a negotiated cross / hedge, not someone paying up.

Baseline: one small JSON per market and day (order counts + the top 400 values per half-hour), written after the
close by the recorder (unusual/<day>_<mkt>.json on the state branch), seeded from the saved days in core/data/unusual.
Score: the same file holds what each flag did that day (SPX/ES/SPY 20 min later in the flag's direction, vs all
orders that day in the same direction) → the running score shown next to each flag.

Colour everywhere: blue = bullish (calls bought / puts sold), magenta = bearish (puts bought / calls sold)."""
from __future__ import annotations

import math
import os
import json
import time

import numpy as np
import pandas as pd

MULT = {"SPX": 100.0, "ES": 50.0, "SPY": 100.0}
DEF = dict(big_rare=10000, pay_rare=1000, burst_k=3.0, burst_win=30, burst_rare=1000,
           new_ratio=1.0, new_min_oi=100, drop_cross=True)
FLAGS = ["big", "burst", "pay", "new"]
NB, TOPK, NDAYS, FWD, MIN_DAYS = 13, 400, 10, 20, 3
SEED_DIR = os.path.join(os.path.dirname(__file__), "data", "unusual")


def _spx_frame(rec, exp: str) -> pd.DataFrame:
    from .orderflow import _spx_map
    df = rec._all_prints()
    keep = (df["exp"].astype(str).values == exp) & (df["ev_type"].astype(str).values != "2")
    if "valid" in df:
        keep &= df["valid"].values.astype(bool)
    d = df[keep]
    if not len(d):
        return pd.DataFrame()
    ts = d["ts_ms"].values.astype("int64")
    S = d["spot"].values.astype(float) if "spot" in d else np.full(len(d), np.nan)
    miss = ~np.isfinite(S)
    if miss.any():
        mp = _spx_map(rec)
        S[miss] = pd.Series((ts[miss] // 60000) * 60000).map(mp).values.astype(float)
        still = ~np.isfinite(S)
        if still.any():
            S[still] = rec.spot_now()[0]
    oi = getattr(rec, "oi", {}) or {}
    sym = d["sym"]
    return pd.DataFrame({"ts_ms": ts, "sym": sym.values,
                         "strike": d["strike"].values.astype(float), "cp": d["cp"].values.astype(float),
                         "px": d["px"].values.astype(float), "size": d["size"].values.astype(float),
                         "bid": d["bid"].values.astype(float), "ask": d["ask"].values.astype(float),
                         "aggr": np.nan_to_num(d["aggr"].values.astype(float)),
                         "sl": ~d["spread_leg"].values.astype(bool) if "spread_leg" in d else np.ones(len(d), bool),
                         "eth": d["eth"].values.astype(bool) if "eth" in d else np.zeros(len(d), bool),
                         "S": S, "oi": pd.Series(sym.values).map(lambda s: oi.get(str(s), np.nan)).values.astype(float)})


def _x_frame(rec, mkt: str) -> pd.DataFrame:
    d = rec.xprints_df(mkt) if hasattr(rec, "xprints_df") else pd.DataFrame()
    if not len(d):
        return pd.DataFrame()
    d = d[d["valid"].values.astype(bool)]
    oi = getattr(rec, "oi", {}) or {}
    sym = d["sym"] if "sym" in d else pd.Series([""] * len(d))
    return pd.DataFrame({"ts_ms": d["ts_ms"].values.astype("int64"), "sym": sym.values,
                         "strike": d["strike"].values.astype(float), "cp": d["cp"].values.astype(float),
                         "px": d["px"].values.astype(float), "size": d["size"].values.astype(float),
                         "bid": d["bid"].values.astype(float), "ask": d["ask"].values.astype(float),
                         "aggr": np.nan_to_num(d["aggr"].values.astype(float)), "sl": ~d["spread_leg"].values.astype(bool),
                         "eth": d["eth"].values.astype(bool), "S": d["und"].values.astype(float),
                         "oi": pd.Series(sym.values).map(lambda s: oi.get(str(s), np.nan)).values.astype(float)})


def frame(rec, mkt: str, exp: str) -> pd.DataFrame:
    """All of today's prints for the market (whole session, sorted). v0.41.2: NOT cached — a full copy of the day's
    prints kept on the recorder cost hundreds of MB (23 Nov: memory 2.3 GB by 14:00, app gone before the close copy).
    Only the small result is cached (see result())."""
    if hasattr(rec, "_unu_frames"):                      # drop a copy left by v0.41.0
        try:
            del rec._unu_frames
        except Exception:                                # noqa: BLE001
            pass
    f = _spx_frame(rec, exp) if mkt == "SPX" else _x_frame(rec, mkt)
    if len(f):
        f = f.sort_values("ts_ms", kind="stable").reset_index(drop=True)
        for c in ("strike", "cp", "px", "size", "bid", "ask", "aggr", "S", "oi"):
            f[c] = f[c].astype("float32")
    return f


def result(rec, mkt: str, exp: str, day, legs: str, on: list, p: dict, x_exp: str = ""):
    """v0.44.0: flags against the previous sessions (cuts). v0.41.2: (flagged orders only, bursts), cached on the store size + settings — a few hundred rows, not the tape."""
    n = len(rec._all_prints()) if mkt == "SPX" else len(rec.xprints_df(mkt)) if hasattr(rec, "xprints_df") else 0
    hist = history(mkt, str(pd.Timestamp(day).date()))
    cut = cuts(hist, legs, p)
    key = (mkt, exp, x_exp, str(day), n, len(getattr(rec, "oi", {}) or {}), legs, tuple(on), tuple(sorted(p.items())),
           len(hist), tuple(d.get("day") for d in hist))
    c = getattr(rec, "_unu_res", {}) or {}
    if mkt in c and c[mkt][0] == key:
        return c[mkt][1]
    f = frame(rec, mkt, exp)
    g, bu = detect(f, mkt, day, legs, on, p, exp=x_exp, cut=cut)
    del f
    if len(g):
        g = g[g[[k for k in FLAGS if k in g]].any(axis=1)].copy()
    c = dict(c)
    c[mkt] = (key, (g, bu))
    try:
        rec._unu_res = c
    except Exception:                                    # noqa: BLE001
        pass
    return g, bu


def _t0(day) -> int:
    from .timeutil import ET
    return int(pd.Timestamp(pd.Timestamp(day).normalize() + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)


def _bk(ts_ms, t0):
    return np.clip(((np.asarray(ts_ms, "int64") - t0) // 60000) // 30, 0, NB - 1).astype(int)


def _prep(f: pd.DataFrame, day, legs: str, p: dict, new_on: bool, cross_cut=None):
    """RTH prints of `day` with side / bull / paid-through / new-position columns; crosses dropped against the
    previous sessions' size cut-off of the same half-hour (never against today's own distribution)."""
    t0 = _t0(day)
    t1 = t0 + int(6.5 * 3600 * 1000)
    f = f.copy()
    f["bull"] = np.sign(f["aggr"].values) * np.sign(f["cp"].values)
    f["new"] = False
    f["new_bull"] = 0.0
    if new_on:                                           # whole session (incl. overnight), all prints — causal
        oi = f["oi"].values
        cum = f.groupby("sym", observed=True)["size"].cumsum().values
        lim = p["new_ratio"] * oi
        f["new"] = (oi >= p["new_min_oi"]) & (cum >= lim) & (cum - f["size"].values < lim)
        f["new_bull"] = np.sign((f["bull"] * f["size"]).groupby(f["sym"], observed=True).cumsum().values)
    rth = (f["ts_ms"].values >= t0) & (f["ts_ms"].values < t1) & ~f["eth"].values
    f = f[rth]
    if legs == "single-leg":
        f = f[f["sl"].values]
    f = f[f["aggr"].values != 0]
    if p.get("drop_cross") and len(f) and cross_cut is not None:
        px_, b_, a_ = f["px"].values, f["bid"].values, f["ask"].values
        at_mid = np.abs(px_ - (a_ + b_) / 2) <= np.maximum((a_ - b_) * 0.1, 0.0001)
        cut = np.nan_to_num(np.asarray(cross_cut, float)[_bk(f["ts_ms"].values, t0)], nan=np.inf)
        f = f[~(at_mid & (f["size"].values >= np.maximum(cut, 50.0)))]
    if p.get("drop_mid"):                                # v0.42.0: ignore prints traded inside the spread
        f = f[~((f["px"].values > f["bid"].values + 1e-9) & (f["px"].values < f["ask"].values - 1e-9))]
    if len(f):
        px, b, a, ag = f["px"].values, f["bid"].values, f["ask"].values, f["aggr"].values
        f["paid"] = ((ag > 0) & (px > a + 1e-9)) | ((ag < 0) & (px < b - 1e-9))     # strictly THROUGH the quote
        f["side"] = np.sign(ag)
        f["sec"] = f["ts_ms"].values // 1000
        f["pv"] = px * f["size"].values
    return f, t0


def _orders(f: pd.DataFrame, mkt: str, day, exp: str = "") -> pd.DataFrame:
    from .timeutil import ET
    from .orderflow import implied_delta
    g = f.groupby([f["sym"].astype(str).values, f["side"].values, f["sec"].values], sort=False)
    o = g.agg(ts_ms=("ts_ms", "first"), sym=("sym", "first"), strike=("strike", "first"), cp=("cp", "first"),
              aggr=("side", "first"), size=("size", "sum"), pv=("pv", "sum"), S=("S", "first"), n=("px", "size"),
              paid=("paid", "max"), new=("new", "max"), oi=("oi", "first"), new_bull=("new_bull", "last"), bull=("bull", "first"))
    o = o.reset_index(drop=True)
    o["px"] = o["pv"] / o["size"].clip(lower=1)
    end = pd.Timestamp(f"{exp or pd.Timestamp(day).date()} 16:00").tz_localize(ET).value // 10**6
    T = np.maximum(end - o["ts_ms"].values, 60_000) / (365.25 * 86400e3)
    o["d"] = implied_delta(o["px"].values, o["S"].values, o["strike"].values, T, o["cp"].values)
    o["mult"] = MULT[mkt]
    o["prem"] = o["pv"] * o["mult"]
    o["dn"] = o["d"] * o["size"] * o["mult"] * o["S"]
    return o.sort_values("ts_ms", kind="stable").reset_index(drop=True)


def _strike_minutes(f: pd.DataFrame, t0: int, k: float, win: int):
    """per strike-minute: volume, bull volume, multiple vs own rolling median (prior `win` min), and the gate
    (> k × own median and > k × the market's typical busy strike-minute). All look-back only."""
    m = (f["ts_ms"].values - t0) // 60000
    V = pd.DataFrame({"m": m, "k": f["strike"].values, "v": f["size"].values,
                      "b": f["bull"].values * f["size"].values, "S": f["S"].values})
    A = V.groupby(["m", "k"]).agg(v=("v", "sum"), b=("b", "sum"), S=("S", "mean")).reset_index()
    P = A.pivot(index="m", columns="k", values="v").reindex(range(int(A["m"].max()) + 1)).fillna(0.0)
    med = P.rolling(win, min_periods=min(5, win)).median().shift(1)
    busy = P.where(P > 0).stack().dropna().groupby(level=0).median().reindex(P.index).expanding().median().shift(1)
    R = P / med.clip(lower=1.0)
    ok = (P > k * med) & (P.gt(k * busy, axis=0)) & (P > 0)
    return A, P, med, R, ok


def cuts(hist: list, legs: str, p: dict) -> dict | None:
    """Pool the previous sessions' half-hour tails → the cut-off of each flag per half-hour (NaN = no data)."""
    if len(hist or []) < MIN_DAYS:
        return None
    L = "sl" if legs == "single-leg" else "al"

    def pool(key, rare):
        out = np.full(NB, np.nan)
        for b in range(NB):
            n = 0
            vals = []
            for d in hist:
                x = (d.get(L) or {}).get(key)
                if not x:
                    continue
                n += int(x[b][0])
                vals += x[b][1]
            if n and vals:
                v = np.sort(np.asarray(vals, float))[::-1]
                out[b] = v[min(max(1, math.ceil(n / float(rare))), len(v)) - 1]
        return out
    cr = np.full(NB, np.nan)
    for b in range(NB):
        xs = [(d.get(L) or {}).get("cross", [None] * NB)[b] for d in hist]
        xs = [x for x in xs if x is not None]
        if xs:
            cr[b] = float(np.median(xs))
    return dict(big=pool("dn", p["big_rare"]), pay=pool("pay", p["pay_rare"]), burst=pool("R", p["burst_rare"]),
                cross=cr, n=len(hist))


def detect(f: pd.DataFrame, mkt: str, day: pd.Timestamp, legs: str, on: list, p: dict, exp: str = "", cut: dict | None = None):
    """→ (orders with flag columns, bursts frame) for RTH of `day`. Only flags in `on` are computed. `cut` = cuts()
    from the previous sessions; without it big / paying up / bursts stay off (nothing to compare with yet)."""
    if not len(f):
        return pd.DataFrame(), pd.DataFrame()
    f, t0 = _prep(f, day, legs, p, "new" in on, cut["cross"] if cut else None)
    if not len(f):
        return pd.DataFrame(), pd.DataFrame()
    o = _orders(f, mkt, day, exp)
    ob = _bk(o["ts_ms"].values, t0)
    for k in ("big", "burst", "pay"):
        o[k] = False
    if "new" not in on:
        o["new"] = False
    if cut is not None:
        if "big" in on:
            o["big"] = o["dn"].values >= np.nan_to_num(cut["big"][ob], nan=np.inf)
        if "pay" in on:
            o["pay"] = o["paid"].values & (o["dn"].values >= np.nan_to_num(cut["pay"][ob], nan=np.inf))
    bursts = pd.DataFrame()
    if "burst" in on and cut is not None:
        A, P, med, R, ok = _strike_minutes(f, t0, float(p["burst_k"]), int(p["burst_win"]))
        rc = pd.Series(np.nan_to_num(cut["burst"], nan=np.inf)[np.clip(P.index.values // 30, 0, NB - 1)], index=P.index)
        ok = ok & R.ge(rc, axis=0)
        r = R.where(ok).stack().dropna()
        if len(r):
            bursts = A.set_index(["m", "k"]).loc[r.index].reset_index()
            bursts["med"] = [med.at[mm, kk] for mm, kk in zip(bursts["m"], bursts["k"])]
            bursts["ts_ms"] = t0 + bursts["m"] * 60000
            om = (o["ts_ms"].values - t0) // 60000
            inb = pd.MultiIndex.from_arrays([om, o["strike"].values]).isin(
                pd.MultiIndex.from_arrays([bursts["m"].values, bursts["k"].values]))
            if inb.any():                                # table: the biggest order in each burst minute
                top = o[inb].assign(_m=om[inb]).sort_values("dn").groupby(["_m", "strike"]).tail(1).index
                o.loc[top, "burst"] = True
    return o, bursts


# ── baseline + score: one small file per market and day ─────────────────────────────────────────────────────────────
def _tail(vals, b, mask=None):
    out = []
    for i in range(NB):
        m = (b == i) if mask is None else ((b == i) & mask)
        v = vals[m]
        out.append([int(m.sum()), [round(float(x), 2) for x in np.sort(v)[::-1][:TOPK]]])
    return out


def summary(f: pd.DataFrame, mkt: str, day, exp: str = "", hist: list | None = None) -> dict:
    """One day → its half-hour tails (for future cut-offs) + what each flag did today at default settings, judged
    against the PREVIOUS sessions only (`hist`)."""
    out = {"day": str(pd.Timestamp(day).date()), "mkt": mkt, "v": 1}
    for legs, L in (("single-leg", "sl"), ("all", "al")):
        p = dict(DEF, drop_mid=False)
        g, t0 = _prep(f, day, legs, p, False, None)
        if not len(g):
            continue
        sz = g["size"].values
        gb = _bk(g["ts_ms"].values, t0)
        cross = [float(np.percentile(sz[gb == i], 99.5)) if (gb == i).sum() >= 200 else None for i in range(NB)]
        cut = cuts(hist or [], legs, p)
        g2, _ = _prep(f, day, legs, p, False, cut["cross"] if cut else None)
        o = _orders(g2, mkt, day, exp)
        ob = _bk(o["ts_ms"].values, t0)
        A, P, med, R, ok = _strike_minutes(g2, t0, float(p["burst_k"]), int(p["burst_win"]))
        Rs = R.where(P > 0).stack().dropna()
        rb = np.clip(Rs.index.get_level_values(0).values // 30, 0, NB - 1)
        out[L] = {"dn": _tail(o["dn"].values, ob), "pay": _tail(o["dn"].values, ob, o["paid"].values),
                  "R": _tail(Rs.values, rb), "cross": cross}
        if legs == "single-leg":
            out["score"] = _score(f, mkt, day, exp, hist or [])
    return out


def _score(f, mkt, day, exp, hist):
    """What each flag did today (default settings): underlying FWD min later × the flag's direction, minus the same
    for all orders today in that direction (removes the day's drift)."""
    p = dict(DEF, drop_mid=False)
    cut = cuts(hist, "single-leg", p)
    if cut is None:
        return {}
    o, bu = detect(f, mkt, day, "single-leg", FLAGS, p, exp=exp, cut=cut)
    if not len(o):
        return {}
    t0 = _t0(day)
    m = ((o["ts_ms"].values - t0) // 60000).astype(int)
    S = pd.Series(o["S"].values, index=m).groupby(level=0).median().reindex(range(0, 391)).ffill()
    fw = S.reindex(m + FWD).values - S.reindex(m).values
    d = np.where(o["bull"].values > 0, 1.0, -1.0)
    base = {s: np.nanmean(fw[d == s]) for s in (1.0, -1.0)}
    res = {}
    for k in FLAGS:
        if k == "burst":
            if not len(bu):
                res[k] = {"n": 0}
                continue
            mm = bu["m"].values.astype(int)
            dd = np.where(bu["b"].values > 0, 1.0, -1.0)
            mv = (S.reindex(mm + FWD).values - S.reindex(mm).values) * dd - np.array([base[x] * x for x in dd])
        else:
            sel = o[k].values.astype(bool)
            dd = (np.where(o["new_bull"].values > 0, 1.0, -1.0) if k == "new" else d)[sel]
            mv = fw[sel] * dd - np.array([base[x] * x for x in dd])
        mv = mv[np.isfinite(mv)]
        res[k] = {"n": int(len(mv)), "edge": round(float(mv.mean()), 2) if len(mv) else None,
                  "hit": round(float((mv > 0).mean()), 3) if len(mv) else None}
    return res


_hist_cache: dict = {}


def history(mkt: str, today: str, n: int = NDAYS) -> list:
    """The last `n` sessions before `today` for `mkt`: state branch (written after each close) + the shipped seed."""
    key = (mkt, today)
    c = _hist_cache.get(key)
    if c is not None and time.time() - c[0] < 3600:
        return c[1]
    days: dict = {}
    try:
        for fn in sorted(os.listdir(SEED_DIR)):
            if fn.endswith(f"_{mkt}.json") and fn[:10] < today:
                days[fn[:10]] = json.load(open(os.path.join(SEED_DIR, fn)))
    except Exception:                                    # noqa: BLE001
        pass
    try:
        from . import state as ST
        names = [x for x in ST.list_dir("unusual") if x.endswith(f"_{mkt}.json") and x[:10] < today]
        for x in sorted(names)[-n:]:
            if x[:10] not in days or days[x[:10]].get("src") != "state":
                j = ST.read_file(f"unusual/{x}")
                if j:
                    j["src"] = "state"
                    days[x[:10]] = j
    except Exception:                                    # noqa: BLE001
        pass
    out = [days[k] for k in sorted(days)[-n:]]
    _hist_cache[key] = (time.time(), out)
    return out


def running_score(hist: list) -> dict:
    """{flag: (sessions with ≥3 flags, sessions positive, total n, mean of daily edges, pooled hit)}"""
    res = {}
    for k in FLAGS:
        rows = [d["score"][k] for d in hist if (d.get("score") or {}).get(k, {}).get("n", 0) >= 3]
        if not rows:
            res[k] = None
            continue
        n = sum(r["n"] for r in rows)
        res[k] = (len(rows), sum(1 for r in rows if (r["edge"] or 0) > 0), n,
                  float(np.mean([r["edge"] for r in rows])), float(sum(r["hit"] * r["n"] for r in rows) / n))
    return res


def save_day(rec, day: str) -> list:
    """After the close (recorder thread): write today's baseline + score for SPX / ES / SPY to the state branch."""
    from . import state as ST
    done = []
    exp = str(rec.exps[0]) if getattr(rec, "exps", None) else day
    for mkt in ("SPX", "ES", "SPY"):
        try:
            f = frame(rec, mkt, exp)
            if not len(f):
                continue
            xe = exp if mkt == "SPX" else (getattr(rec, "xinfo", {}) or {}).get(mkt, {}).get("exp", "")
            j = summary(f, mkt, pd.Timestamp(day), exp=xe, hist=history(mkt, day))
            del f
            ST.save_file(f"unusual/{day}_{mkt}.json", j, f"unusual baseline {day} {mkt}", wait=True)
            done.append(mkt)
        except Exception:                                # noqa: BLE001
            continue
    _hist_cache.clear()
    return done


def table(f: pd.DataFrame, on: list, mkt: str, n: int, sort: str, min_flags: int) -> pd.DataFrame:
    if not len(f) or not on:
        return pd.DataFrame()
    nf = f[on].sum(1)
    t = f[nf >= max(1, min_flags)].copy()
    if not len(t):
        return pd.DataFrame()
    t["nf"] = nf[t.index]
    from .timeutil import ET
    lab = {"big": "big", "burst": "burst", "pay": "paying up", "new": "new pos"}
    t = t.sort_values({"delta $": "dn", "premium": "prem", "size": "size", "time": "ts_ms"}[sort], ascending=False)
    t = t.head(n)
    return pd.DataFrame({
        "mkt": mkt,
        "time": pd.to_datetime(t["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.strftime("%H:%M:%S").values,
        "strike": t["strike"].values, "C/P": np.where(t["cp"].values > 0, "C", "P"),
        "size": t["size"].astype(int).values, "price": t["px"].round(2).values,
        "side": np.where(t["aggr"].values > 0, "bought", np.where(t["aggr"].values < 0, "sold", "mid")),
        "read": np.where(t["bull"].values > 0, "bullish", np.where(t["bull"].values < 0, "bearish", "—")),
        "premium $": t["prem"].round(0).astype(int).values, "delta $M": (t["dn"] / 1e6).round(1).values,
        "vs spot": (t["strike"] - t["S"]).round(1).values,
        "flags": [" · ".join(lab[k] for k in on if r[k]) for _, r in t[on].iterrows()],
        "_ts": t["ts_ms"].values, "_S": t["S"].values})


_LB = {"big": "big orders", "burst": "bursts", "pay": "paying up", "new": "new positions"}


def status_line(mkt: str, today: str, on: list, legs: str, p: dict) -> str:
    """Baseline state + each switched-on flag's running score (what it did over the previous sessions)."""
    hist = history(mkt, today)
    if not on:
        return ""
    head = f"{mkt} baseline: {len(hist)} previous session(s)"
    if cuts(hist, legs, p) is None:
        return (head + f" — big / paying up / bursts start once {MIN_DAYS} are saved (new positions works now)")
    rs = running_score(hist)
    parts = []
    for k in on:
        r = rs.get(k)
        if r is None:
            parts.append(f"{_LB[k]}: no score yet")
        else:
            nd, pos, n, e, h = r
            parts.append(f"{_LB[k]}: {e:+.1f} pts / {FWD} min vs all orders · {pos}/{nd} sessions + · {h:.0%} right · n {n}")
    return head + " · track record (default settings, single-leg; + = went the flag's way): " + " │ ".join(parts)
