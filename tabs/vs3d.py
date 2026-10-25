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
from core import loader as LD
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


THIRD = ["2 charts (no third)", "+ Net flow (participant view)", "+ Naive calls+/puts−"]


def _book_controls():
    with st.container(border=True):
        c = st.columns([1.5, 0.35, 0.35, 0.35, 1.1, 1.0, 1.1, 1.1])
        c[0].selectbox("Third chart", THIRD, index=0, key="vs_third", label_visibility="collapsed",
                       help="Charts 1 (flow-signed) and 2 (clean-B single-leg) are always shown; add a third and all three share the width.")
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
        c[7].checkbox("Spot path", True, key="vs_spot", help="white price path on every chart, session time along the top")


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
    from core import session as _S
    key = ("terr", _S.gth(), tuple(exps), ts_ms or int(now.timestamp() // 30), round(spot, 1), repr(sorted(o.items())),
           round(float(ch["oi"].fillna(0).sum())), round(float(ch["dsign"].fillna(0).sum()), 2) if "dsign" in ch else 0,
           repr(sorted((k, round(v, 3)) for k, v in caps.items() if k.startswith("terr_cap_"))))
    cache = rec.ui_state.setdefault("_terr_png", {})
    if key in cache:
        return cache[key]
    LD.stage("terrain field", 0.5)
    # v0.19 L36: frozen past columns, shared by every viewer for this day + field options (rec.ui_state)
    fstore = rec.ui_state.setdefault("_terr_frozen", {})
    fkey = (str(axis_day), tuple(exps), T.frozen_sig(o))
    for k_ in [k_ for k_ in fstore if k_[0] != str(axis_day)]:
        fstore.pop(k_, None)
    frozen = fstore.setdefault(fkey, {})
    h_ = rec.chain_df()
    snaps = np.unique(h_["ts_ms"].values) if len(h_) else np.array([], dtype=np.int64)

    def _backfill(tau):
        """chain as RECORDED at tau (nearest snapshot at or before it, ≤ 10 min old) → (chain, spot, time)."""
        if not len(snaps):
            return None
        from core.timeutil import ET as _ET
        ms = int(pd.Timestamp(tau).tz_localize(_ET).timestamp() * 1000)
        i = np.searchsorted(snaps, ms, side="right") - 1
        if i < 0 or ms - int(snaps[i]) > 10 * 60_000:
            return None
        ch_j, spot_j, now_j = D.frame(rec, exps, int(snaps[i]))
        if ch_j.empty or not spot_j == spot_j:
            return None
        return ch_j, spot_j, now_j
    figs, notes = T.terrain_figures(ch, spot, exps, now, axis_day, bars, o, caps, peak, frozen=frozen, backfill=_backfill)
    LD.stage("rendering terrain", 0.85)
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
    LD.stage("GEX³ three lenses", 0.5)
    fig, rd, notes = G.gex3_figure(ch, spot, exps[0], axis_day, bars, doi, ss.get("g3w") or "Δ-OI overnight",
                                   ss.get("g3s") or "signed (dsign)", float(ss.get("g3room", 0.5)) / 100.0,
                                   float(ss.get("g3wd", 0.45)), float(ss.get("g3h", 5.5)),
                                   (lock or {}).get("levels"))
    html, det = G.readout_html(rd)
    return B.fig_png(fig), html, det, notes


def build_read(rec, exps, ts_ms):
    """Market Read: verdict, METHOD card, full read figure, legacy signals board."""
    LD.stage("market read inputs", 0.3)
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
    LD.stage("interval bubbles", 0.6)
    fig = IV.interval_figure(d, bars, day, dsign, signed, ss.get("iv2_rth", True), int(ss.get("iv2_top", 5)),
                             float(ss.get("iv2_zthr", 3.0)), ss.get("iv2_fit", True), ss.get("iv2_now", True))
    note = None if day == target else f"showing the last recorded session ({day:%a %d %b}); the next session fills from 09:30"
    return B.fig_png(fig), note


def build_dt(rec, exps, ts_ms):
    ss = st.session_state
    e0 = exps[0]
    day = D.session_date(rec)
    spot, _ = rec.spot_now()
    from core import session as S
    p = IV.prep_prints(rec.prints_df(e0), rec.greeks, spot)
    op = D.et_ms(day, dt.time(9, 30))
    gth = S.gth() and ss.get("dt_gth", True)
    st0 = S.ms(S.open_dt(day)) if gth else op            # L4: count from 20:15 when GTH is on
    if ts_ms:
        p = p[p["ts_ms"] <= ts_ms] if len(p) else p
    live = p[(p["ts_ms"] >= st0) & (p["ts_ms"] < S.ms(S.close_dt(day)))] if len(p) else p
    adj = IV.netflow_by_strike(p[(p["ts_ms"] >= st0) & (p["ts_ms"] < op)]) if (gth and len(p)) else None
    bars = D.bars_for(rec, day, upto_ms=ts_ms)
    band, floor_, prox = float(ss.get("dt_band", 5.0)), float(ss.get("dt_floor", 200)), float(ss.get("dt_prox", 0.75))
    LD.stage("DT replay minute by minute", 0.5)
    ev = IV.dt_events(rec.dsign_table(e0), live, bars, band, floor_, prox, int(ss.get("dt_watch", 10)), dot_adj=adj)
    x0 = S.open_dt(day) if gth else dt.datetime.combine(day, dt.time(9, 30)) - dt.timedelta(minutes=10)
    return B.fig_png(IV.dt_figure(ev, bars, day, band, floor_, prox, start=x0)), len(ev)


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
    LD.stage("loading chain", 0.10)
    ch, spot, now = D.frame(rec, exps, ts_ms)
    if ch.empty or not spot == spot or not ch["gamma"].notna().any():
        return None
    day = D.session_date(rec)
    e0 = exps[0]
    LD.stage("dealer signs", 0.22)
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

    LD.stage("chart 1 · flow-signed", 0.45)
    lv = dict(lock_levels=(lock or {}).get("levels"), preview_levels=prev_lv, intraday_levels=ilv,
              show_delta=ss.get("vs_delta", False))
    FS = (5.4, 8.2)
    nb = B.naive_book(ch)
    charts = []
    f1 = B.book_figure(nb, spot, strad, lo, hi, signed=flow_sg, signed_open=seed_rows if show_dots else None,
                       signmode="flow", figsize=FS, title="1 · FLOW-SIGNED (MM-inferred)", **lv)
    sp_bars = D.bars_for(rec, day, upto_ms=ts_ms) if ss.get("vs_spot", True) else None
    from core import session as S

    def _sp(f):
        return B.book_spot_overlay(f, sp_bars, S.open_dt(day), S.close_dt(day)) if sp_bars is not None else f
    charts.append(B.fig_png(_sp(f1)))
    LD.stage("chart 2 · clean-B", 0.60)
    f2 = B.book_figure(nb, spot, strad, lo, hi, signed=clean_sg if clean_sg is not None else pd.DataFrame(
        columns=["strike", "signed_pct", "conf"]), signed_open=clean_dot if show_dots else None, signmode="clean",
        figsize=FS, title="2 · CLEAN-B (single-leg tape)", lock_suffix=" ·flow-lock", **lv)
    charts.append(B.fig_png(_sp(f2)))
    if third != THIRD[0]:
        LD.stage("chart 3", 0.70)
    if "Net" in third:
        f3 = B.book_figure(nb, spot, strad, lo, hi, signed=B.netflow_rows(ds, True),
                           signed_open=B.netflow_rows(ds, False) if show_dots else None, signmode="net",
                           figsize=FS, title="3 · NET FLOW (participant view)", lock_suffix=" ·flow-lock", **lv)
        charts.append(B.fig_png(_sp(f3)))
    elif "Naive" in third:
        f3 = B.book_figure(nb, spot, strad, lo, hi, signed=None, figsize=FS, title="3 · NAIVE calls+/puts−",
                           lock_suffix=" ·flow-lock", **lv)
        charts.append(B.fig_png(_sp(f3)))
    png = charts[0]

    LD.stage("key-levels card", 0.80)
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

    LD.stage("strip", 0.90)
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
                if bk["card"]:                       # card on top, compact (L5)
                    k1, k2 = st.columns([0.62, 1.38], gap="small")     # v0.18 L31: card ≈ 40 % of its old area
                    with k1:
                        _img(bk["card"][1], width=460)
                    with k2:
                        if bk["card"][0]:
                            st.caption(bk["card"][0])
                        if bk["div"]:
                            st.caption(f"⚡ Δ-book divergence — {bk['div']}")
                        for n in notes:
                            st.caption(n)
                cols = st.columns(len(bk["charts"]), gap="small")
                for col, png in zip(cols, bk["charts"]):
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
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1.8, 1.0, 0.8, 1.3, 1.0, 1.0, 1.0])
            c1.radio("Scope", ["All aggregated expiries", "0DTE only"], horizontal=True, key="iv2_scope")
            c2.checkbox("Session x-axis", True, key="iv2_rth", help="fix the x-axis to the session (20:15 with GTH on, else 09:30)")
            c6.checkbox("Fit y", True, key="iv2_fit", help="y range = top strikes + price path, not the whole chain")
            c7.checkbox("End at now", True, key="iv2_now", help="end the time axis at the latest data + 20 min")
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
            dmode = st.segmented_control("DT mode", ["v2 · tested", "signals"], default="v2 · tested", key="dt_mode",
                                         label_visibility="collapsed",
                                         help="v2 = the settings that held up out of sample on 11 sessions (research/l24): "
                                              "adaptive band, follow arrows, GEX gate, initiation, live scorecard. "
                                              "signals (v0.18, replaces classic) = clean price + arrows: shape = signal, "
                                              "size = tier, hollow = no proven edge, with each signal's record.")
            if dmode == "signals":
                _signals(rec, exps, ts_ms)
            else:
                _dt_v2(rec, exps, ts_ms, ctl)


