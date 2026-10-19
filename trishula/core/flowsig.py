"""AG-REV signal engine: port of SPXFlow v2.10 (thinkorswim RTD workbook, VBA module
SPXFlow.bas), rebuilt on the tastytrade tape.

What changes versus the workbook (better data, same rules):
  · aggr: SPXFlow inferred side from AVP/mid every 5 s (aggr = (px − mid)/half, clipped ±1).
    Here every print carries its own bid/ask at the trade + aggressorSide, so aggr is the
    five-bucket classifier (ABOVE_ASK/ASK +1 · BID/BELOW_BID −1 · MID by aggressorSide).
  · prem = aggr · size · px · 100 · dn = aggr · size · Δ · 100 · S · bull = prem × (+1 call / −1 put)
    — exactly the workbook formulas, applied per print instead of per 5-s volume delta.
  · walls: CW/PW = strike of max call / put OI in the grid (workbook cwOIk / pwOIk).
  · candles: SPX 1-minute candles (the workbook built OHLC from 5-s spot samples).
Rules (EvaluateBucketRow / EvaluateSignals / Fire / UpdateOpenSignals) are line-for-line:
  Q1 call sweep · Q3 put sweep · Q2 puts sold into dip · Q4 calls sold into strength ·
  Q5 flow divergence at new low/high · W wall + flow. ("B" does not exist in v2.10.)
Every call recomputes from the tape, so the workbook's REPLAY SIGNALS button is automatic:
change any config and the whole day re-scores.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

ZWIN = 30
ZMIN = 10
CFG_DEFAULT = dict(BucketMin=1, SkipOpenMin=10, ZThresh=2.5, MinPrem=250000.0, WallTol=3.0, CooldownMin=5,
                   Q1Target=20.0, Q1Stop=20.0, Q2Target=20.0, Q2Stop=20.0, Q3Target=20.0, Q3Stop=20.0,
                   Q4Target=20.0, Q4Stop=20.0, Q5Target=None, Q5Stop=20.0, WTarget=30.0, WStop=15.0,
                   StrikesEachSide=40)
FAMILIES = ["Q1", "Q2", "Q3", "Q4", "Q5", "W"]
DESCR = {"Q1": "call sweep (bought calls, z-spike)", "Q2": "puts sold into dip (below MA)",
         "Q3": "put sweep (bought puts, z-spike)", "Q4": "calls sold into strength (above MA)",
         "Q5": "divergence: new low + flow higher low / new high + flow lower high",
         "W": "price at OI wall + flow in the bounce direction"}


def flow_rows(p: pd.DataFrame, spot_now: float) -> pd.DataFrame:
    """Per-print workbook quantities (prem, dn, bull, dealer gamma $/1%)."""
    if p is None or p.empty:
        return pd.DataFrame()
    d = p.copy()
    s = d["spot"].fillna(spot_now) if "spot" in d else pd.Series(spot_now, index=d.index)
    side = np.where(d["cp"] == 1, 1.0, -1.0)
    d["prem"] = d["aggr"] * d["size"] * d["px"] * 100.0
    d["dn"] = d["aggr"] * d["size"] * d["delta"].fillna(0) * 100.0 * s
    d["bull"] = d["prem"] * side
    d["dgam"] = -d["aggr"] * d["size"] * d["gamma"].fillna(0) * 100.0 * s * s * 0.01   # DealerGamma
    d["cprem"] = np.where(d["cp"] == 1, d["prem"], 0.0)
    d["pprem"] = np.where(d["cp"] == -1, d["prem"], 0.0)
    return d


def walls(chain: pd.DataFrame, spot: float, n_each: int):
    """CW / PW = strike of max call / put OI inside the grid (workbook cwOIk / pwOIk)."""
    if chain is None or chain.empty or not spot == spot:
        return None, None
    c = chain[(chain["strike"] - spot).abs() <= n_each * 5.0]
    out = []
    for cp in (1, -1):
        x = c[(c["cp"] == cp) & c["oi"].notna()]
        out.append(float(x.loc[x["oi"].idxmax(), "strike"]) if len(x) and x["oi"].max() > 0 else None)
    return out[0], out[1]


def buckets(d: pd.DataFrame, candles: pd.DataFrame, day: dt.date, nmin: int, cw, pw) -> pd.DataFrame:
    """Workbook Buckets sheet: one row per BucketMin bar of the RTH session."""
    from .timeutil import ET
    if candles is None or candles.empty:
        return pd.DataFrame()
    c = candles.copy()
    c["t"] = pd.to_datetime(c["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    c = c[(c["t"].dt.date == day) & (c["t"].dt.time >= dt.time(9, 30)) & (c["t"].dt.time < dt.time(16, 0))]
    if c.empty:
        return pd.DataFrame()
    rule = f"{max(1, int(nmin))}min"
    c["b"] = c["t"].dt.floor(rule)
    bk = c.groupby("b").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                            close=("close", "last")).reset_index().rename(columns={"b": "ts"})
    if d is not None and len(d):
        f = d.copy()
        f["b"] = f["ts"].dt.floor(rule)
        f = f[f["b"].isin(bk["ts"])]
        g = f.groupby("b")[["cprem", "pprem", "dn", "bull"]].sum().reset_index().rename(columns={"b": "ts"})
        bk = bk.merge(g, on="ts", how="left")
    for col in ("cprem", "pprem", "dn", "bull"):
        if col not in bk:
            bk[col] = 0.0
        bk[col] = bk[col].fillna(0.0)
    bk["cumdn"] = bk["dn"].cumsum()
    bk["cumbull"] = bk["bull"].cumsum()
    bk["cw"], bk["pw"] = cw, pw
    bk["end"] = bk["ts"] + pd.Timedelta(minutes=max(1, int(nmin)))
    return bk


def _zlast(x: np.ndarray, sgn: float) -> float:
    v = np.clip(sgn * x, 0, None)
    mean = v.mean(); var = (v * v).mean() - mean * mean
    if var < 1e-9:
        return 0.0
    return float((v[-1] - mean) / np.sqrt(var))


def evaluate(bk: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, list]:
    """Rolling stats per bucket + the six rules. Returns (buckets with MA/z, raw fires)."""
    if bk.empty:
        return bk, []
    bk = bk.copy()
    for col in ("ma", "zcb", "zcs", "zpb", "zps"):
        bk[col] = np.nan
    fires, last_fire = [], {}
    zT, minP, tol = float(cfg["ZThresh"]), float(cfg["MinPrem"]), float(cfg["WallTol"])
    cool = pd.Timedelta(minutes=float(cfg["CooldownMin"]))
    for r in range(len(bk)):
        cnt_total = r + 1
        if cnt_total < ZMIN:
            continue
        w = bk.iloc[max(0, r - ZWIN + 1): r + 1]
        ma = float(w["close"].mean())
        zcb, zcs = _zlast(w["cprem"].values, 1), _zlast(w["cprem"].values, -1)
        zpb, zps = _zlast(w["pprem"].values, 1), _zlast(w["pprem"].values, -1)
        bk.iloc[r, bk.columns.get_indexer(["ma", "zcb", "zcs", "zpb", "zps"])] = [ma, zcb, zcs, zpb, zps]
        row = bk.iloc[r]
        t_end = row["end"]
        sm = (t_end - t_end.normalize()).total_seconds() / 60 - 570
        if 0 <= sm < float(cfg["SkipOpenMin"]):
            continue
        entry = float(row["close"])
        hi, lo, cl = float(row["high"]), float(row["low"]), float(row["close"])
        cp_, pp_, bull = float(row["cprem"]), float(row["pprem"]), float(row["bull"])

        def fire(nm, dirn, why):
            if nm != "W" and nm in last_fire and t_end - last_fire[nm] < cool:
                return
            last_fire[nm] = t_end
            fires.append(dict(ts=t_end, name=nm, dir=dirn, entry=entry, why=why, bk=r, hi=hi, lo=lo))
        if cp_ >= minP and zcb >= zT:
            fire("Q1", 1, f"call sweep ${cp_ / 1e6:.1f}M z{zcb:.1f}")
        if pp_ >= minP and zpb >= zT:
            fire("Q3", -1, f"put sweep ${pp_ / 1e6:.1f}M z{zpb:.1f}")
        if -pp_ >= minP and zps >= zT and cl < ma:
            fire("Q2", 1, f"puts sold into dip ${-pp_ / 1e6:.1f}M")
        if -cp_ >= minP and zcs >= zT and cl > ma:
            fire("Q4", -1, f"calls sold into strength ${-cp_ / 1e6:.1f}M")
        if len(w) >= ZMIN + 1:
            prev = w.iloc[:-1]
            iMin = prev["low"].idxmin(); iMax = prev["high"].idxmax()
            if lo < float(prev["low"].min()) and float(row["cumdn"]) > float(bk.loc[iMin, "cumdn"]):
                fire("Q5", 1, "new low, flow higher low")
            if hi > float(prev["high"].max()) and float(row["cumdn"]) < float(bk.loc[iMax, "cumdn"]):
                fire("Q5", -1, "new high, flow lower high")
        pwk, cwk = row["pw"], row["cw"]
        if pwk and abs(lo - float(pwk)) <= tol and bull > 0:
            fire("W", 1, f"put wall {float(pwk):,.0f} + bullish flow")
        if cwk and abs(hi - float(cwk)) <= tol and bull < 0:
            fire("W", -1, f"call wall {float(cwk):,.0f} + bearish flow")
    return bk, fires


def score(fires: list, candles1m: pd.DataFrame, cfg: dict, session_over: bool) -> pd.DataFrame:
    """Workbook UpdateOpenSignals / CloseAllOpenSignals on the 1-min path after entry.
    Inside one bar where both target and stop are reachable, the stop is taken (conservative —
    the workbook ticked every 5 s and took whichever came first)."""
    cols = ["ts", "name", "dir", "entry", "target", "stop", "status", "exit_ts", "pnl", "why", "bk", "hi", "lo"]
    if not fires:
        return pd.DataFrame(columns=cols)
    c = candles1m.sort_values("t")
    out = []
    for f in fires:
        tgt = cfg.get(f"{f['name']}Target"); stp = float(cfg.get(f"{f['name']}Stop") or 20.0)
        path = c[c["t"] >= f["ts"]]
        status, exit_ts, pnl = "open", None, 0.0
        for _, b in path.iterrows():
            fav = f["dir"] * ((b["high"] if f["dir"] > 0 else b["low"]) - f["entry"])
            adv = f["dir"] * ((b["low"] if f["dir"] > 0 else b["high"]) - f["entry"])
            if adv <= -stp:
                status, exit_ts, pnl = "stop", b["t"], -stp
                break
            if tgt is not None and fav >= float(tgt):
                status, exit_ts, pnl = "target", b["t"], float(tgt)
                break
            pnl = f["dir"] * (b["close"] - f["entry"])
        if status == "open" and session_over and len(path):
            status, exit_ts = "eod", path["t"].iloc[-1]
        out.append(dict(f, target=tgt, stop=stp, status=status, exit_ts=exit_ts, pnl=pnl))
    return pd.DataFrame(out)[cols]


def stats_line(sig: pd.DataFrame, cfg: dict) -> str:
    if sig is None or sig.empty:
        return "no signals yet"
    parts = []
    for nm in FAMILIES:
        s = sig[sig["name"] == nm]
        if s.empty:
            continue
        tgt = cfg.get(f"{nm}Target")
        parts.append(f"{nm} {s['pnl'].sum():+.1f} {int((s['status'] == 'target').sum())}/{len(s)} won "
                     f"{'-' if tgt is None else f'{float(tgt):g}'}/{float(cfg.get(f'{nm}Stop') or 0):g}")
    return "    ".join(parts)


# ── heat grid + projection + profile (workbook WriteGridColumns / WriteProjection / WriteProfile) ──
def heat_grid(d: pd.DataFrame, day: dt.date, strikes: np.ndarray):
    """Cumulative dealer gamma from flow per strike per minute (gamma mode), each column scaled
    by its own max (workbook ScaleVal(heatCum/mx) × HEAT_DISP)."""
    if d is None or d.empty or not len(strikes):
        return None
    f = d[d["ts"].dt.date == day].copy()
    if f.empty:
        return None
    f["m"] = f["ts"].dt.floor("1min")
    g = f.groupby(["m", "strike"])["dgam"].sum().unstack(fill_value=0.0).sort_index()
    g = g.reindex(columns=strikes, fill_value=0.0).cumsum()
    mx = g.abs().max(axis=1).replace(0, np.nan)
    return (g.div(mx, axis=0) * 2.0).fillna(0.0)


def projection(pos: pd.DataFrame, spot: float, now: dt.datetime, expiry: dt.datetime, strikes, step_min=5):
    """Positions held fixed (pos = −Σ aggr·size per leg), gamma re-evaluated at future times,
    dimmed ×0.6 — the decay picture right of now (workbook WriteProjection)."""
    from .terrain import bs_gamma
    if pos is None or pos.empty or now >= expiry:
        return None
    cols, mins = [], int((expiry - now).total_seconds() // 60)
    for c0 in range(1, mins + 1, step_min):
        T = max((expiry - (now + dt.timedelta(minutes=c0))).total_seconds(), 60) / (365 * 86400)
        val = pos["pos"].values * bs_gamma(spot, pos["strike"].values, T, np.where(pos["iv"] > 0, pos["iv"], 0.15))
        v = pd.Series(val * 100 * spot * spot * 0.01).groupby(pos["strike"].values).sum().reindex(strikes, fill_value=0.0)
        mx = float(v.abs().max()) or 1.0
        cols.append((now + dt.timedelta(minutes=c0), (v / mx * 0.6 * 2.0).values))
    return cols
