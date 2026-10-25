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

from core import loader as LD
from plotly.subplots import make_subplots

from core import flowsig as F
from tabs import agrev3d as R3
from core import session as S
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
        d.slider("RidgeEachSide", 4, 30, 9, key="fs_Ridge")
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


def render(rec, ctl=None):
    exps = rec.status()["expiries"]
    if not exps:
        st.info(f"Recorder: {rec.status()['state']} — waiting for the chain.")
        return
    c1, c2 = st.columns([1, 1])
    exp = c1.selectbox("Expiry", exps, key="agrev_exp")
    legs = c2.radio("Legs", ["All", "Single", "Multi"], horizontal=True, key="agrev_legs",
                    help="SPXFlow used all traded volume; Single = single-leg tape only (spread legs out).")
    cfg, ridge = _cfg_controls()
    st.session_state["_ag_ctl"] = ctl
    _dash(rec, exp, legs, cfg, ridge)


def _dash(rec, exp, legs, cfg, ridge):
    LD.stage("loading prints", 0.10)
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
        p = p[S.mask(p["ts"], day)]
    d = F.flow_rows(p, spot)
    ch = rec.live_chain(exp)
    cw, pw = F.walls(ch, spot, int(cfg["StrikesEachSide"]))
    bars = D.bars_for(rec, day, asof)
    LD.stage("SPXFlow buckets + signals", 0.35)
    bk = F.buckets(d, bars, day, int(cfg["BucketMin"]), cw, pw)
    bk, fires = F.evaluate(bk, cfg)
    c1m = bars.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
    session_over = now.date() > day or now.time() >= dt.time(16, 0)
    sig = F.score(fires, c1m, cfg, session_over) if len(c1m) else F.score([], c1m, cfg, False)
    st.markdown(f"**{F.stats_line(sig, cfg)}**")
    st.caption(f"{exp} · {legs} legs · walls CW {cw or '—'} / PW {pw or '—'} (max OI ±{cfg['StrikesEachSide']} strikes) · "
               f"{len(bk)} × {cfg['BucketMin']}-min buckets · {coverage_text(rec.dsign_table(exp))} · "
               "aggr from bid/ask at print + aggressorSide (MID by aggressor)")
    if day != (rec.exps[0] if rec.exps else day):
        st.caption(f"showing the {day:%a %d %b} session; the next one starts filling at 20:15 ET (GTH) "
                   "— turn 🌙 GTH off to see 09:30–16:00 only")

    left, right = st.columns([2.6, 1])
    with left:
        st.plotly_chart(_v1(bk, sig), width="stretch", key="ag_v1")
        st.plotly_chart(_v2(bk, sig, cfg), width="stretch", key="ag_v2")
    with right:
        st.plotly_chart(_v3(d, ch, spot, now, exp, int(cfg["StrikesEachSide"])), width="stretch", key="ag_v3")
    # ── V5 ridges (3-D / 2-D) with the spike filter · V4 positioning surface / heatmap ──
    st.markdown("**V5 · Ridges — volume per strike through time** · ⚡ spikes = unusual for that contract AND big for the chain")
    LD.stage("V5 ridges + spike filter", 0.60)
    tb = R3.toolbar()
    rexp = R3.ridge_exps(rec, exp, tb.get("exp", "0+1DTE"))          # v0.18: AG's ridges include 1DTE
    pr = p
    if len(rexp) > 1:
        extra = []
        for e_ in rexp[1:]:
            q_ = IV.prep_prints(rec.prints_df(e_), rec.greeks, spot)
            if len(q_):
                if legs == "Single":
                    q_ = q_[~q_["spread_leg"].astype(bool)]
                elif legs == "Multi":
                    q_ = q_[q_["spread_leg"].astype(bool)]
                extra.append(q_[S.mask(q_["ts"], day)])
        if extra:
            pr = pd.concat([p] + extra, ignore_index=True) if len(p) else pd.concat(extra, ignore_index=True)
    spk, _V, mt = R3.spikes_for(rec, pr, day, rexp, tb["spike"])
    labs = sorted({R3._label(k, cp) for k, cp in zip(mt["strike"], mt["cp"])}, key=lambda x: (float(x[:-1].replace(",", "")), x[-1])) if len(mt) else []
    hot = list(dict.fromkeys(R3._label(k, cp) for k, cp in zip(spk["strike"][::-1], spk["cp"][::-1]))) if len(spk) else []
    t0, t1 = R3.window_bounds(day, mt, asof, tb["win"])
    ks = (R3.ridgeline_strikes(mt, spot, bars, t0, t1) if tb["view"] == "ridgeline"
          else R3.ridge_strikes(mt, spot, st.session_state.get("_ag_ctl"), ridge, bars, t0, t1))
    auto = R3.auto_pin(spk, t0, t1, ks, tb["side"])
    ss = st.session_state
    # ── L7 click-to-pin: strike strip (2-D, clickable) and the ⚡ Spikes table feed ss["r3_pick"] ──
    def _ev_sig(v):
        return repr(v)
    def _dig(o, *ks_):
        for k_ in ks_:
            try:
                o = o[k_]
            except Exception:                                   # noqa: BLE001
                o = getattr(o, k_, None)
            if o is None:
                return []
        return list(o)
    strip_ev = _dig(ss.get("ag_strip"), "selection", "points")
    if strip_ev and _ev_sig(strip_ev) != ss.get("r3_last_strip"):
        ss["r3_last_strip"] = _ev_sig(strip_ev)
        pt = strip_ev[0]
        cd_ = pt.get("customdata")
        if cd_ and len(cd_) >= 2:
            k_, cp_ = float(cd_[0]), int(cd_[1])
        else:
            k_ = float(str(pt.get("y", "0")).replace(",", "")); cp_ = 1 if pt.get("curve_number", 0) == 0 else -1
        is_star = pt.get("curve_number", 0) == (2 if tb["side"] == "C+P" else 1)
        ss["r3_pick"] = (k_, cp_ if (is_star or tb["side"] != "C+P") else 0)
    rows = _dig(ss.get("ag_spk_tbl"), "selection", "rows")
    if rows and _ev_sig(rows) != ss.get("r3_last_tbl") and len(spk):
        ss["r3_last_tbl"] = _ev_sig(rows)
        r_ = spk.iloc[::-1].reset_index(drop=True).iloc[min(rows[0], len(spk) - 1)]
        ss["r3_pick"] = (float(r_["strike"]), int(r_["cp"]))
    def _sel():
        v = ss.get("r3_pin2") or ""
        ss["r3_pick"] = None if v.startswith("auto") else ("none" if v == "—" else
                                                           (float(v[:-1].replace(",", "")), 1 if v[-1] == "C" else -1))
    auto_lbl = f"auto · strongest spike ({R3._label(*auto)})" if auto else "auto · strongest spike (none yet)"
    c_pin, c_auto = st.columns([5, 1])
    c_pin.selectbox("pin a contract", [auto_lbl, "—"] + hot + [x for x in labs if x not in hot], key="r3_pin2",
                    on_change=_sel, help="auto = the strongest spike in the window (premium × z). Or click a strike in the "
                                         "strip beside the ridges, or a row in the ⚡ Spikes table.")
    if c_auto.button("↺ auto", key="r3_auto", help="back to the strongest spike"):
        ss["r3_pick"] = None
    pick = ss.get("r3_pick")
    pin = None if pick == "none" else (auto if pick is None else tuple(pick))
    def _pl(pn):
        return "—" if not pn else (f"{pn[0]:,.0f} (C+P)" if pn[1] == 0 else R3._label(*pn))
    st.caption(f"pinned: **{_pl(pin)}**" + (" · auto (strongest spike)" if pick is None else " · your pick"))
    a3, s3, b3 = st.columns([3, 0.55, 1])
    with a3:
        if tb["view"] in ("3D", "ridgeline") and len(ks):
            from core import ridges_ag as RA
            cd = R3.pane_for(pr, spk, pin, t0, t1, rexp, rec.greeks, tb["side"], R3.candles_for(rec, rexp, day),
                             legs=dict(rec.legs)) if pin else None
            nsp = int(((spk['m'] >= t0) & (spk['m'] <= t1)).sum()) if len(spk) else 0
            ttl = (f"RIDGES · {t0:%H:%M}–{t1:%H:%M} · "
                   + ("contracts / min (AG)" if tb.get("height", "AG") == "AG" else "unusual vs own last 30 min")
                   + " · spikes = ridge peaks "
                   f"(▲ green bullish · ▼ pink bearish) · ⚡ {nsp} (top {tb['top']} bold per session part) · pinned {_pl(pin)}")
            ttl = ttl.replace("RIDGES ·", f"RIDGES · {' + '.join(pd.Timestamp(e_).strftime('%d %b') for e_ in rexp)} ·")
            if tb["view"] == "ridgeline":
                fig = RA.ridgeline(mt, spk, bars, t0, t1, ks, pin=pin, side=tb["side"], top=tb["top"], contract=cd,
                                   h=900 if cd else 640, title=ttl.replace("spikes = ridge peaks ", "spikes = marks "),
                                   height=tb.get("height", "AG"))
            else:
                fig = RA.figure(mt, spk, bars, t0, t1, ks, pin=pin, side=tb["side"], top=tb["top"], contract=cd,
                                h=900 if cd else 620, title=ttl,
                                rth_open=pd.Timestamp(dt.datetime.combine(day, dt.time(9, 30))),
                                height=tb.get("height", "AG"))
            st.plotly_chart(fig, width="stretch", key="ag_ridges")
        else:
            pl = R3._label(*pin) if (pin and pin[1] in (1, -1)) else None
            st.plotly_chart(R3.ridges(mt, spk, bars, spot, ridge, tb, pl, day), width="stretch", key="ag_ridges")
        st.caption(_bf_note(rec))
    with s3:
        if len(ks):
            st.plotly_chart(R3.strike_strip(mt, spk, sorted(ks, reverse=True), t0, t1, tb["side"], pin,
                                            h=900 if (tb["view"] in ("3D", "ridgeline") and pin) else 620),
                            width="stretch", key="ag_strip", on_select="rerun", selection_mode="points",
                            config={"displayModeBar": False})
    with b3:
        st.markdown("**⚡ Spikes** · click a row to pin")
        R3.spikes_table(spk, key="ag_spk_tbl")
    st.markdown("**Tetris** — where each strike's options matter most through the session (AG-style blocks)")
    LD.stage("Tetris", 0.80)
    tt = st.columns([1.5, 1.1, 1.3, 0.9, 1.1])
    v4mode = tt[0].segmented_control("Tetris view", ["A · γ", "E · vega", "flow surface", "2-D"], default="A · γ",
                                     key="ag_tt_mode2", label_visibility="collapsed",
                                     help="A (default) = open interest × gamma, E = open interest × vega; each strike scaled to its "
                                          "own peak SO FAR (v0.19: a drawn column never changes colour). 'flow surface' / '2-D' "
                                          "= the earlier cumulative-flow views. (G · price grid removed 24 Oct: flat bands.)")
    pal = "AG"                                                    # v0.19: readable palette removed
    ov_opts = (["OI only (fixed at open)", "+ traded since 20:15 (overnight)", "+ traded since 09:30"] if S.gth()
               else ["OI only (fixed at open)", "+ traded since 09:30"])        # GTH off: the open IS 09:30
    if ss.get("ag_tt_ovl") not in ov_opts:
        ss.pop("ag_tt_ovl", None)
    ovl = tt[2].selectbox("overlay", ov_opts,
                          key="ag_tt_ovl", label_visibility="collapsed",
                          help="weight = prior-close open interest, optionally plus contracts traded since 20:15 ET the evening before "
                               "(overnight session, GTH on) or since the 09:30 regular open")
    scl = tt[1].segmented_control("scale", ["no repaint", "hindsight"], default="no repaint", key="ag_tt_scale",
                                  label_visibility="collapsed",
                                  help="no repaint (default) = each strike scaled to its peak SO FAR: a drawn column never changes. "
                                       "hindsight = scaled to the DAY's peak (the v0.18 look): uses the future, repaints — the warm "
                                       "blocks at highs/lows only appear after the fact (L34, 25 Oct).")
    tt_ex = tt[4].segmented_control("Tetris expiries", ["0DTE", "0+1DTE"], default="0DTE", key="ag_tt_exp",
                                    label_visibility="collapsed",
                                    help="0DTE = the selected expiry (how A/E were matched to AG's 16 Oct chart) · 0+1DTE = "
                                         "also the next expiry, summed per strike, each with its own time to expiry")
    smo = tt[3].select_slider("smooth", [0, 1, 2, 3], value=0, key="ag_tt_smooth", format_func=lambda v: f"smooth {v * 5}pt" if v else "no smooth",
                              label_visibility="collapsed")
    if v4mode in ("A · γ", "E · vega", None):
        try:
            res = R3.tetris_build(rec, exp, day, asof, ks, bars, mt,
                                  {"E · vega": "E"}.get(v4mode, "A"), pal or "AG", ovl, smo, causal=(scl != "hindsight"),
                                  exps=R3.ridge_exps(rec, exp, "0+1DTE") if tt_ex == "0+1DTE" else [exp])
        except Exception as e:                                     # noqa: BLE001
            res = None
            st.caption(f"⚠ tetris error: {type(e).__name__}: {e}")
        if res is not None:
            fig3, fig2, legend = res
            a4, b4 = st.columns([3, 1])
            a4.plotly_chart(fig3, width="stretch", key="ag_tt3")
            b4.plotly_chart(fig2, width="stretch", key="ag_tt2", config={"displayModeBar": False})
            b4.markdown(legend, unsafe_allow_html=True)
            b4.caption(f"OI coverage {exp}: {rec.status().get('oi_0dte_legs', '?')} contracts · "
                       + "Height and colour = this strike's weight × greek as a share of its own peak SO FAR (no repaint). "
                       + "Reverse-engineered from AG's screenshots — a visual match, not his confirmed formula.")
    elif v4mode == "flow surface":
        g, proj = _heat_data(d, ch, spot, now, exp, day, int(cfg["StrikesEachSide"]))
        st.plotly_chart(R3.surface(g, proj, bars, day), width="stretch", key="ag_v4s")
    else:
        st.plotly_chart(_v4(d, ch, spot, now, exp, day, bk, int(cfg["StrikesEachSide"])), width="stretch", key="ag_v4")
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