def _dt_classic(rec, exps, ts_ms):
    st.caption("DT classic — repositioning tape · netflow lens (participant) · a square marks the minute a strike's "
               "net paper crosses a new band vs its yesterday-final dot · causal, never repaints · "
               "tested (research/l24): following these squares had no edge; fading ABSORBED bursts (≥3 strikes, "
               "price within 1 pt) was the useful reading · hollow/filled did not match next-morning OI")
    st.markdown(
        "<div style='font-size:.85rem;line-height:1.7'>"
        "<span style='color:#1e90ff'>■</span> blue filled = bullish, extending (net-long strike adds, or fresh paper bought) · "
        "<span style='color:#1e90ff'>□</span> blue hollow = bullish, receding (net-short strike covered) · "
        "<span style='color:#ff00ff'>■</span> magenta filled = bearish, extending (net-short strike adds, or fresh paper sold) · "
        "<span style='color:#ff00ff'>□</span> magenta hollow = bearish, receding (net-long strike unwound) · "
        "no prior position (|dot| below the floor) → always filled · one square per new band crossed</div>",
        unsafe_allow_html=True)
    d1, d2, d3, d4, d5 = st.columns([1, 1, 1, 1, 0.8])
    d5.checkbox("From 20:15 (GTH)", True, key="dt_gth",
                help="with 🌙 GTH on: dot = book at 20:15 and overnight prints count as moves; off: from 09:30 only")
    d1.slider("band % of dot", 1.0, 25.0, 5.0, 0.5, key="dt_band")
    d2.slider("abs floor (contracts)", 50, 1000, 200, 25, key="dt_floor")
    d3.slider("± % of spot", 0.2, 2.0, 0.75, 0.05, key="dt_prox")
    d4.slider("watch strikes", 4, 30, 10, 1, key="dt_watch")
    try:
        png, n_ev = build_dt(rec, exps, ts_ms)
        _img(png)
    except Exception as e:                           # noqa: BLE001
        st.caption(f"⚠ DT error: {type(e).__name__}: {e}")


