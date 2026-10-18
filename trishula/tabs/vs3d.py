"""VS3D: vs3dgbt 0.9.79 port on tastytrade data.

Book (matplotlib, vs3dgbt book_figure as-is) has three lenses (flow-signed,
clean-B, net flow) plus a Naive bars mode, seed dots, exhausted-extent sticks,
1× straddle, the 09:35 locked card ladder / PREVIEW, the Δ ladder with ⚡
divergence, a spot-path overlay, the KEY LEVELS card JPG and THE STRIP.
VS3D (combined) shows Book×spot | terrain. Global controls cover expiries to
aggregate, live price layer, snapshot scrubber and playback.
Terrain (gradient) is vs3dgbt's terrain (matplotlib): forward-projected field,
greeks, pockets, contours, peak-γ rail and stacked charm panel. GEX³ is vs3dgbt's
three-lens NIFTY model (convention · flow-signed · ΔOI/volume) with candles,
density profiles, levels, scorecards and readout.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st

from core import book as B
from core import gex3 as G
from core import terrain as T
from core import vs3d_data as D
from core.signs import coverage_text
from core.timeutil import ET

BG = "#0e1117"
TEAL, RED = "#26a69a", "#ef5350"
SUBTABS = ["VS3D (combined)", "Book (by strike)", "Terrain (gradient)", "Interval (bubbles)",
           "Market Read", "GEX³ (3-lens)", "DT"]
LENSES = ["flow-signed (current)", "clean-B (single-leg tape)", "net flow (PARTICIPANT VIEW)"]


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


def _terrain_controls():
    ss = st.session_state
    with st.expander("🗺 Terrain controls", expanded=False):
        a, b, c, d = st.columns(4)
        a.selectbox("Greek", T.GREEKS, index=1, key="tr_greek",
                    help="Delta Change (§7.7): futures dealers must trade to arrive hedged at each price/time — "
                         "combines gamma+charm; path of least resistance.")
        a.selectbox("Weighting", T.WEIGHTS, index=0, key="tr_wt",
                    help="OI = yesterday's settled book · Volume = today's cumulative flow · OI+Volume = both (default).")
        a.selectbox("Gamma field mode", T.FIELD_MODES, index=0, key="tr_fieldmode")
        a.checkbox("Signed field (dealer dsign)", True, key="tr_signed",
                   help="ON: per-leg dealer signs from the tape (seed + live; unseeded = naive × 0.2) drive the "
                        "field, like the Book. OFF: vs3dgbt's naive calls+/puts−.")
        b.selectbox("Range", ["Manual (fixed cap)", "Percentile", "Std Dev"], index=0, key="tr_norm",
                    help="Manual (guide §2.4): fixed symmetric cap so a loose day LOOKS loose.")
        if ss.get("tr_norm", "Manual (fixed cap)") == "Percentile":
            b.slider("Percentile hi", 80, 99, 95, key="tr_pct")
        b1, b2 = b.columns(2)
        if b1.button("Calibrate", key="tr_cal", help="cap = 1.3 × recent mean (after 2–3 snapshots)"):
            cs = ss.setdefault("tr_caps", {})
            for k in [k for k in list(cs) if k.startswith("terr_hist_")]:
                if cs[k]:
                    cs["terr_cap_" + k[len("terr_hist_"):]] = 1.3 * float(np.mean(cs[k][-24:]))
        if b2.button("Reset cap", key="tr_reset", help="reset at the open"):
            cs = ss.setdefault("tr_caps", {})
            for k in [k for k in list(cs) if k.startswith("terr_cap_")]:
                cs.pop(k, None)
        b.selectbox("Intensity", ["Power", "Sqrt", "Arcsinh"], index=0, key="tr_int")
        b.slider("Power exponent", 0.1, 1.5, 0.40, 0.05, key="tr_pow")
        c.slider("Field opacity", 0.15, 1.0, 0.38, 0.01, key="tr_alpha")
        c.slider("Saturation (cap ×)", 0.05, 1.0, 1.0, 0.05, key="tr_sat")
        c.checkbox("Contours (zero + ridges/troughs)", True, key="tr_cont")
        c.checkbox("Gamma pockets (cavity + red core)", True, key="tr_rings")
        c.slider("Pockets to show", 1, 6, 3, 1, key="tr_nblob")
        d.checkbox("Straddle bounds", False, key="tr_strad")
        d.checkbox("Dealer levels overlay (Pinak)", False, key="tr_lvls")
        d.radio("Vol adjust", ["0%", "+1%"], horizontal=True, key="tr_voladj")
        d.checkbox("Simulated gamma ($5 finite diff, §2.7)", False, key="tr_simg")
        d.checkbox("Simulated charm (5-min clock, §2.7)", False, key="tr_simc")
        d.checkbox("Charm panel below (stacked)", True, key="tr_charm2")
        z1, z2, z3 = d.columns(3)
        if z1.button("➕", key="tr_zin", help="zoom in (terrain)"):
            ss["tr_zoom"] = max(0.25, ss.get("tr_zoom", 1.0) * 0.7)
        if z2.button("➖", key="tr_zout", help="zoom out"):
            ss["tr_zoom"] = min(1.0, ss.get("tr_zoom", 1.0) / 0.7)
        if z3.button("↔", key="tr_zfull", help="full range"):
            ss["tr_zoom"] = 1.0


def _terrain_opts(spot, ctl, canonical=False):
    ss = st.session_state
    half = (ctl["pct"] / 100 * spot) if ctl["mode"] == "% move" else ctl["n"] * 5.0
    o = dict(greek=ss.get("tr_greek", "Gamma"), weighting=ss.get("tr_wt", T.WEIGHTS[0]),
             norm=ss.get("tr_norm", "Manual (fixed cap)"), pct=ss.get("tr_pct", 95),
             intensity=ss.get("tr_int", "Power"), power=float(ss.get("tr_pow", 0.40)),
             alpha=float(ss.get("tr_alpha", 0.38)), sat=float(ss.get("tr_sat", 1.0)),
             contours=ss.get("tr_cont", True), pockets=ss.get("tr_rings", True), nblob=ss.get("tr_nblob", 3),
             strad=ss.get("tr_strad", False), levels=ss.get("tr_lvls", False), voladj=ss.get("tr_voladj", "0%"),
             simg=ss.get("tr_simg", False), simc=ss.get("tr_simc", False), charm2=ss.get("tr_charm2", True),
             fieldmode=ss.get("tr_fieldmode", T.FIELD_MODES[0]), signed=ss.get("tr_signed", True),
             zoom=float(ss.get("tr_zoom", 1.0)), p_min=spot - half, p_max=spot + half)
    if canonical:                       # vs3dgbt canonical pair: Gamma + Charm, overlay-free
        o.update(greek="Gamma", strad=False, levels=False, charm2=True, zoom=1.0)
    return o


def build_terrain(rec, exps, ts_ms, ctl, canonical=False):
    ch, spot, now = D.frame(rec, exps, ts_ms)
    if ch.empty or not spot == spot or not ch["gamma"].notna().any():
        return None, ["waiting for greeks / OI / spot"]
    target = rec.exps[0] if rec.exps else D.session_date(rec)
    day = D.session_date(rec)
    axis_day = day if day == target else target          # weekend / pre-open: project the next session
    bars = D.bars_for(rec, axis_day, upto_ms=ts_ms)
    o = _terrain_opts(spot, ctl, canonical)
    caps = st.session_state.setdefault("tr_caps", {})
    peak = D.peak_track(rec, exps[0], axis_day) if o["greek"] == "Gamma" else []
    key = ("terr", tuple(exps), ts_ms or int(now.timestamp() // 30), round(spot, 1), repr(sorted(o.items())),
           round(float(ch["oi"].fillna(0).sum())), round(float(ch["dsign"].fillna(0).sum()), 2) if "dsign" in ch else 0,
           repr(sorted((k, round(v, 3)) for k, v in caps.items() if k.startswith("terr_cap_"))))
    cache = rec.ui_state.setdefault("_terr_png", {})
    if key in cache:
        return cache[key]
    figs, notes = T.terrain_figures(ch, spot, exps, now, axis_day, bars, o, caps, peak)
    res = ([B.fig_png(f) for f in figs], notes)
    while len(cache) >= 8:
        cache.pop(next(iter(cache)))
    cache[key] = res
    return res


def _img(png: bytes, caption: str | None = None, max_w: int | None = None):
    """Inline data-URI image: fragment reruns cannot orphan it (st.image media files 404'd
    when a fragment re-registered them)."""
    import base64
    b64 = base64.b64encode(png).decode()
    cap = f"<div style='color:#8b949e;font-size:0.8rem'>{caption}</div>" if caption else ""
    st.markdown(f"<img src='data:image/png;base64,{b64}' style='width:100%;height:auto;{f"max-width:{max_w}px" if max_w else ""}'/>{cap}",
                unsafe_allow_html=True)


def build_gex3(rec, exps, ts_ms):
    ss = st.session_state
    ch, spot, now = D.frame(rec, exps, ts_ms)
    if ch.empty or not spot == spot or not ch["gamma"].notna().any():
        return None
    target = rec.exps[0] if rec.exps else D.session_date(rec)
    day = D.session_date(rec)
    axis_day = day if day == target else target
    bars = D.bars_for(rec, axis_day, upto_ms=ts_ms)
    doi = None
    if (ss.get("g3w") or "Δ").startswith("Δ"):
        today = now.date()
        pk = G.prev_day_key(rec.oi_log, today)
        with rec.lock:
            legs = dict(rec.legs)
            cur = dict(rec.oi_log.get(str(today), {}))
            prev = dict(rec.oi_log.get(pk, {})) if pk else {}
        doi = G.doi_frame(cur, prev, legs)
    lock = D.card_lock(rec, exps, day, None) if day == target else None
    fig, rd, notes = G.gex3_figure(ch, spot, exps[0], axis_day, bars, doi, ss.get("g3w") or "Δ-OI overnight",
                                   ss.get("g3s") or "signed (dsign)", float(ss.get("g3room", 0.5)) / 100.0,
                                   float(ss.get("g3wd", 0.45)), float(ss.get("g3h", 5.5)),
                                   (lock or {}).get("levels"))
    html, det = G.readout_html(rd)
    return B.fig_png(fig), html, det, notes


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
    with tabs[2]:
        _terrain_controls()
    with tabs[5]:
        with st.expander("⚙ GEX³ controls", expanded=False):
            g1, g2, g3 = st.columns(3)
            g1.slider("panel height (inches)", 3.0, 8.0, 5.5, 0.5, key="g3h")
            g2.slider("± % price room (display)", 0.25, 3.0, 0.5, 0.25, key="g3room",
                      help="absolute view height around spot — 0.5% default; the model computes on the full chain.")
            g3.slider("density width (share of panel)", 0.25, 0.60, 0.45, 0.05, key="g3wd")
            g1.radio("Panel-3 weight", ["Δ-OI overnight", "live volume"], horizontal=True, key="g3w")
            g2.radio("Panel-3 sign", ["signed (dsign)", "naive"], horizontal=True, key="g3s")

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
                    _img(bk["png"])
                with c:
                    st.caption("Gamma + Charm terrain (canonical pair)")
                    try:
                        pngs, tn = build_terrain(rec, exps, ts_ms, ctl, canonical=True)
                    except Exception as e:                   # noqa: BLE001
                        pngs, tn = None, [f"⚠ terrain error: {type(e).__name__}: {e}"]
                    for n_ in tn:
                        st.caption(n_)
                    for p_ in (pngs or []):
                        _img(p_)
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
                    _img(bk["card"][1], "right-click → save image to copy the card", max_w=620)
                for n in notes:
                    st.caption(n)
                if bk["div"]:
                    st.caption(f"⚡ Δ-book structural divergence — {bk['div']} (Δ ladder toggle is in Book controls)")
                st.caption(bk["cap"] + " · " + bk["cov"])
                _img(bk["png"])
        with tabs[2]:
            if bk is not None and bk["strip"]:
                _render_strip(bk["strip"])
            try:
                pngs, tn = build_terrain(rec, exps, ts_ms, ctl)
            except Exception as e:                           # noqa: BLE001
                pngs, tn = None, [f"⚠ terrain error: {type(e).__name__}: {e}"]
            st.caption("VS3D Gradient Chart, guide-spec. Field = chosen greek across price×time for the WHOLE "
                       "aggregated book (each expiry decays on its own clock). Manual symmetric range · near-linear "
                       "intensity · field behind price. Contours: dotted = zero boundary · orange = ridge/trough.")
            for n_ in tn:
                st.caption(n_)
            for p_ in (pngs or []):
                _img(p_)
        with tabs[5]:
            st.caption("GEX³ [EXPERIMENTAL] — the NIFTY GEX model on three lenses, strikes on Y with live candles. "
                       "DISPLAY-ONLY: never feeds THE METHOD. Panel 1 CONVENTION assumes the US dealer-sign convention; "
                       "panel 2 FLOW-SIGNED is the tape inference; panel 3 is Δ-OI overnight (recorded settled OI, "
                       "today − prior session) or live volume.")
            try:
                g3 = build_gex3(rec, exps, ts_ms)
            except Exception as e:                           # noqa: BLE001
                g3 = None
                st.caption(f"⚠ GEX³ error: {type(e).__name__}: {e}")
            if g3 is None:
                st.info("waiting for greeks / OI / spot")
            else:
                png, html, det, gnotes = g3
                for n_ in gnotes:
                    st.caption(n_)
                _img(png)
                st.markdown(html, unsafe_allow_html=True)
                with st.expander("model detail (gravity trio · pin scoring · HHI top-5 · dials)"):
                    st.code(det, language=None)

    for i, msg in ((3, "Interval bubbles — queued (needs your definition before build)."),
                   (4, "Market Read — queued (needs your definition before build)."),
                   (6, "DT — queued (needs your definition before build).")):
        with tabs[i]:
            st.info(msg)
    _live()
