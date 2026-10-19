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
from core import interval as IV
from core import read as RD
from core import terrain as T
from core import vs3d_data as D
from core.signs import coverage_text
from core.timeutil import ET

BG = "#0e1117"
TEAL, RED = "#26a69a", "#ef5350"
SUBTABS = ["VS3D (combined)", "Book (by strike)", "Terrain (gradient)", "Interval (bubbles)",
           "Market Read", "GEX³ (3-lens)", "DT"]


# ── controls ─────────────────────────────────────────────────────────────
def _expiries(rec, ctl):
    exps_all = rec.all_exps or [str(e) for e in rec.exps]
    n = int(st.session_state.get("vs_nexp", 1))
    exp0 = ctl["exp"]
    i0 = exps_all.index(exp0) if exp0 in exps_all else 0
    exps = exps_all[i0:i0 + n] if exps_all else []
    for e in exps:
        rec.request_expiry(e)
    return exps


THIRD = ["Net flow (participant view)", "Naive calls+/puts−", "none"]


def _book_controls():
    with st.container(border=True):
        c = st.columns([1.5, 0.35, 0.35, 0.35, 1.1, 1.0, 1.1, 1.1])
        c[0].selectbox("Third chart", THIRD, index=0, key="vs_third", label_visibility="collapsed",
                       help="Charts 1 (flow-signed) and 2 (clean-B single-leg) are always shown; pick the third.")
        if c[1].button("➕", key="vs_zin", help="zoom in (strikes)"):
            st.session_state["vs_zoom"] = max(0.25, st.session_state.get("vs_zoom", 1.0) * 0.7)
        if c[2].button("➖", key="vs_zout", help="zoom out"):
            st.session_state["vs_zoom"] = min(1.0, st.session_state.get("vs_zoom", 1.0) / 0.7)
        if c[3].button("↔", key="vs_zfull", help="full range"):
            st.session_state["vs_zoom"] = 1.0
        c[4].checkbox("Comparison dots", True, key="vs_dots", help="yesterday-final (seed) dots + exhausted sticks")
        c[5].checkbox("1× straddle", True, key="vs_strad")
        c[6].checkbox("Δ ladder (orange)", False, key="vs_delta",
                      help="intraday-change METHOD vs the 09:30 book; ⚡ badge on a side's sign flip")
        c[7].checkbox("Spot path (chart 1)", True, key="vs_spot")


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


def _img(png: bytes, caption: str | None = None, width="stretch"):
    st.image(png, caption=caption, width=width)


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