# ── SIGNALS (v0.18.0, L30 — replaces DT classic) ───────────────────────────────────────────────
def _signals(rec, exps, ts_ms):
    """v0.19 L35b: ONE sensitivity slider. Each position = the settings a WALK-FORWARD test picked (chosen on earlier days,
    scored only on later days it never saw — research/l35). Filled marks = passed; unproven hidden unless toggled."""
    from core import signals as SG
    ss = st.session_state
    c1, c3, c2 = st.columns([3, 1.1, 1.2])
    smode = c3.segmented_control("tape", ["0DTE", "0+1DTE"], default="0DTE", key="sig_mode", label_visibility="collapsed",
                                 help="0DTE = every signal on today's expiry · 0+1DTE = every signal on today's AND the next "
                                      "expiry (AG's ridges include 1DTE). Each mode has its own walk-forward record.") or "0DTE"
    pos = c1.select_slider("Signal sensitivity", options=SG.POSITIONS, value="middle", key="sig_pos",
                           help="fewer ↔ more marks. Each position uses the thresholds a walk-forward test chose "
                                "(22 sessions: chosen on earlier days, scored on the next 3, rolled 4 times).")
    show_u = c2.toggle("show unproven", value=False, key="sig_unproven",
                       help="also draw signals that did NOT pass the walk-forward test, as hollow marks")
    wf = SG.wf_table(smode)
    r = wf[wf["position"] == (pos or "middle")]
    npass = int(r["PASS"].sum()) if len(r) else 0
    st.caption(f"**{pos} · {smode}** — {npass} of {len(r)} signals passed the walk-forward test at this sensitivity (pooled test-day edge "
               "> 0, t ≥ 2, ≥ 3 of 4 test blocks positive). 6 signals × 3 positions were tested, so about one pass is "
               "expected by luck alone — treat a pass as 'worth watching', not proven.")
    try:
        res = build_signals(rec, exps, ts_ms, pos or "middle", bool(show_u), smode)
    except Exception as e:                                       # noqa: BLE001
        st.caption(f"⚠ signals error: {type(e).__name__}: {e}")
        return
    if res is None:
        st.info("Signals need the regular session (09:30–16:00): no minutes yet.")
        return
    fig, tbl, card = res
    st.plotly_chart(fig, width="stretch", key="sig_fig")
    a, b = st.columns([1.5, 1])
    with a:
        st.markdown("**Out-of-sample record at this sensitivity** (test days only)")
        st.dataframe(tbl, hide_index=True, width="stretch")
    with b:
        st.markdown("**Today** — every mark, SPX points after it in the mark's direction")
        if len(card):
            show = card.assign(t=card["t"].dt.strftime("%H:%M"), dir=card["d"].map({1: "▲", -1: "▼"}))
            st.dataframe(show[["t", "code", "dir", "verdict", "px", "fw10", "fw20", "fw30"]].iloc[::-1].round(1),
                         hide_index=True, width="stretch", height=min(600, 38 + 35 * len(show)))
        else:
            st.caption("no marks yet today")
    with st.expander("what each signal is"):
        for code, (name, mk, tiers, what) in SG.SIG.items():
            st.markdown(f"**{code} {name}** ({mk}) — {what}")