def _open_line(f, bk):
    if S.gth() and len(bk):
        d0 = bk["ts"].max().date()
        if bk["ts"].min() < S.rth_open_dt(d0) <= bk["ts"].max():
            f.add_vline(x=S.rth_open_dt(d0), line_dash="dash", line_color="#8a93a6", line_width=1)


def _v1(bk, sig):
    title = "V1 · LIVE — cumulative delta-notional ($B) · close · walls · signals"
    if bk.empty:
        return _empty(title, "waiting for session bars / prints", 300)
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
    _open_line(f, bk)
    return _style(f, title, 320)


def _v2(bk, sig, cfg):
    title = f"V2 · SPX {cfg['BucketMin']}-minute candles + signals"
    if bk.empty:
        return _empty(title, "waiting for session bars", 340)
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
    _open_line(f, bk)
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


def _heat_data(d, ch, spot, now, exp, day, n_each):
    if ch is None or ch.empty or not spot == spot:
        return None, None
    strikes = np.array(sorted(set(ch.loc[(ch["strike"] - spot).abs() <= n_each * 5.0, "strike"])))
    g = F.heat_grid(d, day, strikes)
    if g is None:
        return None, None
    expiry = dt.datetime.combine(dt.date.fromisoformat(exp), dt.time(16, 0))
    proj = None
    if S.open_dt(day) <= now <= S.close_dt(day) and len(d):
        pz = d.assign(pz=-d["aggr"] * d["size"]).groupby("sym").agg(pos=("pz", "sum"), strike=("strike", "first")).reset_index()
        ivm = dict(zip(ch["sym"], ch["iv"].fillna(0)))
        pz["iv"] = pz["sym"].map(ivm).fillna(0.15)
        proj = F.projection(pz, spot, now, expiry, strikes)
    return g, proj


