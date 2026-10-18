"""VS3D: vs3dgbt 0.9.79 port on tastytrade data.

Book (matplotlib, vs3dgbt book_figure as-is) has three lenses (flow-signed,
clean-B, net flow) plus a Naive bars mode, seed dots, exhausted-extent sticks,
1× straddle, the 09:35 locked card ladder / PREVIEW, the Δ ladder with ⚡
divergence, a spot-path overlay, the KEY LEVELS card JPG and THE STRIP.
VS3D (combined) shows Book×spot | terrain. Global controls cover expiries to
aggregate, live price layer, snapshot scrubber and playback.
Terrain is still the interim heatmap (matplotlib port is v0.5.0); GEX³ is
panel 1 only (port is v0.6.0).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import book as B
from core import vs3d_data as D
from core.gex import add_exposures, window
from core.signs import coverage_text
from core.timeutil import ET

BG = "#0e1117"
TEAL, RED = "#26a69a", "#ef5350"
SUBTABS = ["VS3D (combined)", "Book (by strike)", "Terrain (gradient)", "Interval (bubbles)",
           "Market Read", "GEX³ (3-lens)", "DT"]
LENSES = ["flow-signed (current)", "clean-B (single-leg tape)", "net flow (PARTICIPANT VIEW)"]


# ── interim plotly panels (terrain until v0.5.0, GEX³ panel 1 until v0.6.0) ──
def _style(f, title, h):
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h,
                    margin=dict(l=8, r=8, t=34, b=30), showlegend=False,
                    title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01))
    f.update_xaxes(gridcolor="#1c2128", zeroline=False)
    f.update_yaxes(gridcolor="#1c2128", zeroline=False, dtick=10)
    return f


def _empty(title, msg, h):
    f = go.Figure()
    f.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                     font=dict(color="#6e7681", size=12))
    f.update_xaxes(visible=False)
    f.update_yaxes(visible=False)
    return _style(f, title, h)


def terrain_fig(hist, spot, lo, hi, h=820):
    title = "Terrain · naive e-minis per $1 by strike × time (interim — full port v0.5.0)"
    if hist.empty or hist["gamma"].isna().all():
        return _empty(title, "waiting for snapshots", h)
    e = hist.dropna(subset=["gamma"]).copy()
    e = e[(e["strike"] >= lo) & (e["strike"] <= hi)]
    if e.empty:
        return _empty(title, "no strikes in window", h)
    e["v"] = e["cp"] * e["gamma"] * e["oi"].fillna(0) * 100 / 50.0
    z = e.pivot_table(index="strike", columns="ts_ms", values="v", aggfunc="sum").sort_index()
    cap = float(np.nanpercentile(np.abs(z.values), 98)) or 1.0
    t = pd.to_datetime(z.columns, unit="ms", utc=True).tz_convert(ET)
    f = go.Figure(go.Heatmap(z=z.values, x=t, y=z.index, zmin=-cap, zmax=cap, showscale=False,
                             colorscale=[[0, RED], [0.5, BG], [1, TEAL]]))
    sp = e.groupby("ts_ms")["spot"].last()
    f.add_scatter(x=pd.to_datetime(sp.index, unit="ms", utc=True).tz_convert(ET), y=sp.values,
                  mode="lines", line=dict(color="white", width=1.5))
    f.update_yaxes(range=[lo, hi])
    return _style(f, title, h)


# ── controls ─────────────────────────────────────────────────────────────
def _global_controls(rec, ctl):
    exps_all = rec.all_exps or [str(e) for e in rec.exps]
    with st.expander("🌐 VS3D controls — expiries · live price layer · snapshot scrubber · playback", expanded=False):
        c1, c2, c3 = st.columns([1.2, 1.0, 2.2])
        n = c1.slider("Expiries to aggregate", 1, 5, 1, key="vs_nexp",
                      help="Book and card sum the first N listed expiries, starting from the expiry "
                           "picked in the bar above.")
        c2.selectbox("📡 Live price layer", ["15s", "30s", "60s", "off"], index=1, key="vs_live",
                     help="Refresh timer for the spot path and live book. Positioning itself moves "
                          "with the tape (seed + live) and the 60 s chain snapshots.")
        c3.segmented_control("Frame", ["LIVE", "Snapshot"], default="LIVE", key="vs_frame_mode")
        p1, p2, p3, p4, p5 = st.columns([0.5, 0.5, 0.5, 0.5, 1.4])
        if p1.button("⏮", key="vs_p_first", help="first snapshot"):
            st.session_state.update(vs_pidx=0, vs_play=False)
        if p2.button("▶", key="vs_p_play", help="play"):
            st.session_state["vs_play"] = True
            if st.session_state.get("vs_pidx") is None:
                st.session_state["vs_pidx"] = 0
        if p3.button("⏸", key="vs_p_pause", help="pause"):
            st.session_state["vs_play"] = False
        if p4.button("⏹", key="vs_p_stop", help="stop — back to LIVE / scrubber"):
            st.session_state.update(vs_pidx=None, vs_play=False)
        p5.segmented_control("Speed", ["1 s", "2 s", "4 s"], default="2 s", key="vs_speed")
    mode = st.session_state.get("vs_frame_mode") or "LIVE"
    exp0 = ctl["exp"]
    i0 = exps_all.index(exp0) if exp0 in exps_all else 0
    exps = exps_all[i0:i0 + n] if exps_all else []
    for e in exps:
        rec.request_expiry(e)
    snaps = D.snapshot_times(rec, exp0) if exp0 else []
    scrub = None
    if mode == "Snapshot" and snaps:
        scrub = st.select_slider("Snapshot", options=snaps, value=snaps[-1], key="vs_scrub",
                                 format_func=lambda t: D.naive_et(t).strftime("%a %H:%M"))
    elif mode == "Snapshot":
        st.caption("no stored snapshots for this expiry yet (one every 60 s while the market is open, 5 min outside)")
    return exps, snaps, scrub


def _book_controls():
    with st.expander("📊 Book controls", expanded=False):
        a, b, c = st.columns(3)
        a.radio("Bars", ["MM-inferred (signed)", "Naive calls+/puts−"], key="vs_bars")
        a.radio("Book signing", LENSES, key="vs_lens",
                help="flow-signed: dealer sign × OI contracts (seed + live tape, opacity = confidence). "
                     "clean-B: net single-leg paper per strike, dealer view. net flow: customer net "
                     "bought/sold paper (participant view). MID prints are signed by aggressorSide.")
        b.radio("Show (naive mode)", ["Total", "Calls", "Puts"], horizontal=True, key="vs_side")
        z1, z2, z3 = b.columns(3)
        if z1.button("➕", key="vs_zin", help="zoom in (strikes)"):
            st.session_state["vs_zoom"] = max(0.25, st.session_state.get("vs_zoom", 1.0) * 0.7)
        if z2.button("➖", key="vs_zout", help="zoom out"):
            st.session_state["vs_zoom"] = min(1.0, st.session_state.get("vs_zoom", 1.0) / 0.7)
        if z3.button("↔", key="vs_zfull", help="full range"):
            st.session_state["vs_zoom"] = 1.0
        c.checkbox("Comparison dots (open / seed)", True, key="vs_dots")
        c.checkbox("1× straddle lines", True, key="vs_strad")
        c.checkbox("Δ ladder — intraday-change METHOD (orange)", False, key="vs_delta")
        c.checkbox("Spot-path overlay (VS3D view)", True, key="vs_spot")
        c.checkbox("🗂 KEY LEVELS card", True, key="vs_card")
        c.checkbox("🎛 THE STRIP [EXPERIMENTAL]", True, key="vs_strip")


def _render_strip(strip):
    if not strip:
        st.caption("STRIP: no chain yet")
        return
    l1 = "&nbsp;·&nbsp;".join(f"<span style='color:{c}'>{t}</span>" for t, c in strip["chips"])
    p, pc = strip["play"]
    st.markdown("<div style='font-family:monospace;font-weight:bold;font-size:0.86rem;line-height:1.9'>"
                + l1 + f"<br><span style='color:{pc}'>▶ {p}</span></div>", unsafe_allow_html=True)


# ── the Book ─────────────────────────────────────────────────────────────
def build_book(rec, exps, ts_ms, ctl, notes):
    """Returns dict(png, card, strip, caption...) or None."""
    ss = st.session_state
    ch, spot, now = D.frame(rec, exps, ts_ms)
    if ch.empty or not spot == spot or not ch["gamma"].notna().any():
        return None
    day = D.session_date(rec)
    lens = ss.get("vs_lens") or LENSES[0]
    signed_mode = (ss.get("vs_bars") or "MM").startswith("MM")
    e0 = exps[0]
    ch0 = ch[ch["exp"] == e0]
    strad_now = B.mid_straddle(ch0, spot)
    strad = strad_now if ss.get("vs_strad", True) else None

    # dsign tables (seed / live split) for dots and paper lenses
    ds = pd.concat([rec.dsign_table(e) for e in exps], ignore_index=True)
    ds1 = pd.concat([rec.dsign_table(e, single_leg=True) for e in exps], ignore_index=True)
    seed_rows = B.seed_dot_rows(ch, ds)

    sg = sgo = None
    if signed_mode:
        if lens.startswith("clean"):
            sg, sgo = B.cleanB_rows(ds1, "all"), B.cleanB_rows(ds1, "seed")
            notes.append("CLEAN-B — net SINGLE-LEG paper, DEALER view: blue = dealer bought (participants sold) / "
                         "magenta = dealer sold · bar = seed + live, dot = yesterday-final")
        elif lens.startswith("net"):
            sg, sgo = B.netflow_rows(ds, True), B.netflow_rows(ds, False)
            notes.append("NET FLOW — ⚠ PARTICIPANT VIEW (sign = opposite actor vs the position lenses): "
                         "+ net bought / − net sold · no OI, no γ")
        else:
            sg, sgo = B.signed_book_rows(ch, spot, units="contracts"), seed_rows
        if sg is None:
            notes.append("no signed data in this frame — naive bars shown")
    if not ss.get("vs_dots", True):
        sgo = None

    # price window: control bar range × zoom
    half = (ctl["pct"] / 100 * spot) if ctl["mode"] == "% move" else ctl["n"] * 5.0
    z = float(ss.get("vs_zoom", 1.0))
    lo, hi = spot - half * z, spot + half * z

    # METHOD: reference, opening straddle, 09:35 lock, preview, Δ ladder
    target = rec.exps[0] if rec.exps else day          # the session the levels are for
    is_today = day == target                             # False = weekend / pre-open: preview of target
    ref, ref_src = D.method_ref(rec, spot, target, now)
    o_str = D.open_straddle(rec, exps, day) if is_today else None
    lock = D.card_lock(rec, exps, day, strad_now) if is_today else None
    flow_rows = B.signed_book_rows(ch, spot, units="contracts")
    prev_lv = None
    if not isinstance(lock, dict) and flow_rows is not None:
        out = {}
        B.key_levels_lines(flow_rows, spot, strad_now, "w", "g", "r", "c", "d", "y", ref_spot=ref,
                           open_strad=o_str, levels_out=out, seed_rows=seed_rows)
        prev_lv = out.get("levels") if out.get("ok") else None
    ilv, div = None, None
    ts_open = D.first_snap(rec, exps, day, dt.time(9, 30))
    if is_today and ts_open and now.time() >= dt.time(9, 35) and flow_rows is not None:
        och, osp, _ = D.frame(rec, exps, ts_open)
        r0 = B.signed_book_rows(och, osp, units="contracts")
        if r0 is not None:
            mg = flow_rows.merge(r0, on="strike", how="outer", suffixes=("", "_o")).fillna(0.0)
            mg["signed_pct"] = mg["signed_pct"] - mg["signed_pct_o"]
            ilv = B.dan_levels_from_rows(mg[["strike", "signed_pct", "conf"]], float(ref),
                                         float(o_str or strad_now or spot * 0.009))
            a_c = float(flow_rows.loc[flow_rows["strike"] > ref, "signed_pct"].sum())
            a_o = float(r0.loc[r0["strike"] > ref, "signed_pct"].sum())
            b_c = float(flow_rows.loc[flow_rows["strike"] < ref, "signed_pct"].sum())
            b_o = float(r0.loc[r0["strike"] < ref, "signed_pct"].sum())
            div = ("upside net sign flipped vs open book" if a_c * a_o < 0 else
                   "downside net sign flipped vs open book" if b_c * b_o < 0 else None)

    sfx = "" if lens.startswith("flow") else " ·flow-lock"
    fig = B.book_figure(B.naive_book(ch), spot, strad, lo, hi, side=ss.get("vs_side", "Total"),
                        signed=sg, signed_open=sgo, signmode=lens.split()[0],
                        lock_levels=(lock or {}).get("levels"), preview_levels=prev_lv,
                        intraday_levels=ilv, show_delta=ss.get("vs_delta", False), lock_suffix=sfx)
    if ss.get("vs_spot", True):
        bars = D.bars_for(rec, day, upto_ms=ts_ms)
        x0 = dt.datetime.combine(day, dt.time(9, 30))
        fig = B.book_spot_overlay(fig, bars, x0, x0 + dt.timedelta(hours=6, minutes=30))
    png = B.fig_png(fig)

    card = None
    if ss.get("vs_card", True):
        hdr = None
        status = None
        if isinstance(lock, dict):
            hdr = f"LOCKED {lock['locked_at']} ET — frozen for the session"
            b2 = D.bars_for(rec, day, upto_ms=ts_ms)
            b2 = b2[b2["ts_ms"] >= lock["ts_ms"]]
            status = b2["c"].dropna().tolist() or None
        elif not is_today or now.time() < dt.time(9, 35):
            hdr = "PREVIEW — pre-open book (yesterday's flow on today's OI) · locks at first ≥09:35 ET snapshot"
        lines = B.key_levels_lines(flow_rows, spot, strad_now, "k", "g", "r", "c", "d", "y", ref_spot=ref,
                                   open_strad=o_str, lock=(lock or {}).get("levels"), status_prices=status,
                                   header_note=hdr, seed_rows=seed_rows)
        card = (hdr, B.method_card_jpg(lines))

    strip = None
    if ss.get("vs_strip", True) and len(ch0):
        upto = ts_ms or int(dt.datetime.now(ET).timestamp() * 1000)
        hist, fuel0, tape = D.strip_inputs(rec, e0, day, upto)
        strip = B.compute_strip(ch0, spot, now, hist, fuel0, tape, D.vix_today(rec, day))

    s0 = f"${o_str:.2f} open" if o_str else (f"${strad_now:.2f} now" if strad_now else "n/a")
    frame_lbl = "snapshot " + D.naive_et(ts_ms).strftime("%a %H:%M") if ts_ms else "LIVE"
    cap = (f"{' + '.join(exps)} · {frame_lbl} · spot {spot:,.2f} · showing {int(lo)}–{int(hi)} · "
           f"zoom ×{z:.2f} · ref {ref:,.2f} ({ref_src}) · S0 {s0}")
    return dict(png=png, card=card, strip=strip, cap=cap, div=div,
                cov=coverage_text(ds), ch=ch, spot=spot, lo=lo, hi=hi)


def render(rec, ctl):
    exps, snaps, scrub = _global_controls(rec, ctl)
    tabs = st.tabs(SUBTABS)
    with tabs[1]:
        _book_controls()

    ss = st.session_state
    playing = bool(ss.get("vs_play")) and len(snaps) > 0
    speed = {"1 s": 1, "2 s": 2, "4 s": 4}.get(ss.get("vs_speed") or "2 s", 2)
    live_sec = {"15s": 15, "30s": 30, "60s": 60, "off": None}[ss.get("vs_live") or "30s"]
    run_every = speed if playing else (live_sec if scrub is None and ss.get("vs_pidx") is None else None)

    @st.fragment(run_every=run_every)
    def _live():
        if not ctl["exp"] or not exps:
            for t in (0, 1):
                with tabs[t]:
                    st.info("waiting for the chain")
            return
        pidx = ss.get("vs_pidx")
        ts_ms = scrub
        if pidx is not None and snaps:
            pidx = min(pidx, len(snaps) - 1)
            ts_ms = snaps[pidx]
            if ss.get("vs_play"):
                if pidx >= len(snaps) - 1:
                    ss["vs_play"] = False
                else:
                    ss["vs_pidx"] = pidx + 1
        notes: list[str] = []
        try:
            bk = build_book(rec, exps, ts_ms, ctl, notes)
        except Exception as e:                               # noqa: BLE001
            bk = None
            notes.append(f"⚠ book error: {type(e).__name__}: {e}")
        if pidx is not None and ts_ms:
            notes.insert(0, f"▶ playback {pidx + 1}/{len(snaps)} · {D.naive_et(ts_ms):%a %H:%M} ET"
                            + (" · playing" if ss.get("vs_play") else " · paused"))
        h = rec.chain_df()
        if len(h):
            h = h[h["exp"] == exps[0]]
            if ts_ms:
                h = h[h["ts_ms"] <= ts_ms]
        lo = bk["lo"] if bk else 0
        hi = bk["hi"] if bk else 1
        spot = bk["spot"] if bk else float("nan")

        with tabs[0]:
            if bk is None:
                st.info("waiting for greeks / OI / spot")
                for n in notes:
                    st.caption(n)
            else:
                if bk["strip"]:
                    _render_strip(bk["strip"])
                st.caption(bk["cap"] + " · " + bk["cov"])
                a, c = st.columns([1.0, 1.5], gap="small")
                with a:
                    st.caption("Positions — Book × spot path")
                    st.image(bk["png"], width="stretch")
                with c:
                    st.caption("Gamma terrain (interim)")
                    st.plotly_chart(terrain_fig(h, spot, lo, hi, 900), width="stretch", key="vs_c_terr")
        with tabs[1]:
            if bk is None:
                st.info("waiting for greeks / OI / spot")
                for n in notes:
                    st.caption(n)
            else:
                if bk["strip"]:
                    _render_strip(bk["strip"])
                if bk["card"]:
                    if bk["card"][0]:
                        st.caption(bk["card"][0])
                    st.image(bk["card"][1], caption="right-click → save image to copy the card")
                for n in notes:
                    st.caption(n)
                if bk["div"]:
                    st.caption(f"⚡ Δ-book structural divergence — {bk['div']} (Δ ladder toggle is in Book controls)")
                st.caption(bk["cap"] + " · " + bk["cov"])
                st.image(bk["png"], width="stretch")
        with tabs[2]:
            st.plotly_chart(terrain_fig(h, spot, lo, hi, 900), width="stretch", key="vs_terr")
        with tabs[5]:
            st.caption("GEX³ panel 1 · convention (naive) — full three-lens port is v0.6.0.")
            ch = bk["ch"] if bk else pd.DataFrame()
            if len(ch):
                e = add_exposures(ch[ch["exp"] == exps[0]].dropna(subset=["gamma"]), spot)
                g = e.groupby("strike")["gex"].sum().reset_index()
                g = window(g, spot, ctl["mode"], ctl["n"], ctl["pct"])
                f = go.Figure(go.Bar(y=g["strike"], x=g["gex"] / 1e9, orientation="h", width=3.6,
                                     marker_color=[TEAL if x >= 0 else RED for x in g["gex"]]))
                f.add_hline(y=spot, line_dash="dash", line_color="white", line_width=1)
                f.update_xaxes(title=dict(text="$B per 1% (convention)", font=dict(size=10, color="#aaa")))
                st.plotly_chart(_style(f, "GEX³ · panel 1 · convention", 820), width="stretch", key="vs_g3")
            else:
                st.plotly_chart(_empty("GEX³ · panel 1", "waiting for greeks / OI", 820), width="stretch", key="vs_g3")

    for i, msg in ((3, "Interval bubbles — queued (needs your definition before build)."),
                   (4, "Market Read — queued (needs your definition before build)."),
                   (6, "DT — queued (needs your definition before build).")):
        with tabs[i]:
            st.info(msg)
    _live()