def build_signals(rec, exps, ts_ms, position="middle", show_unproven=False, mode="0DTE"):
    from core import signals as SG
    from core import session as S
    from tabs import agrev3d as R3
    e0 = exps[0]
    day = D.session_date(rec)
    spot_now, _ = rec.spot_now()
    LD.stage("signals · minute flow", 0.3)
    use = R3.ridge_exps(rec, e0, "0+1DTE")
    ps = []
    for e_ in use:
        q = IV.prep_prints(rec.prints_df(e_), rec.greeks, spot_now)
        if ts_ms and len(q):
            q = q[q["ts_ms"] <= ts_ms]
        if len(q):
            ps.append(q[S.mask(q["ts"], day)])
    p = pd.concat(ps, ignore_index=True) if ps else None
    c1 = R3.candles_for(rec, use, day)
    if c1 is not None and ts_ms:
        c1 = c1[c1["ts_ms"] <= ts_ms]
    with rec.lock:
        legs = dict(rec.legs)
    bars = D.bars_for(rec, day, upto_ms=ts_ms)
    if bars is None or bars.empty:
        return None
    o_, end = pd.Timestamp(dt.datetime.combine(day, dt.time(9, 30))), pd.Timestamp(dt.datetime.combine(day, dt.time(15, 59)))
    last = min(pd.Timestamp(bars["t"].max()), end)
    if last < o_ + pd.Timedelta(minutes=15):
        return None
    rth = pd.date_range(o_, last, freq="1min")
    spot = pd.Series(bars["c"].astype(float).values, index=pd.to_datetime(bars["t"]).dt.floor("1min"))
    spot = spot[~spot.index.duplicated(keep="last")].reindex(rth).ffill()
    key = ("sig2", str(day), len(rth), 0 if p is None else len(p), 0 if c1 is None else len(c1), ts_ms, position, show_unproven, mode)
    cache = rec.ui_state.setdefault("_signals", {})
    if key in cache:
        return cache[key]
    o = SG.minute_flow(c1, p, legs)
    LD.stage("signals · rules", 0.6)
    wf = SG.wf_table(mode)
    ev = SG.compute_picks(o, spot, rth, day, SG.picks_for(position, wf), mode)
    card = SG.score(ev, spot)
    if len(card):
        okd = {r.code: bool(r.PASS) for r in wf[wf["position"] == position].itertuples()}
        card["verdict"] = ["passed" if okd.get(c) else "no edge" for c in card["code"]]
    res = (SG.figure_wf(ev, spot, wf, position, day, show_unproven), SG.wf_rows(wf, position, ev), card)
    while len(cache) >= 3:
        cache.pop(next(iter(cache)))
    cache[key] = res
    try:
        rec.ui_state.setdefault("_sig_cards", {})[str(day)] = card.assign(day=str(day), position=position, mode=mode)
    except Exception:                                            # noqa: BLE001
        pass
    return res