def build_read(rec, exps, ts_ms):
    """Market Read: verdict, METHOD card, full read figure, legacy signals board."""
    ri = D.read_inputs(rec, exps, ts_ms)
    if ri is None or ri["ch0"].empty or not ri["ch0"]["gamma"].notna().any():
        return None
    ch, ch0, spot, now, e0 = ri["ch"], ri["ch0"], ri["spot"], ri["now"], ri["e0"]
    v = RD.read_verdict(ch0, spot, e0, now, ri["prev"], ri["gmag_hist"], ri["strad_open"], ri["open_lbl"], ri["vix"])
    day = D.session_date(rec)
    target = rec.exps[0] if rec.exps else day
    is_today = day == target
    ref, ref_src = D.method_ref(rec, spot, target, now)
    o_str = D.open_straddle(rec, exps, day) if is_today else None
    strad_now = B.mid_straddle(ch0, spot)
    lock = D.card_lock(rec, exps, day, strad_now) if is_today else None
    ds = pd.concat([rec.dsign_table(e) for e in exps], ignore_index=True)
    seed_rows = B.seed_dot_rows(ch, ds)
    flow_rows = B.signed_book_rows(ch, spot, units="contracts")
    hdr, status = None, None
    if isinstance(lock, dict):
        hdr = f"LOCKED {lock['locked_at']} ET — frozen for the session"
        b2 = D.bars_for(rec, day, upto_ms=ts_ms)
        status = b2[b2["ts_ms"] >= lock["ts_ms"]]["c"].dropna().tolist() or None
    elif not is_today or now.time() < dt.time(9, 35):
        hdr = "PREVIEW — pre-open book (yesterday's flow on today's OI) · anchor frozen · locks at first ≥09:35 ET snapshot"
    kw = dict(ref_spot=ref, open_strad=o_str, lock=(lock or {}).get("levels"), status_prices=status, header_note=hdr,
              seed_rows=seed_rows)
    card_png = B.method_card_jpg(B.key_levels_lines(flow_rows, spot, strad_now, "k", "g", "r", "c", "d", "y", **kw))
    lines = B.key_levels_lines(flow_rows, spot, strad_now, "w", "g", "r", "c", "d", "y", **kw)
    ts_open = D.first_snap(rec, exps, day, dt.time(9, 30)) if is_today else None
    if ts_open:                                         # OPEN READ: prior book × the opening spot, frozen
        och, osp, _ = D.frame(rec, exps, ts_open)
        orow = B.signed_book_rows(och, osp, units="contracts")
        out = {}
        if orow is not None:
            B.key_levels_lines(orow, osp, B.mid_straddle(och[och["exp"] == e0], osp), "w", "g", "r", "c", "d", "y",
                               ref_spot=D.true_open(rec, day) or osp, levels_out=out)
        if out.get("ok"):
            ol = out["levels"]; ob = ol.get("bal")
            ou = [t["peak"] for t in ol.get("ups", [])][:1]; od = [t["peak"] for t in ol.get("dns", [])][:1]
            lines.append((f"OPEN READ {D.naive_et(ts_open):%H:%M} — prior book × open {D.true_open(rec, day) or osp:,.0f}: "
                          + (f"BAL {ob['peak']:,.0f}" if ob else "BAL —") + (f" · UP {ou[0]:,.0f}" if ou else " · UP —")
                          + (f" · DN {od[0]:,.0f}" if od else " · DN —"), "c", 11, False))
    label = f"{now:%H:%M:%S}"
    upto = ts_ms or int(dt.datetime.now(ET).timestamp() * 1000)
    hist, fuel0, tape = D.strip_inputs(rec, e0, day, upto)
    strip = B.compute_strip(ch0, spot, now, hist, fuel0, tape, D.vix_today(rec, day))
    fr = RD.read_figure(v, label, lines)
    fs = RD.signals_board(v, ch0, spot, label, e0, ri["n_snaps"], ri["gmag_hist"], now)
    return dict(v=v, card=card_png, hdr=hdr, strip=strip, read=B.fig_png(fr), board=B.fig_png(fs), ref_src=ref_src)


def build_interval(rec, exps, ts_ms):
    ss = st.session_state
    scope0 = (ss.get("iv2_scope") or "All aggregated expiries") != "All aggregated expiries"
    use = exps[:1] if scope0 else exps
    spot, _ = rec.spot_now()
    p = pd.concat([rec.prints_df(e) for e in use], ignore_index=True)
    d = IV.prep_prints(p, rec.greeks, spot)
    target = rec.exps[0] if rec.exps else D.session_date(rec)
    day = D.session_date(rec)
    if len(d):
        d = d[d["ts"].dt.date == day]
    bars = D.bars_for(rec, day, upto_ms=ts_ms)
    signed = ss.get("iv2_signed", True)
    dsign = {}
    if signed:
        for e in use:
            t = rec.dsign_table(e)
            dsign.update(dict(zip(t["sym"], t["dsign"])))
    fig = IV.interval_figure(d, bars, day, dsign, signed, ss.get("iv2_rth", True), int(ss.get("iv2_top", 5)),
                             float(ss.get("iv2_zthr", 3.0)))
    note = None if day == target else f"showing the last recorded session ({day:%a %d %b}); the next session fills from 09:30"
    return B.fig_png(fig), note


