"""SIGNALS view (v0.18.0, L30 — replaces DT classic). Arrows on the price line, one shape per signal, size = tier.

Every rule is the LOCKED research version (research/l28/l29.py, written 21 Oct before the history arrived) — no
parameter here was fitted on the days it is shown on. The side table carries each signal × tier's record from
research/l29 (20 sessions, 9 of them fresh = never used to design anything) and its verdict:
  edge      fresh-days t ≥ 3 and positive            → filled, bright
  watch     fresh-days t ≥ 2 and positive            → filled, dim
  unproven  everything else                          → hollow
S2 (the 21 Oct caption "loading setup") was negative out of sample → dropped.
S7 "quiet big block" (AG's captions: someone positioned BEFORE the news; 22 Oct 7720P 21 Oct afternoon) was locked
22 Oct and has NO history yet → hollow, to be scored on days after 21 Oct.
"""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from . import dtv2 as V

COOL = 10
HIST = os.path.join(os.path.dirname(__file__), "data", "signal_history.csv")
WF = os.path.join(os.path.dirname(__file__), "data", "signal_wf.csv")       # v0.19 L35 walk-forward result (mixed)
WF_MODE = {"0DTE": os.path.join(os.path.dirname(__file__), "data", "signal_wf_0dte.csv"),
           "0+1DTE": os.path.join(os.path.dirname(__file__), "data", "signal_wf_01dte.csv")}   # v0.19.1 L41
POSITIONS = ["fewer", "middle", "more"]

# code → (name, marker, tiers low→high, what it means)
SIG = {
    "S1": ("aggressive block vs move", "triangle", ["×5", "×10", "×20"],
           "one contract, one minute, ≥ k × its own median minute and ≥ 100 contracts, ≥ 90 % at the ask (or bid), "
           "AGAINST the last 15-min move → fade the move · 0DTE + 1DTE"),
    "S3": ("near-spot flip", "diamond", ["500", "1000", "2000"],
           "calls + puts within ±25 of spot flip net side in a 5-min bucket by ≥ N contracts · fires AT the turn "
           "(may be profit-taking)"),
    "S4": ("DT v2 follow", "arrow", ["2 strikes", "3 strikes", "4 strikes"],
           "≥ N strikes print the same net colour within 3 min (adaptive band) → follow"),
    "S5": ("initiation", "circle", ["5 %", "10 %", "15 %"],
           "10-min net flow ≥ share of volume and price ≥ 4 pts the same way → follow"),
    "S6": ("exhaustion + breadth", "star", ["8 pts", "12 pts", "16 pts"],
           "≥ 5 strikes within 50 pts unusually busy (z > 4 vs own 30 min) after a ≥ N-pt 15-min move → fade"),
    "S7": ("quiet big block", "square", ["1,000", "2,000", "4,000"],
           "one 0DTE/1DTE contract-minute ≥ N contracts and ≥ 10 × its own median, ≥ 90 % one side, while the last "
           "30 min ranged ≤ 15 pts → bought put / sold call = bearish (mirror bullish) · NEW, no history"),
}


def history() -> pd.DataFrame:
    try:
        h = pd.read_csv(HIST)
    except Exception:                                        # noqa: BLE001
        return pd.DataFrame(columns=["code", "tier", "verdict"])
    h["tier"] = h["tier"].astype(str)
    return h


def verdict(h: pd.DataFrame, code: str, tier: str) -> str:
    if code == "S7":
        return "new"
    r = h[(h["code"] == code) & (h["tier"] == tier)]
    return str(r["verdict"].iloc[0]) if len(r) else "unproven"


def cool(series: pd.Series, minutes: int = COOL) -> pd.Series:
    out = pd.Series(0, index=series.index); last = None
    for t, v in series[series != 0].items():
        if last is None or (t - last) >= pd.Timedelta(minutes=minutes):
            out[t] = int(np.sign(v)); last = t
    return out