# ── DT v2 (v0.17.0): tested defaults · follow arrows · GEX gate · initiation · scorecard ──────────────
SENS = {"fewer": dict(alpha=0.50, floor=400.0, need=3, note="untested — fewer, stronger squares"),
        "tested": dict(alpha=0.25, floor=200.0, need=2, note="the setting that held up out of sample (research/l24)"),
        "more": dict(alpha=0.15, floor=100.0, need=1, note="untested — more, weaker squares")}


def _dt_v2(rec, exps, ts_ms, ctl=None):
    """v0.19 L37: ONE sensitivity slider; ± range from the control bar's strike window (top of the page)."""
    from core import dtv2 as V
    ss = st.session_state
    a_, b_ = st.columns([3, 1.1])
    dmode = b_.segmented_control("DT tape", ["0DTE", "0+1DTE"], default="0DTE", key="dt2_mode", label_visibility="collapsed",
                                 help="0DTE = squares from today's expiry (the tested setting) · 0+1DTE = today's and the next "
                                      "expiry's flow summed per strike (untested)") or "0DTE"
    sens = a_.select_slider("DT sensitivity", options=list(SENS), value="tested", key="dt2_sens",
                            help="fewer ↔ more squares and arrows. 'tested' = α 0.25 · floor 200 · follow ≥ 2 strikes "
                                 "(held up on 11 sessions); the ends are untested.")
    cfg = SENS[sens or "tested"]
    spot_now, _ = rec.spot_now()
    if ctl and spot_now == spot_now:
        prox = float(ctl["pct"]) if ctl.get("mode") == "% move" else float(ctl.get("n", 20)) * 5.0 / spot_now * 100.0
    else:
        prox = V.PROX
    prox = float(np.clip(prox, 0.05, 5.0))
    with st.expander("advanced (fixed at the tested values)", expanded=False):
        watch = st.slider("watch strikes", 4, 30, V.WATCH, 1, key="dt2_watch")
        cool = st.slider("per-strike cooldown (min)", 0, 30, V.COOLDOWN, 1, key="dt2_cool")
    alpha, floor, need = cfg["alpha"], cfg["floor"], cfg["need"]
    st.caption(f"DT v2 · sensitivity **{sens}** ({cfg['note']}) · watch ±{prox:.2f} % of spot from the control bar's strike "
               f"window (tested value was ±0.30 %) · squares = a strike's net paper crossing max(floor, α × its own 30-min "
               "volume) · ▲▼ follow = ≥ N strikes the same colour within 3 min (grey when dealer GEX ≤ 0) · ● initiation · "
               "scorecard = SPX 10 / 20 / 30 min later. Treat as context — no proven edge.")
    try:
        res = build_dt2(rec, exps, ts_ms, alpha, float(floor), prox, int(watch), int(cool), int(need), dmode)
    except Exception as e:                                   # noqa: BLE001
        st.caption(f"⚠ DT v2 error: {type(e).__name__}: {e}")
        return
    if res is None:
        st.info("DT v2 needs the regular session (09:30–16:00): no minutes yet for this session.")
        return
    png, card, summ, note = res
    _img(png)
    st.markdown("**Scorecard** — every signal today, scored on the SPX move after it (points, in the signal's direction)")
    if len(summ):
        st.dataframe(summ, hide_index=True, width="stretch")
    if len(card):
        show = card.assign(t=card["t"].dt.strftime("%H:%M"), gex=card["gex_pos"].map({True: "+", False: "−", None: "?"}))
        st.dataframe(show[["t", "type", "dir", "px", "gex", "fw10", "fw20", "fw30"]].iloc[::-1].round(2), hide_index=True,
                     width="stretch", height=min(420, 38 + 35 * len(show)))
    st.caption(note)


