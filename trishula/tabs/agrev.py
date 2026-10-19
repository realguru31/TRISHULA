"""AG-REV — SPXFlow v2.10 on the tastytrade tape.

Signals Q1–Q5 + W (core/flowsig.py, rules line-for-line from SPXFlow.bas) and the
workbook's dashboard as panels:
  V1 LIVE flow — cumulative delta-notional ±$B bars + close + walls + signal markers
  V2 SPX BucketMin candles + walls + signal markers
  V3 Strike profile — today's flow (dealer γ $M/1%) vs naive OI GEX
  V4 Positioning heatmap — cumulative dealer γ from flow per strike × minute,
     decay projection right of now, white spot path
  V5 Call / put volume ridges by strike through time (ATM ± RidgeEachSide)
Plus the signals table, the stats line, and the tape diagnostics (gates G1–G3).
Everything recomputes from the tape (no state), so it replays with the universal player
and any config change re-scores the whole day (the workbook's REPLAY SIGNALS).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import flowsig as F
from core import interval as IV
from core import vs3d_data as D
from core.classify import NAMES
from core.signs import coverage_text
from core.timeutil import ET

BG = "#000000"
GRID = "#1c2128"
MARK = {("Q1", 1): ("triangle-up", "#00e676"), ("Q2", 1): ("triangle-up", "#69f0ae"),
        ("Q3", -1): ("triangle-down", "#ff5252"), ("Q4", -1): ("triangle-down", "#ff8a80"),
        ("Q5", 1): ("diamond", "#40c4ff"), ("Q5", -1): ("diamond", "#ffab40"),
        ("W", 1): ("star", "#b2ff59"), ("W", -1): ("star", "#ff6e40")}


def _style(f, title, h):
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h,
                    margin=dict(l=8, r=8, t=34, b=8), title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01),
                    legend=dict(orientation="h", y=1.08, x=1, xanchor="right", font=dict(size=10)))
    f.update_xaxes(gridcolor=GRID, zeroline=False)
    f.update_yaxes(gridcolor=GRID, zeroline=False)
    return f


def _empty(title, msg, h):
    f = go.Figure()
    f.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(color="#6e7681", size=12))
    f.update_xaxes(visible=False); f.update_yaxes(visible=False)
    return _style(f, title, h)


def _cfg_controls():
    ss = st.session_state
    with st.expander("⚙ SPXFlow config (BucketMin · ZThresh · MinPrem · WallTol · targets/stops) — the day re-scores live",
                     expanded=False):
        a, b, c, d = st.columns(4)
        a.slider("BucketMin", 1, 15, F.CFG_DEFAULT["BucketMin"], key="fs_BucketMin")
        a.slider("SkipOpenMin", 0, 30, F.CFG_DEFAULT["SkipOpenMin"], key="fs_SkipOpenMin")
        b.slider("ZThresh", 1.0, 5.0, F.CFG_DEFAULT["ZThresh"], 0.1, key="fs_ZThresh")
        b.number_input("MinPrem ($)", 0, 5_000_000, int(F.CFG_DEFAULT["MinPrem"]), 50_000, key="fs_MinPrem")
        c.slider("WallTol (pts)", 0.5, 10.0, F.CFG_DEFAULT["WallTol"], 0.5, key="fs_WallTol")
        c.slider("CooldownMin", 0, 30, F.CFG_DEFAULT["CooldownMin"], key="fs_CooldownMin")
        d.slider("StrikesEachSide (walls/grid)", 10, 60, F.CFG_DEFAULT["StrikesEachSide"], 5, key="fs_StrikesEachSide")
        d.slider("RidgeEachSide", 4, 30, 12, key="fs_Ridge")
        t = st.columns(6)
        for i, nm in enumerate(F.FAMILIES):
            dt_ = F.CFG_DEFAULT[f"{nm}Target"]
            t[i].number_input(f"{nm} target (0 = none)", 0.0, 200.0, float(dt_ or 0.0), 1.0, key=f"fs_{nm}Target")
            t[i].number_input(f"{nm} stop", 1.0, 200.0, float(F.CFG_DEFAULT[f"{nm}Stop"]), 1.0, key=f"fs_{nm}Stop")
    cfg = dict(F.CFG_DEFAULT)
    for k in list(cfg):
        if f"fs_{k}" in ss:
            cfg[k] = ss[f"fs_{k}"]
    for nm in F.FAMILIES:
        if not cfg.get(f"{nm}Target"):
            cfg[f"{nm}Target"] = None
    return cfg, int(ss.get("fs_Ridge", 12))


def render(rec):
    exps = rec.status()["expiries"]
    if not exps:
        st.info(f"Recorder: {rec.status()['state']} — waiting for the chain.")
        return
    c1, c2 = st.columns([1, 1])
    exp = c1.selectbox("Expiry", exps, key="agrev_exp")
    legs = c2.radio("Legs", ["All", "Single", "Multi"], horizontal=True, key="agrev_legs",
                    help="SPXFlow used all traded volume; Single = single-leg tape only (spread legs out).")
    cfg, ridge = _cfg_controls()
    _dash(rec, exp, legs, cfg, ridge)


def _dash(rec, exp, legs, cfg, ridge):
    spot, _ = rec.spot_now()
    raw = rec.prints_df(exp)
    day = D.session_date(rec)
    asof = getattr(rec, "ts_ms", None)
    now = (dt.datetime.fromtimestamp(asof / 1000, ET) if asof else dt.datetime.now(ET)).replace(tzinfo=None)
    p = IV.prep_prints(raw, rec.greeks, spot)
    if len(p):
        if legs == "Single":
            p = p[~p["spread_leg"].astype(bool)]
        elif legs == "Multi":
            p = p[p["spread_leg"].astype(bool)]
        p = p[p["ts"].dt.date == day]
    d = F.flow_rows(p, spot)
    ch = rec.live_chain(exp)
    cw, pw = F.walls(ch, spot, int(cfg["StrikesEachSide"]))
    candles = rec.candles_df()
    bk = F.buckets(d, candles, day, int(cfg["BucketMin"]), cw, pw)
    bk, fires = F.evaluate(bk, cfg)
    c1m = candles.copy()
    if len(c1m):
        c1m["t"] = pd.to_datetime(c1m["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
        c1m = c1m[c1m["t"].dt.date == day]
    session_over = now.date() > day or now.time() >= dt.time(16, 0)
    sig = F.score(fires, c1m, cfg, session_over) if len(c1m) else F.score([], c1m, cfg, False)
    st.markdown(f"**{F.stats_line(sig, cfg)}**")
    st.caption(f"{exp} · {legs} legs · walls CW {cw or '—'} / PW {pw or '—'} (max OI ±{cfg['StrikesEachSide']} strikes) · "
               f"{len(bk)} × {cfg['BucketMin']}-min buckets · {coverage_text(rec.dsign_table(exp))} · "
               "aggr from bid/ask at print + aggressorSide (MID by aggressor)")
    if day != (rec.exps[0] if rec.exps else day):
        st.caption(f"showing the last recorded session ({day:%a %d %b}); the next session fills from 09:30")

    left, right = st.columns([2.6, 1])
    with left:
        st.plotly_chart(_v1(bk, sig), width="stretch", key="ag_v1")
        st.plotly_chart(_v2(bk, sig, cfg), width="stretch", key="ag_v2")
    with right:
        st.plotly_chart(_v3(d, ch, spot, now, exp, int(cfg["StrikesEachSide"])), width="stretch", key="ag_v3")
    st.plotly_chart(_v4(d, ch, spot, now, exp, day, bk, int(cfg["StrikesEachSide"])), width="stretch", key="ag_v4")
    r1, r2 = st.columns(2)
    with r1:
        st.plotly_chart(_v5(p, spot, ridge, 1), width="stretch", key="ag_v5c")
    with r2:
        st.plotly_chart(_v5(p, spot, ridge, -1), width="stretch", key="ag_v5p")
    st.markdown("**Signals**")
    if sig.empty:
        st.caption("no signals yet — rules arm after 10 buckets and skip the first SkipOpenMin minutes")
    else:
        show = sig.copy()
        show["time"] = show["ts"].dt.strftime("%H:%M")
        show["exit"] = show["exit_ts"].apply(lambda t: t.strftime("%H:%M") if pd.notna(t) and t is not None else "")
        show["dir"] = show["dir"].map({1: "LONG", -1: "SHORT"})
        st.dataframe(show[["time", "name", "dir", "entry", "target", "stop", "status", "exit", "pnl", "why"]],
                     hide_index=True, width="stretch")
    with st.expander("Rule book (SPXFlow v2.10)", expanded=False):
        st.markdown("\n".join(f"- **{k}** — {v}" for k, v in F.DESCR.items()) +
                    "\n- Rolling window 30 buckets (arms at 10); z = (last positive/negative part − mean)/σ of that part;"
                    " MA = window mean close · cooldown per family (W exempt) · entry = bucket close · target/stop in SPX points.")
    with st.expander("Tape diagnostics (gates G1–G3) · bullish premium · CVD · last 200 prints", expanded=False):
        _diag(rec, exp, raw)


def _markers(f, bk, sig, row=None, col=None, secondary=None):
    if sig is None or sig.empty or bk.empty:
        return
    for (nm, dirn), (sym, color) in MARK.items():
        s = sig[(sig["name"] == nm) & (sig["dir"] == dirn)]
        if s.empty:
            continue
        y = np.where(dirn > 0, s["lo"] - 1.0, s["hi"] + 1.0)
        kw = dict(row=row, col=col) if row else {}
        if secondary is not None:
            kw["secondary_y"] = secondary
        f.add_scatter(x=s["ts"], y=y, mode="markers+text", text=s["name"], textposition="bottom center" if dirn > 0 else "top center",
                      textfont=dict(size=9, color=color), marker=dict(symbol=sym, size=11, color=color),
                      name=f"{nm}{'L' if dirn > 0 else 'S'}", **kw)


def _v1(bk, sig):
    title = "V1 · LIVE — cumulative delta-notional ($B) · close · walls · signals"
    if bk.empty:
        return _empty(title, "waiting for RTH candles / prints", 300)
    f = make_subplots(specs=[[{"secondary_y": True}]])
    cum = bk["cumdn"] / 1e9
    f.add_bar(x=bk["ts"], y=cum.where(cum > 0), marker_color="#2e7d32", name="cum Δ-notional +$B")
    f.add_bar(x=bk["ts"], y=cum.where(cum <= 0), marker_color="#c62828", name="cum Δ-notional −$B")
    f.add_scatter(x=bk["ts"], y=bk["close"], mode="lines", line=dict(color="white", width=1.3), name="close", secondary_y=True)
    for k, c in (("cw", "#ff5a3c"), ("pw", "#3ca0ff")):
        if bk[k].notna().any() and bk[k].iloc[-1]:
            f.add_scatter(x=bk["ts"], y=bk[k], mode="lines", line=dict(color=c, width=1, dash="dot"),
                          name=k.upper(), secondary_y=True)
    _markers(f, bk, sig, secondary=True)
    f.update_layout(barmode="overlay", bargap=0)
    f.update_yaxes(title_text="$B", secondary_y=False)
    return _style(f, title, 320)


def _v2(bk, sig, cfg):
    title = f"V2 · SPX {cfg['BucketMin']}-minute candles + signals"
    if bk.empty:
        return _empty(title, "waiting for RTH candles", 340)
    f = go.Figure()
    f.add_candlestick(x=bk["ts"], open=bk["open"], high=bk["high"], low=bk["low"], close=bk["close"],
                      increasing_line_color="#26a69a", decreasing_line_color="#ef5350", name="SPX", showlegend=False)
    if bk["ma"].notna().any():
        f.add_scatter(x=bk["ts"], y=bk["ma"], mode="lines", line=dict(color="#f0c040", width=1), name="MA(30)")
    for k, c in (("cw", "#ff5a3c"), ("pw", "#3ca0ff")):
        if bk[k].notna().any() and bk[k].iloc[-1]:
            f.add_scatter(x=bk["ts"], y=bk[k], mode="lines", line=dict(color=c, width=1, dash="dot"), name=k.upper())
    _markers(f, bk, sig)
    f.update_layout(xaxis_rangeslider_visible=False)
    return _style(f, title, 340)


def _v3(d, ch, spot, now, exp, n_each):
    title = "V3 · Strike profile — today's flow (dealer γ $M/1%) vs OI GEX naive"
    if ch is None or ch.empty or not spot == spot:
        return _empty(title, "waiting for chain", 680)
    c = ch[(ch["strike"] - spot).abs() <= n_each * 5.0]
    gex = (np.where(c["cp"] == 1, 1.0, -1.0) * c["oi"].fillna(0) * c["gamma"].fillna(0) * 100 * spot * spot * 0.01)
    og = pd.Series(gex.values, index=c["strike"].values).groupby(level=0).sum() / 1e6
    fl = (d.groupby("strike")["dgam"].sum() / 1e6).reindex(og.index, fill_value=0.0) if len(d) else og * 0
    f = go.Figure()
    f.add_bar(y=og.index, x=og.values, orientation="h", marker_color="#78829a", name="OI GEX naive ($M/1%)", opacity=0.75)
    f.add_bar(y=fl.index, x=fl.values, orientation="h", marker_color="#00e5ff", name="today's flow ($M)")
    f.add_hline(y=spot, line_dash="dash", line_color="white", line_width=1)
    f.update_layout(barmode="overlay")
    return _style(f, title, 680)


def _v4(d, ch, spot, now, exp, day, bk, n_each):
    title = "V4 · Positioning heatmap — cumulative dealer γ from flow · right of 'now' = decay projection · white = spot"
    if ch is None or ch.empty or not spot == spot:
        return _empty(title, "waiting for chain", 420)
    strikes = np.array(sorted(set(ch.loc[(ch["strike"] - spot).abs() <= n_each * 5.0, "strike"])))
    g = F.heat_grid(d, day, strikes)
    if g is None:
        return _empty(title, "no prints for this session yet", 420)
    expiry = dt.datetime.combine(dt.date.fromisoformat(exp), dt.time(16, 0))
    proj = None
    if now.date() == day and len(d):
        pos = d.groupby("sym").agg(pos=("aggr", lambda a: 0.0), strike=("strike", "first")).reset_index()
        pz = d.assign(pz=-d["aggr"] * d["size"]).groupby("sym")["pz"].sum()
        pos["pos"] = pos["sym"].map(pz).fillna(0.0)
        ivm = dict(zip(ch["sym"], ch["iv"].fillna(0)))
        pos["iv"] = pos["sym"].map(ivm).fillna(0.15)
        proj = F.projection(pos, spot, now, expiry, strikes)
    z = g.values.T
    x = list(g.index)
    if proj:
        x += [t for t, _ in proj]
        z = np.hstack([z, np.column_stack([v for _, v in proj])])
    f = go.Figure(go.Heatmap(z=z, x=x, y=strikes, zmin=-2, zmax=2, showscale=False,
                             colorscale=[[0, "#c62828"], [0.5, "#0b0f14"], [1, "#2e7d32"]]))
    if not bk.empty:
        f.add_scatter(x=bk["ts"], y=bk["close"], mode="lines", line=dict(color="white", width=1.6), name="spot")
    if proj:
        f.add_vline(x=now, line_color="#3399dd", line_dash="dot")
    f.update_yaxes(range=[strikes.min(), strikes.max()])
    return _style(f, title, 420)


def _v5(p, spot, ridge, cp):
    nm = "Call" if cp == 1 else "Put"
    title = f"V5 · {nm} volume by strike through time (ATM ±{ridge} strikes, 1-min)"
    if p is None or p.empty or not spot == spot:
        return _empty(title, "no prints yet", 380)
    x = p[(p["cp"] == cp) & ((p["strike"] - spot).abs() <= ridge * 5.0)].copy()
    if x.empty:
        return _empty(title, "no prints near ATM", 380)
    x["m"] = x["ts"].dt.floor("1min")
    g = x.groupby(["strike", "m"])["size"].sum().reset_index()
    f = go.Figure()
    color = "#26a69a" if cp == 1 else "#ef5350"
    for k, s in g.groupby("strike"):
        f.add_scatter3d(x=s["m"], y=[k] * len(s), z=s["size"], mode="lines", line=dict(color=color, width=3), showlegend=False)
    f.update_layout(scene=dict(xaxis_title="time", yaxis_title="strike", zaxis_title="contracts",
                               bgcolor=BG, xaxis=dict(gridcolor=GRID), yaxis=dict(gridcolor=GRID), zaxis=dict(gridcolor=GRID),
                               camera=dict(eye=dict(x=1.6, y=-1.6, z=0.8))))
    return _style(f, title, 380)


def _diag(rec, exp, all_df):
    if all_df is None or all_df.empty:
        st.info("No prints recorded yet for this expiry.")
        return
    m = st.columns(5)
    m[0].metric("Prints", f"{len(all_df):,}")
    m[1].metric("Quote on print", f"{(all_df['quote_src'] == 0).mean():.0%}")
    m[2].metric("aggressorSide set", f"{all_df['aggr_side'].isin(['BUY', 'SELL']).mean():.0%}")
    m[3].metric("Spread-leg share", f"{all_df['spread_leg'].mean():.0%}")
    m[4].metric("Unclassified", f"{(all_df['bucket'] == 9).mean():.0%}")
    d = all_df.sort_values("ts_ms").copy()
    d["t"] = pd.to_datetime(d["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET)
    d["bullp"] = d["aggr"] * d["size"] * d["px"] * 100 * d["cp"]
    d["cvd"] = (np.sign(d["aggr"]) * d["size"]).cumsum()
    g = make_subplots(specs=[[{"secondary_y": True}]])
    g.add_scatter(x=d["t"], y=d["bullp"].cumsum() / 1e6, mode="lines", line=dict(color="#2ecc71", width=1.4), name="cum bullish premium $M")
    for src, col in (("replay", "#8b949e"), ("live", "#58a6ff")):
        mm = d["src"] == src if "src" in d else (d.index == d.index)
        if mm.any():
            g.add_scatter(x=d.loc[mm, "t"], y=d.loc[mm, "cvd"], mode="lines", name=f"CVD {src}", line=dict(color=col, width=1.2),
                          secondary_y=True)
    st.plotly_chart(_style(g, "Bullish premium ($M) · CVD contracts (seed grey / live blue)", 280), width="stretch", key="ag_diag")
    a, b = st.columns([1, 2])
    bc = all_df["bucket"].map(NAMES).value_counts().rename_axis("bucket").reset_index(name="prints")
    a.dataframe(bc, hide_index=True, width="stretch")
    show = d.tail(200).iloc[::-1][["t", "strike", "cp", "px", "size", "bid", "ask", "bucket", "aggr_side", "spread_leg", "src"]].copy()
    show["t"] = show["t"].dt.strftime("%H:%M:%S")
    show["cp"] = show["cp"].map({1: "C", -1: "P"})
    show["bucket"] = show["bucket"].map(NAMES)
    b.dataframe(show, hide_index=True, width="stretch", height=360)