# ── inputs ──────────────────────────────────────────────────────────────────────
def minute_flow(c1: pd.DataFrame | None, p: pd.DataFrame | None, legs: dict) -> pd.DataFrame:
    """Per contract-minute: t, base, exp, strike, cp, volume, bidv (sold), askv (bought).
    1-minute candles first (uncapped), recorded prints for minutes the candles don't cover yet."""
    cols = ["t", "base", "exp", "strike", "cp", "volume", "bidv", "askv"]
    parts = []
    if c1 is not None and len(c1):
        c = c1.rename(columns={"m": "t", "sym": "base", "size": "volume"})
        if "bidv" not in c:
            c = c.assign(bidv=((c["volume"] - c["net"]) / 2).clip(lower=0), askv=((c["volume"] + c["net"]) / 2).clip(lower=0))
        parts.append(c[["t", "base", "strike", "cp", "volume", "bidv", "askv"]])
    if p is not None and len(p):
        q = p.assign(t=p["ts"].dt.floor("1min"), base=p["sym"].astype(str),
                     askv=np.where(p["aggr"] > 0, p["size"], 0.0), bidv=np.where(p["aggr"] < 0, p["size"], 0.0))
        q = q.groupby(["t", "base"], as_index=False, observed=True).agg(strike=("strike", "first"), cp=("cp", "first"),
                                                                        volume=("size", "sum"), bidv=("bidv", "sum"), askv=("askv", "sum"))
        if parts:
            have = pd.MultiIndex.from_arrays([parts[0]["t"], parts[0]["base"]])
            q = q[~pd.MultiIndex.from_arrays([q["t"], q["base"]]).isin(have)]
        parts.append(q)
    if not parts:
        return pd.DataFrame(columns=cols)
    o = pd.concat(parts, ignore_index=True)
    o["exp"] = o["base"].map(lambda x: (legs.get(x) or ("",))[0])
    return o[cols]


# ── the locked rules (research/l28/l29.py, verbatim logic) ─────────────────────────
def s1_blocks(o, S, rth, k):
    sig = pd.Series(0, index=rth)
    o = o[(o.t >= rth[0]) & (o.t <= rth[-1])].sort_values("t")
    if o.empty:
        return sig
    med = o.groupby("base").volume.transform(lambda v: v.where(v > 0).expanding().median().shift(1))
    big = (o.volume >= np.maximum(100, k * med.fillna(np.inf)))
    bought = o.askv >= 0.9 * o.volume; sold = o.bidv >= 0.9 * o.volume
    d = np.where(bought, np.where(o.cp == 1, 1, -1), np.where(sold, np.where(o.cp == 1, -1, 1), 0))
    m = (big & (d != 0)).values
    e = o[m].assign(d=d[m])
    dp15 = S.diff(15)
    for t, g in e.groupby("t"):
        dd = int(np.sign(g.d.sum()))
        if dd and t in dp15.index and dp15[t] == dp15[t] and np.sign(dp15[t]) == -dd:
            sig[t] = dd
    return cool(sig)


def s7_quiet_block(o, S, rth, size):
    sig = pd.Series(0, index=rth)
    o = o[(o.t >= rth[0]) & (o.t <= rth[-1])].sort_values("t")
    if o.empty:
        return sig
    med = o.groupby("base").volume.transform(lambda v: v.where(v > 0).expanding().median().shift(1))
    big = (o.volume >= np.maximum(size, 10 * med.fillna(np.inf)))
    bought = o.askv >= 0.9 * o.volume; sold = o.bidv >= 0.9 * o.volume
    d = np.where(bought, np.where(o.cp == 1, 1, -1), np.where(sold, np.where(o.cp == 1, -1, 1), 0))
    m = (big & (d != 0)).values
    e = o[m].assign(d=d[m])
    rng30 = S.rolling(30, min_periods=20).max() - S.rolling(30, min_periods=20).min()
    for t, g in e.groupby("t"):
        dd = int(np.sign(g.d.sum()))
        if dd and t in rng30.index and rng30[t] == rng30[t] and rng30[t] <= 15:
            sig[t] = dd
    return cool(sig)