def build_dt(rec, exps, ts_ms):
    ss = st.session_state
    e0 = exps[0]
    day = D.session_date(rec)
    spot, _ = rec.spot_now()
    p = IV.prep_prints(rec.prints_df(e0), rec.greeks, spot)
    op = D.et_ms(day, dt.time(9, 30))
    live = p[(p["ts_ms"] >= op) & (p["ts"].dt.date == day)] if len(p) else p
    bars = D.bars_for(rec, day, upto_ms=ts_ms)
    band, floor_, prox = float(ss.get("dt_band", 5.0)), float(ss.get("dt_floor", 200)), float(ss.get("dt_prox", 0.75))
    ev = IV.dt_events(rec.dsign_table(e0), live, bars, band, floor_, prox, int(ss.get("dt_watch", 10)))
    return B.fig_png(IV.dt_figure(ev, bars, day, band, floor_, prox)), len(ev)


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
    e0 = exps[0]
    ch0 = ch[ch["exp"] == e0]
    strad_now = B.mid_straddle(ch0, spot)
    strad = strad_now if ss.get("vs_strad", True) else None

    # dsign tables (seed / live split) for dots and paper lenses
    ds = pd.concat([rec.dsign_table(e) for e in exps], ignore_index=True)
    ds1 = pd.concat([rec.dsign_table(e, single_leg=True) for e in exps], ignore_index=True)
    seed_rows = B.seed_dot_rows(ch, ds)

    show_dots = ss.get("vs_dots", True)
    flow_sg = B.signed_book_rows(ch, spot, units="contracts")
    clean_sg, clean_dot = B.cleanB_rows(ds1, "all"), B.cleanB_rows(ds1, "seed")
    third = ss.get("vs_third") or THIRD[0]
    if flow_sg is None:
        notes.append("no flow-signed data in this frame — chart 1 shows naive bars")
    if clean_sg is None:
        notes.append("no single-leg prints yet — chart 2 empty")

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

    lv = dict(lock_levels=(lock or {}).get("levels"), preview_levels=prev_lv, intraday_levels=ilv,
              show_delta=ss.get("vs_delta", False))
    FS = (5.4, 8.2)
    nb = B.naive_book(ch)
    charts = []
    f1 = B.book_figure(nb, spot, strad, lo, hi, signed=flow_sg, signed_open=seed_rows if show_dots else None,
                       signmode="flow", figsize=FS, title="1 · FLOW-SIGNED (MM-inferred)", **lv)
    if ss.get("vs_spot", True):
        bars = D.bars_for(rec, day, upto_ms=ts_ms)
        from core import session as S
        f1 = B.book_spot_overlay(f1, bars, S.open_dt(day), S.close_dt(day))
    charts.append(B.fig_png(f1))
    f2 = B.book_figure(nb, spot, strad, lo, hi, signed=clean_sg if clean_sg is not None else pd.DataFrame(
        columns=["strike", "signed_pct", "conf"]), signed_open=clean_dot if show_dots else None, signmode="clean",
        figsize=FS, title="2 · CLEAN-B (single-leg tape)", lock_suffix=" ·flow-lock", **lv)
    charts.append(B.fig_png(f2))
    if third.startswith("Net"):
        f3 = B.book_figure(nb, spot, strad, lo, hi, signed=B.netflow_rows(ds, True),
                           signed_open=B.netflow_rows(ds, False) if show_dots else None, signmode="net",
                           figsize=FS, title="3 · NET FLOW (participant view)", lock_suffix=" ·flow-lock", **lv)
        charts.append(B.fig_png(f3))
    elif third.startswith("Naive"):
        f3 = B.book_figure(nb, spot, strad, lo, hi, signed=None, figsize=FS, title="3 · NAIVE calls+/puts−",
                           lock_suffix=" ·flow-lock", **lv)
        charts.append(B.fig_png(f3))
    png = charts[0]

    card = None
    if True:                                        # card always on (R3)
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
    if len(ch0):                                    # strip always on (R3)
        upto = ts_ms or int(dt.datetime.now(ET).timestamp() * 1000)
        hist, fuel0, tape = D.strip_inputs(rec, e0, day, upto)
        strip = B.compute_strip(ch0, spot, now, hist, fuel0, tape, D.vix_today(rec, day))

    s0 = f"${o_str:.2f} open" if o_str else (f"${strad_now:.2f} now" if strad_now else "n/a")
    frame_lbl = "snapshot " + D.naive_et(ts_ms).strftime("%a %H:%M") if ts_ms else "LIVE"
    cap = (f"{' + '.join(exps)} · {frame_lbl} · spot {spot:,.2f} · showing {int(lo)}–{int(hi)} · "
           f"zoom ×{z:.2f} · ref {ref:,.2f} ({ref_src}) · S0 {s0}")
    return dict(png=png, charts=charts, card=card, strip=strip, cap=cap, div=div,
                cov=coverage_text(ds), ch=ch, spot=spot, lo=lo, hi=hi)