def build_dt2(rec, exps, ts_ms, alpha, floor, prox, watch, cool, need, mode="0DTE"):
    from core import dtv2 as V
    from core import session as S
    from core import spikes as SP
    from tabs import agrev3d as R3
    e0 = exps[0]
    day = D.session_date(rec)
    spot_now, _ = rec.spot_now()
    LD.stage("DT v2 · minute flow", 0.3)
    use = R3.ridge_exps(rec, e0, "0+1DTE") if mode == "0+1DTE" else [e0]        # v0.19.1 L41
    ps_ = [IV.prep_prints(rec.prints_df(e_), rec.greeks, spot_now) for e_ in use]
    ps_ = [q for q in ps_ if len(q)]
    p = pd.concat(ps_, ignore_index=True) if len(ps_) > 1 else (ps_[0] if ps_ else IV.prep_prints(rec.prints_df(e0), rec.greeks, spot_now))
    if ts_ms and len(p):
        p = p[p["ts_ms"] <= ts_ms]
    if len(p):
        p = p[S.mask(p["ts"], day)]
    c1 = R3.candles_for(rec, use, day)
    f5 = R3.fill5(rec, use, day, p, c1)
    if f5 is not None:
        c1 = f5 if c1 is None else pd.concat([c1[["m", "sym", "strike", "cp", "size", "prem", "net"]], f5], ignore_index=True)
    mt = R3.merge_candles(SP.minute_table(p) if len(p) else pd.DataFrame(columns=["m", "sym", "strike", "cp", "size", "prem", "net"]), c1)
    bars = D.bars_for(rec, day, upto_ms=ts_ms)
    if bars is None or bars.empty:
        return None
    o, end = pd.Timestamp(dt.datetime.combine(day, dt.time(9, 30))), pd.Timestamp(dt.datetime.combine(day, dt.time(15, 59)))
    last = min(pd.Timestamp(bars["t"].max()), end)
    if last < o:
        return None
    minutes = pd.date_range(o, last, freq="1min")
    spot = pd.Series(bars["c"].astype(float).values, index=pd.to_datetime(bars["t"]).dt.floor("1min"))
    spot = spot[~spot.index.duplicated(keep="last")].reindex(minutes).ffill()
    mt = mt[(mt["m"] >= o) & (mt["m"] <= last)] if len(mt) else mt
    nf, vol = V.minute_frames(mt, minutes)
    ds = rec.dsign_table(e0)
    dot = (ds.assign(nf=np.where(ds["type"] == "call", 1.0, -1.0) * ds["seed_net"]).groupby("strike")["nf"].sum()
           if ds is not None and len(ds) else None)
    LD.stage("DT v2 · squares + signals", 0.55)
    sq = V.squares(nf, vol, spot, dot, alpha=alpha, floor=floor, prox=prox, watch=watch, cooldown=cool)
    fo = V.follow(sq, minutes, need=need)
    ini = V.initiation(nf, vol, spot)
    # GEX gate: morning OI of the 0DTE chain, ATM IV from the chain
    ch = rec.live_chain(e0)
    gex = pd.Series(dtype=float)
    if ch is not None and len(ch) and "oi" in ch:
        legs = ch[["strike", "cp", "oi"]].copy()
        ivs = pd.to_numeric(ch.get("iv"), errors="coerce") if "iv" in ch else pd.Series(dtype=float)
        near = (ch["strike"] - spot_now).abs() <= 25 if spot_now == spot_now else ch["strike"] == ch["strike"]
        iv = float(np.nanmedian(ivs[near])) if ivs is not None and len(ivs) and np.isfinite(ivs[near]).any() else 0.16
        gex = V.gex_path(legs, spot, dt.datetime.combine(day, dt.time(16, 0)), float(np.clip(iv, 0.05, 1.0)))
    card = V.scorecard({"follow": fo, "initiation": ini}, spot, gex)
    try:
        rec.ui_state.setdefault("_dt2_cards", {})[str(day)] = card.assign(day=str(day))
    except Exception:                                        # noqa: BLE001
        pass
    png = B.fig_png(_dt2_figure(sq, fo, ini, gex, spot, minutes, day, prox))
    sq_h = len(sq) / max(len(minutes) / 60.0, 1 / 60)
    note = (f"{' + '.join(use)} · {len(sq)} squares ({sq_h:.0f}/h) · α {alpha:.2f} · floor {int(floor)} · ±{prox:.2f}% · watch {watch} · "
            f"cooldown {cool} min · follow needs {need} · GEX now "
            + (f"{'+' if gex.iloc[-1] > 0 else '−'}${abs(gex.iloc[-1]) / 1e9:.1f}B" if len(gex) and gex.iloc[-1] == gex.iloc[-1] else "—")
            + " · research: follow +1.8 / +2.7 pts per signal at 20 min (weeks 6–13 / 14–20 Oct), initiation +1.1 / +2.6")
    return png, card, V.summarize(card), note