def s3_flip(o0, S, rth, size):
    o = o0[(o0.t >= rth[0]) & (o0.t <= rth[-1])].copy()
    s = pd.Series(0, index=rth)
    if o.empty:
        return s
    o["off"] = o.strike.values - S.reindex(o.t).values
    o = o[o.off.abs() <= 25]
    o["bull"] = np.where(o.cp == 1, 1, -1) * (o.askv - o.bidv)
    b = o.groupby(o.t.dt.floor("5min")).bull.sum()
    b = b.reindex(pd.date_range(rth[0], rth[-1], freq="5min")).fillna(0)
    for i in range(1, len(b)):
        if np.sign(b.iat[i]) != np.sign(b.iat[i - 1]) and abs(b.iat[i]) >= size and np.sign(b.iat[i - 1]) != 0:
            t = b.index[i] + pd.Timedelta(minutes=5)
            if t in s.index:
                s[t] = int(np.sign(b.iat[i]))
    return cool(s)


def frames(o0, rth):
    mt = pd.DataFrame({"m": o0.t, "sym": o0.base, "strike": o0.strike, "cp": o0.cp, "size": o0.volume,
                       "net": o0.askv - o0.bidv})
    return V.minute_frames(mt, rth)


def s6_exhaust(nf, vol, S, rth, pts):
    s = pd.Series(0, index=rth)
    if vol.empty or not len(vol.columns):
        return s
    K = vol.columns.values.astype(float); Sv = S.reindex(vol.index).ffill().values
    N = np.abs(K[None, :] - Sv[:, None]) <= 50
    b = vol.shift(1); med = b.rolling(30, min_periods=10).median(); mad = (b - med).abs().rolling(30, min_periods=10).median()
    Z = ((vol - med) / (1.4826 * mad + 1)).values
    br = pd.Series(((Z > 4) & N).sum(1), index=vol.index).rolling(5, min_periods=1).max()
    dp = S.diff(15)
    s = pd.Series(np.where((br >= 5) & (dp >= pts), -1, np.where((br >= 5) & (dp <= -pts), 1, 0)), index=rth)
    s[s.index < rth[0] + pd.Timedelta(minutes=10)] = 0
    return cool(s)


def compute(o: pd.DataFrame, S: pd.Series, rth: pd.DatetimeIndex, day: dt.date) -> pd.DataFrame:
    """All signals × tiers → rows (t, code, tier, tier_i, d). o: minute_flow of 0DTE + 1DTE."""
    out = []
    e0 = str(day)
    o0 = o[o["exp"] == e0]
    nf, vol = frames(o0, rth)
    runs = {
        "S1": [lambda k=k: s1_blocks(o, S, rth, k) for k in (5, 10, 20)],
        "S3": [lambda n=n: s3_flip(o0, S, rth, n) for n in (500, 1000, 2000)],
        "S4": [lambda n=n: V.follow(V.squares(nf, vol, S), rth, need=n) for n in (2, 3, 4)],
        "S5": [lambda sh=sh: V.initiation(nf, vol, S, share=sh) for sh in (0.05, 0.10, 0.15)],
        "S6": [lambda p_=p_: s6_exhaust(nf, vol, S, rth, p_) for p_ in (8, 12, 16)],
        "S7": [lambda n=n: s7_quiet_block(o, S, rth, n) for n in (1000, 2000, 4000)],
    }
    for code, fns in runs.items():
        for i, fn in enumerate(fns):
            try:
                sg = fn()
            except Exception:                                # noqa: BLE001
                continue
            for t, d in sg[sg != 0].items():
                out.append((t, code, SIG[code][2][i], i, int(d)))
    return pd.DataFrame(out, columns=["t", "code", "tier", "tier_i", "d"])


def top_tier(ev: pd.DataFrame) -> pd.DataFrame:
    """One mark per signal per minute (± 2 min): the highest tier that fired."""
    if ev.empty:
        return ev
    ev = ev.sort_values(["code", "t", "tier_i"])
    keep = []
    for code, g in ev.groupby("code"):
        g = g.sort_values("t")
        cl = (g["t"].diff() > pd.Timedelta(minutes=2)).cumsum()
        for _, h in g.groupby(cl):
            keep.append(h.sort_values("tier_i").iloc[-1])
    return pd.DataFrame(keep).sort_values("t").reset_index(drop=True)