def _v4(d, ch, spot, now, exp, day, bk, n_each):
    title = "TETRIS · 2-D heatmap — cumulative dealer γ from flow · right of 'now' = decay projection · white = spot"
    if ch is None or ch.empty or not spot == spot:
        return _empty(title, "waiting for chain", 420)
    strikes = np.array(sorted(set(ch.loc[(ch["strike"] - spot).abs() <= n_each * 5.0, "strike"])))
    g = F.heat_grid(d, day, strikes)
    if g is None:
        return _empty(title, "no prints for this session yet", 420)
    expiry = dt.datetime.combine(dt.date.fromisoformat(exp), dt.time(16, 0))
    proj = None
    if S.open_dt(day) <= now <= S.close_dt(day) and len(d):
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
    # M1: one point per minute (was one per print → ~1M points per trace late in the day)
    d["mt"] = d["t"].dt.tz_localize(None).dt.floor("1min")
    d["cum_bull"] = d["bullp"].cumsum() / 1e6
    g = make_subplots(specs=[[{"secondary_y": True}]])
    bm = d.groupby("mt")["cum_bull"].last()
    g.add_scatter(x=bm.index, y=bm.values, mode="lines", line=dict(color="#2ecc71", width=1.4), name="cum bullish premium $M")
    for src, col in (("replay", "#8b949e"), ("live", "#58a6ff")):
        mm = d["src"] == src if "src" in d else (d.index == d.index)
        if mm.any():
            cm = d.loc[mm].groupby("mt")["cvd"].last()
            g.add_scatter(x=cm.index, y=cm.values, mode="lines", name=f"CVD {src}", line=dict(color=col, width=1.2),
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


def _bf_note(rec):
    """L20: show whether the 1-minute backfill landed (without it, the morning is the capped replay)."""
    try:
        sd = (getattr(rec, "seed", None) or getattr(getattr(rec, "rec", None), "seed", None) or {})
        b = sd.get("backfill_1m")
    except Exception:                                              # noqa: BLE001
        b = None
    if not b:
        return "1-min backfill: pending (ridges before the restart come from the capped replay until it lands)"
    if b.get("note"):
        return f"⚠ 1-min backfill: {b['note']} — ridges before the restart are thin, newer minutes will look louder"
    n, f = b.get("contracts", 0), b.get("filled", b.get("contracts", 0))
    warn = "⚠ " if n and f < 0.8 * n else ""
    sw = sd.get("sweep_1m") or {}
    swt = (f" · candle sweep (0DTE+1DTE, every 5 min): {sw.get('filled', 0)}/{sw.get('contracts', 0)} contracts at "
           f"{str(sw.get('at', ''))[11:16]} ET") if sw else " · candle sweep: first run ~1 min after start"
    return (f"{warn}1-min backfill: {f}/{n} contracts · {b.get('rows', 0):,} candle-minutes · {str(b.get('at', ''))[11:16]} ET"
            + (" — partly thin, newer minutes may look louder" if warn else "") + swt)