def render(rec, ctl, ts_ms=None):
    """VS3D, drawn as of ts_ms (None = live; the universal player sets it)."""
    with st.expander("🌐 VS3D — expiries to aggregate", expanded=False):
        st.slider("Expiries to aggregate", 1, 5, 1, key="vs_nexp",
                  help="Book, card, terrain and GEX³ sum the first N listed expiries from the one picked above.")
    exps = _expiries(rec, ctl)
    tabs = st.tabs(SUBTABS, key="vs_sub", on_change="rerun")
    if not ctl["exp"] or not exps:
        with tabs[0]:
            st.info("waiting for the chain")
        return
    notes: list[str] = []

    def _book():
        try:
            return build_book(rec, exps, ts_ms, ctl, notes)
        except Exception as e:                               # noqa: BLE001
            notes.append(f"⚠ book error: {type(e).__name__}: {e}")
            return None

    if tabs[0].open:
        with tabs[0]:
            bk = _book()
            if bk is None:
                st.info("waiting for greeks / OI / spot")
                for n in notes:
                    st.caption(n)
            else:
                _render_strip(bk["strip"])
                st.caption(bk["cap"] + " · " + bk["cov"])
                a, c = st.columns([1.0, 1.5], gap="small")
                with a:
                    _img(bk["png"])
                with c:
                    try:
                        pngs, tn = build_terrain(rec, exps, ts_ms, ctl, canonical=True)
                    except Exception as e:                   # noqa: BLE001
                        pngs, tn = None, [f"⚠ terrain error: {type(e).__name__}: {e}"]
                    for n_ in tn:
                        st.caption(n_)
                    for p_ in (pngs or []):
                        _img(p_)
    if tabs[1].open:
        with tabs[1]:
            _book_controls()
            bk = _book()
            if bk is None:
                st.info("waiting for greeks / OI / spot")
                for n in notes:
                    st.caption(n)
            else:
                _render_strip(bk["strip"])
                cols = st.columns([0.95] + [1.0] * len(bk["charts"]), gap="small")
                with cols[0]:
                    if bk["card"]:
                        if bk["card"][0]:
                            st.caption(bk["card"][0])
                        _img(bk["card"][1])
                        st.download_button("⬇ card", bk["card"][1], file_name=f"book_card_{dt.date.today()}.png",
                                           mime="image/png", key="dl_card")
                    if bk["div"]:
                        st.caption(f"⚡ Δ-book divergence — {bk['div']}")
                    for n in notes:
                        st.caption(n)
                for col, png in zip(cols[1:], bk["charts"]):
                    with col:
                        _img(png)
                st.caption(bk["cap"] + " · " + bk["cov"])
    if tabs[2].open:
        with tabs[2]:
            _terrain_controls()
            try:
                pngs, tn = build_terrain(rec, exps, ts_ms, ctl)
            except Exception as e:                           # noqa: BLE001
                pngs, tn = None, [f"⚠ terrain error: {type(e).__name__}: {e}"]
            st.caption("Gradient: chosen greek across price × time for the aggregated book · dotted = zero boundary · "
                       "orange = ridge/trough" + ("".join(f" · {n_}" for n_ in tn)))
            for p_ in (pngs or []):
                _img(p_)
    if tabs[5].open:
        with tabs[5]:
            with st.expander("⚙ GEX³ controls", expanded=False):
                g1, g2, g3 = st.columns(3)
                g1.slider("panel height (inches)", 3.0, 8.0, 5.5, 0.5, key="g3h")
                g2.slider("± % price room (display)", 0.25, 3.0, 0.5, 0.25, key="g3room",
                          help="absolute view height around spot — 0.5% default; the model computes on the full chain.")
                g3.slider("density width (share of panel)", 0.25, 0.60, 0.45, 0.05, key="g3wd")
                g1.radio("Panel-3 weight", ["Δ-OI overnight", "live volume"], horizontal=True, key="g3w")
                g2.radio("Panel-3 sign", ["signed (dsign)", "naive"], horizontal=True, key="g3s")
            st.caption("GEX³ — NIFTY GEX model on three lenses · display-only · P1 assumed convention · P2 tape-signed · "
                       "P3 Δ-OI overnight (recorded) or live volume")
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
    if tabs[3].open:
        with tabs[3]:
            c1, c2, c3, c4, c5 = st.columns([1.8, 1.0, 0.8, 1.3, 1.0])
            c1.radio("Scope", ["All aggregated expiries", "0DTE only"], horizontal=True, key="iv2_scope")
            c2.checkbox("RTH display (9:30–16:00)", True, key="iv2_rth")
            c3.selectbox("Top strikes", [5, 10], index=0, key="iv2_top")
            c4.slider("Burst z ≥", 2.0, 6.0, 3.0, 0.5, key="iv2_zthr", help="Lower = more dots.")
            c5.checkbox("Signed (dsign)", True, key="iv2_signed")
            st.caption("Interval bubbles — cumulative exposure of traded volume per strike (5-min buckets) · size = gross · "
                       "colour = sign (blue + / red −) · orange dots = single-leg premium bursts (ring green = call-led, "
                       "orange = put-led) · white = SPX")
            try:
                png, note = build_interval(rec, exps, ts_ms)
                if note:
                    st.caption(note)
                _img(png)
            except Exception as e:                           # noqa: BLE001
                st.caption(f"⚠ interval error: {type(e).__name__}: {e}")
    if tabs[4].open:
        with tabs[4]:
            try:
                rd = build_read(rec, exps, ts_ms)
            except Exception as e:                           # noqa: BLE001
                rd = None
                st.caption(f"⚠ read error: {type(e).__name__}: {e}")
            if rd is None:
                st.info("waiting for greeks / OI / spot")
            else:
                a, b = st.columns([2.2, 1])
                with a:
                    _render_strip(rd["strip"])
                    if rd["hdr"]:
                        st.caption(rd["hdr"])
                    _img(rd["card"], "METHOD card — right-click copy, or download")
                with b:
                    st.download_button("⬇ card", rd["card"], file_name=f"method_card_{dt.date.today()}.png",
                                       mime="image/png", key="dl_mcard")
                    v = rd["v"]
                    st.metric("Confidence", f"{v['conf']}/100", help="cheat-sheet engine: γ env × charm lean, gated")
                    st.caption(("▲ " if v["up"] else "▼ ") + v["pat"])
                with st.expander("📊 full read & diagnostics (cheat-sheet engine)", expanded=False):
                    st.caption("γ environment × charm lean → one of four day patterns, gated by the charm clock, straddle "
                               "check, VIX/vanna regime, fishbone and γ-absorption. Proxy-honest: a weighted coin, not an oracle.")
                    _img(rd["read"])
                with st.expander("🧭 diagnostics (legacy Signals — §5.1 workflow)", expanded=False):
                    _img(rd["board"])
    if tabs[6].open:
        with tabs[6]:
            st.caption("DT — repositioning tape · netflow lens (participant) · a square marks the minute a strike's "
                       "net paper crosses a new band vs its yesterday-final dot · causal, never repaints")
            d1, d2, d3, d4 = st.columns(4)
            d1.slider("band % of dot", 1.0, 25.0, 5.0, 0.5, key="dt_band")
            d2.slider("abs floor (contracts)", 50, 1000, 200, 25, key="dt_floor")
            d3.slider("± % of spot", 0.2, 2.0, 0.75, 0.05, key="dt_prox")
            d4.slider("watch strikes", 4, 30, 10, 1, key="dt_watch")
            try:
                png, n_ev = build_dt(rec, exps, ts_ms)
                _img(png)
            except Exception as e:                           # noqa: BLE001
                st.caption(f"⚠ DT error: {type(e).__name__}: {e}")