def score(ev: pd.DataFrame, S: pd.Series) -> pd.DataFrame:
    if ev.empty:
        return ev.assign(px=[], fw10=[], fw20=[], fw30=[])
    px = S.reindex(ev["t"]).values
    r = ev.assign(px=px)
    for h in (10, 20, 30):
        r[f"fw{h}"] = (S.shift(-h).reindex(ev["t"]).values - px) * ev["d"].values
    return r


COL = {1: "#2ecc71", -1: "#ff5fd2"}


def figure(ev: pd.DataFrame, S: pd.Series, hist: pd.DataFrame, day: dt.date, h: int = 560):
    import plotly.graph_objects as go
    f = go.Figure()
    f.add_scatter(x=S.index, y=S.values, mode="lines", line=dict(color="#e8ecf2", width=1.6), name="SPX",
                  hovertemplate="SPX %{x|%H:%M} %{y:,.2f}<extra></extra>", showlegend=False)
    size = [12, 17, 24]
    if len(ev):
        rng = float(np.nanmax(S.values) - np.nanmin(S.values)) if S.notna().any() else 20.0
        off = max(2.5, 0.04 * rng)
        for code, g in ev.groupby("code"):
            name, mk, tiers, what = SIG[code]
            for d in (1, -1):
                gg = g[g["d"] == d]
                if gg.empty:
                    continue
                vds = [verdict(hist, code, t) for t in gg["tier"]]
                base = {"triangle": "triangle-up" if d > 0 else "triangle-down", "arrow": "arrow-up" if d > 0 else "arrow-down"}.get(mk, mk)
                sym = [base if v in ("edge", "watch") else base + "-open" for v in vds]
                op = [1.0 if v == "edge" else 0.75 if v == "watch" else 0.95 for v in vds]
                y = S.reindex(gg["t"]).values + (-off if d > 0 else off) * (1 + 0.6 * (list(SIG).index(code) % 3))
                f.add_scatter(x=gg["t"], y=y, mode="markers", name=f"{code} {name}",
                              marker=dict(symbol=sym, size=[size[i] for i in gg["tier_i"]], color=COL[d], opacity=op,
                                          line=dict(width=1.6, color=COL[d])),
                              text=[f"{code} {name} · tier {t} · {'bullish' if d > 0 else 'bearish'} · {v}" for t, v in zip(gg["tier"], vds)],
                              hovertemplate="%{text}<br>%{x|%H:%M}<extra></extra>", showlegend=False)
    f.update_layout(template="plotly_dark", paper_bgcolor="#0b1020", plot_bgcolor="#0b1020", height=h,
                    margin=dict(l=6, r=6, t=30, b=6), hovermode="closest",
                    title=dict(text=f"SIGNALS · {day:%a %d %b} · shape = signal · size = tier · ▲ green bullish / ▼ pink bearish · "
                                    "hollow = no proven edge", font=dict(size=12, color="#c9d1d9"), x=0.01),
                    xaxis=dict(gridcolor="#1c2547", tickformat="%H:%M"), yaxis=dict(gridcolor="#1c2547", side="right", tickformat=",.0f"))
    return f