def _dt2_figure(sq, fo, ini, gex, spot, minutes, day, prox):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from core.terrain import DARK
    fg, (ax, ag) = plt.subplots(2, 1, figsize=(12.5, 6.4), dpi=100, sharex=True, gridspec_kw=dict(height_ratios=[5, 0.8], hspace=0.05))
    fg.patch.set_facecolor(DARK)
    for a in (ax, ag):
        a.set_facecolor(DARK); a.tick_params(colors="#8b949e", labelsize=8)
        for spn in a.spines.values():
            spn.set_color("#30363d")
    ax.plot(spot.index, spot.values, color="#e8ecf2", lw=1.1, zorder=4)
    if len(sq):
        for sgn, col in ((1, "#1e90ff"), (-1, "#ff00ff")):
            h = sq[(sq["s"] == sgn) & sq["filled"]]
            ax.scatter(h["t"], h["k"], s=40, marker="s", color=col, lw=0, zorder=5)
            h = sq[(sq["s"] == sgn) & ~sq["filled"]]
            ax.scatter(h["t"], h["k"], s=40, marker="s", facecolors="none", edgecolors=col, lw=1.2, zorder=5)
    gpos = (gex.reindex(minutes) > 0) if len(gex) else pd.Series(False, index=minutes)
    for t, d in fo[fo != 0].items():
        y = spot.get(t, np.nan)
        live = bool(gpos.get(t, False))
        ax.scatter([t], [y + (5 if d > 0 else -5)], marker="^" if d > 0 else "v", s=170, zorder=7,
                   color=("#2ecc71" if d > 0 else "#ff4d6d") if live else "none",
                   edgecolors=("white" if live else "#8b949e"), lw=1.2)
    for t, d in ini[ini != 0].items():
        y = spot.get(t, np.nan)
        ax.scatter([t], [y], marker="o", s=70, zorder=8, color="#ffd166" if d > 0 else "#ff9f1a", edgecolors="black", lw=0.6)
        ax.annotate("▲" if d > 0 else "▼", (t, y), xytext=(0, 9 if d > 0 else -13), textcoords="offset points",
                    color="#ffd166" if d > 0 else "#ff9f1a", fontsize=8, ha="center", zorder=8)
    lo = [float(np.nanmin(spot.values))]; hi = [float(np.nanmax(spot.values))]
    if len(sq):
        lo.append(float(sq["k"].min())); hi.append(float(sq["k"].max()))
    pad = max(5.0, 0.08 * (max(hi) - min(lo)))
    ax.set_ylim(min(lo) - pad, max(hi) + pad)
    if len(gex):
        g = gex.reindex(minutes) / 1e9
        ag.fill_between(g.index, 0, g.values, where=g.values > 0, color="#2ecc71", alpha=0.6, lw=0)
        ag.fill_between(g.index, 0, g.values, where=g.values <= 0, color="#ff4d6d", alpha=0.6, lw=0)
        ag.axhline(0, color="#8b949e", lw=0.6)
    ag.set_ylabel("GEX $B", color="#8b949e", fontsize=7)
    x1 = max(minutes[-1] + pd.Timedelta(minutes=25), minutes[0] + pd.Timedelta(hours=1))
    ax.set_xlim(minutes[0] - pd.Timedelta(minutes=5), min(x1, pd.Timestamp(dt.datetime.combine(day, dt.time(16, 5)))))
    from matplotlib.lines import Line2D
    hs = [Line2D([], [], marker="s", ls="none", ms=7, color="#1e90ff", label="bullish paper (calls bought / puts sold)"),
          Line2D([], [], marker="s", ls="none", ms=7, color="#ff00ff", label="bearish paper"),
          Line2D([], [], marker="s", ls="none", ms=7, mfc="none", mec="#8b949e", label="hollow = against prior book (unverified)"),
          Line2D([], [], marker="^", ls="none", ms=10, color="#2ecc71", mec="white", label="follow ▲▼ (GEX > 0)"),
          Line2D([], [], marker="^", ls="none", ms=10, mfc="none", mec="#8b949e", label="follow, GEX ≤ 0 → stand aside"),
          Line2D([], [], marker="o", ls="none", ms=8, color="#ffd166", mec="black", label="initiation ● (follow)")]
    lg = ax.legend(handles=hs, loc="upper left", bbox_to_anchor=(1.005, 1.0), fontsize=8, facecolor="#11151c",
                   edgecolor="#30363d", labelcolor="#c9d1d9")
    lg.set_zorder(10)
    ax.set_title(f"DT v2 · {len(sq)} squares · {int((fo != 0).sum())} follow · {int((ini != 0).sum())} initiation · watch ±{prox:.2f}%",
                 color="#8b949e", fontsize=9, loc="left")
    ag.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    return fg