def table(ev_all: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, (name, mk, tiers, what) in SIG.items():
        for t in tiers:
            today = int(((ev_all["code"] == code) & (ev_all["tier"] == t)).sum()) if len(ev_all) else 0
            r = hist[(hist["code"] == code) & (hist["tier"] == t)] if len(hist) else hist
            if len(r):
                r = r.iloc[0]
                rows.append(dict(signal=f"{code} {name}", tier=t, today=today, verdict=verdict(hist, code, t),
                                 **{"hit % (all)": round(100 * r["right"]), "pts @20 vs random (fresh)": round(r["fresh_edge20"], 2),
                                    "t (fresh)": round(r["fresh_t"], 2), "n fresh": int(r["fresh_n"]), "n all": int(r["n"])}))
            else:
                rows.append(dict(signal=f"{code} {name}", tier=t, today=today, verdict=verdict(hist, code, t)))
    return pd.DataFrame(rows)



# ── v0.19 L35/L35b: one sensitivity slider, walk-forward tested settings ─────────────────────────────────────────
def wf_table(mode: str | None = None) -> pd.DataFrame:
    try:
        w = pd.read_csv(WF_MODE.get(mode, WF) if mode and os.path.exists(WF_MODE.get(mode, "")) else WF)
    except Exception:                                        # noqa: BLE001
        return pd.DataFrame(columns=["code", "position", "pick", "PASS"])
    import ast
    w["pick"] = [ast.literal_eval(x) if isinstance(x, str) and x.strip() else None for x in w["pick"]]
    return w


def picks_for(position: str, wf: pd.DataFrame) -> dict:
    """{code: params} — the setting the walk-forward chose (trained on all days before the last test block)."""
    r = wf[wf["position"] == position]
    return {row.code: row.pick for row in r.itertuples() if row.pick is not None}


def _blocks(o, S, rth, size_k, share, mode, rng_max=None, mult=None):
    sig = pd.Series(0, index=rth)
    o = o[(o.t >= rth[0]) & (o.t <= rth[-1])].sort_values("t")
    if o.empty:
        return sig
    med = o.groupby("base").volume.transform(lambda v: v.where(v > 0).expanding().median().shift(1))
    if mode == "S1":
        big = o.volume >= np.maximum(100, size_k * med.fillna(np.inf)); side = share
    else:
        big = o.volume >= np.maximum(size_k, mult * med.fillna(np.inf)); side = 0.9
    bought = o.askv >= side * o.volume; sold = o.bidv >= side * o.volume
    d = np.where(bought, np.where(o.cp == 1, 1, -1), np.where(sold, np.where(o.cp == 1, -1, 1), 0))
    m = (big & (d != 0)).values
    e = o[m].assign(d=d[m])
    ref = S.diff(15) if mode == "S1" else (S.rolling(30, min_periods=20).max() - S.rolling(30, min_periods=20).min())
    for t, g in e.groupby("t"):
        dd = int(np.sign(g.d.sum()))
        if not dd or t not in ref.index or ref[t] != ref[t]:
            continue
        if (mode == "S1" and np.sign(ref[t]) == -dd) or (mode == "S7" and ref[t] <= rng_max):
            sig[t] = dd
    return cool(sig)


def _s6(nf, vol, S, rth, pts, br):
    s = pd.Series(0, index=rth)
    if vol.empty or not len(vol.columns):
        return s
    K = vol.columns.values.astype(float); Sv = S.reindex(vol.index).ffill().values
    N = np.abs(K[None, :] - Sv[:, None]) <= 50
    b = vol.shift(1); med = b.rolling(30, min_periods=10).median(); mad = (b - med).abs().rolling(30, min_periods=10).median()
    Z = ((vol - med) / (1.4826 * mad + 1)).values
    brs = pd.Series(((Z > 4) & N).sum(1), index=vol.index).rolling(5, min_periods=1).max()
    dp = S.diff(15)
    s = pd.Series(np.where((brs >= br) & (dp >= pts), -1, np.where((brs >= br) & (dp <= -pts), 1, 0)), index=rth)
    s[s.index < rth[0] + pd.Timedelta(minutes=10)] = 0
    return cool(s)


def compute_picks(o, S, rth, day, picks: dict, mode: str = "0DTE") -> pd.DataFrame:
    """Events (t, code, d) for the walk-forward picks of one slider position. mode: "0DTE" = every signal on the 0DTE
    tape only · "0+1DTE" = every signal on the 0DTE + 1DTE tape (v0.19.1 L41)."""
    out = []
    o0 = o[o["exp"] == str(day)] if mode == "0DTE" else o
    o = o0
    nf, vol = frames(o0, rth)
    for code, p in picks.items():
        try:
            if code == "S1":
                sg = _blocks(o, S, rth, p[0], p[1], "S1")
            elif code == "S7":
                sg = _blocks(o, S, rth, p[0], None, "S7", rng_max=p[2], mult=p[1])
            elif code == "S3":
                sg = s3_flip(o0, S, rth, p[0])
            elif code == "S4":
                sg = V.follow(V.squares(nf, vol, S, alpha=p[1]), rth, need=p[0])
            elif code == "S5":
                sg = V.initiation(nf, vol, S, share=p[0], pts=p[1])
            elif code == "S6":
                sg = _s6(nf, vol, S, rth, p[0], p[1])
            else:
                continue
        except Exception:                                    # noqa: BLE001
            continue
        for t, d in sg[sg != 0].items():
            out.append((t, code, int(d)))
    return pd.DataFrame(out, columns=["t", "code", "d"])


def figure_wf(ev: pd.DataFrame, S: pd.Series, wf: pd.DataFrame, position: str, day, show_unproven: bool, h: int = 560):
    import plotly.graph_objects as go
    f = go.Figure()
    f.add_scatter(x=S.index, y=S.values, mode="lines", line=dict(color="#e8ecf2", width=1.6), showlegend=False,
                  hovertemplate="SPX %{x|%H:%M} %{y:,.2f}<extra></extra>")
    ok = {r.code: bool(r.PASS) for r in wf[wf["position"] == position].itertuples()}
    n_hidden = 0
    if len(ev):
        rng = float(np.nanmax(S.values) - np.nanmin(S.values)) if S.notna().any() else 20.0
        off = max(2.5, 0.04 * rng)
        for code, g in ev.groupby("code"):
            name, mk, _, _ = SIG[code]
            proven = ok.get(code, False)
            if not proven and not show_unproven:
                n_hidden += len(g); continue
            for d in (1, -1):
                gg = g[g["d"] == d]
                if gg.empty:
                    continue
                base = {"triangle": "triangle-up" if d > 0 else "triangle-down", "arrow": "arrow-up" if d > 0 else "arrow-down"}.get(mk, mk)
                y = S.reindex(gg["t"]).values + (-off if d > 0 else off) * (1 + 0.6 * (list(SIG).index(code) % 3))
                f.add_scatter(x=gg["t"], y=y, mode="markers", showlegend=False,
                              marker=dict(symbol=base if proven else base + "-open", size=17 if proven else 12,
                                          color=COL[d], line=dict(width=1.6, color=COL[d])),
                              text=[f"{code} {name} · {'bullish' if d > 0 else 'bearish'} · "
                                    f"{'passed walk-forward' if proven else 'no out-of-sample edge'}"] * len(gg),
                              hovertemplate="%{text}<br>%{x|%H:%M}<extra></extra>")
    f.update_layout(template="plotly_dark", paper_bgcolor="#0b0f14", plot_bgcolor="#0b0f14", height=h,
                    margin=dict(l=6, r=6, t=30, b=6), hovermode="closest",
                    title=dict(text=f"SIGNALS · {pd.Timestamp(day):%a %d %b} · sensitivity {position} · filled = passed the walk-forward "
                                    f"test" + (f" · {n_hidden} unproven marks hidden" if n_hidden else ""),
                               font=dict(size=12, color="#c9d1d9"), x=0.01),
                    xaxis=dict(gridcolor="#1c2547", tickformat="%H:%M"), yaxis=dict(gridcolor="#1c2547", side="right", tickformat=",.0f"))
    return f


def wf_rows(wf: pd.DataFrame, position: str, ev: pd.DataFrame) -> pd.DataFrame:
    r = wf[wf["position"] == position].copy()
    r["signal"] = [f"{c} {SIG[c][0]}" for c in r["code"]]
    r["today"] = [int((ev["code"] == c).sum()) if len(ev) else 0 for c in r["code"]]
    r["verdict"] = np.where(r["PASS"], "✅ passed", "no edge")
    r["setting"] = [str(p) if p is not None else "—" for p in r["pick"]]
    return r[["signal", "verdict", "today", "per_day", "hit", "edge20", "t", "folds_pos", "n_oos", "setting"]].rename(columns={
        "per_day": "marks/day (test)", "hit": "hit % (test)", "edge20": "pts @20 vs random (test)", "t": "t (test)",
        "folds_pos": "test blocks +", "n_oos": "n (test)"})
