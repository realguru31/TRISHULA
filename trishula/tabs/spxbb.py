"""v0.29.0 — SPX BB tab: 0.05-bid liquidity edges (0DTE / 1DTE toggle), your sold strikes vs the edges, Telegram."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import bb as BB
from core.timeutil import now_et

BLUE, MAG = "#2f8bff", "#e040fb"
GRN_BG, RED_BG = "#123d24", "#4a1420"


def _fig(title, h=360):
    f = go.Figure()
    f.update_layout(template="plotly_dark", paper_bgcolor="#0e1117", plot_bgcolor="#0e1117", height=h,
                    margin=dict(l=8, r=8, t=36, b=8), title=dict(text=title, x=0.01, font=dict(size=13)),
                    showlegend=False, hovermode="x unified")
    f.update_yaxes(side="right", gridcolor="rgba(255,255,255,0.06)")
    f.update_xaxes(gridcolor="rgba(255,255,255,0.04)")
    return f


def _cell(txt, bg="transparent", fg="#e6edf3", bold=False, size="1.0em"):
    return (f"<td style='padding:3px 10px;background:{bg};color:{fg};text-align:right;font-size:{size};"
            f"{'font-weight:700;' if bold else ''}'>{txt}</td>")


MODEL_NOTE = ("0DTE figures are for selling around the open, 1DTE figures for selling around the close. "
              "Later in the session the true risk is lower than shown.")


def _run_model(trk: BB.Tracker):
    """Runs ONLY from the Run model button (v0.30.0). Everything shown is frozen into session_state here."""
    from core import edge_model as EM
    mode = st.session_state.get("bb_mode", trk.cfg["mode"])
    exp, expired = trk.exp_for(mode)
    spot, src = trk.rec.spot_now()
    if exp is None or not spot == spot:
        st.session_state["bb_model"] = {"error": "no expiry or spot yet"}
        return
    run = EM.run_model(toggle=mode, spot=spot, now_et=now_et().replace(tzinfo=None), spot_source=src)
    # bids snapshot at the press: every strike of that expiry with a bid, spot out to MAX_RANGE_PCT
    lim = EM.MAX_RANGE_PCT / 100.0
    rows = []
    meta = dict(getattr(trk.rec, "bb_meta", {}) or {})
    for _ in range(3):
        try:
            quotes = dict(trk.rec.quotes)
            break
        except RuntimeError:                            # the quote thread added a key mid-copy
            continue
    else:
        quotes = {}
    for sym, (ex, k, cp) in meta.items():
        if ex != exp:
            continue
        q = quotes.get(sym)
        if not q or not (q[0] == q[0]) or q[0] <= 0:
            continue
        side = "call" if cp > 0 else "put"
        if (side == "call" and spot < k <= spot * (1 + lim)) or (side == "put" and spot * (1 - lim) <= k < spot):
            rows.append(dict(run.price(side, k, q[0]), ask=q[1]))
    tbl = pd.DataFrame(rows).sort_values(["side", "strike"]) if rows else pd.DataFrame()
    e = trk.edges(exp, spot, float(trk.cfg["min_bid"])) or {}
    key = []
    for lab, side, k in (("Call edge", "call", (e.get("ce") or (None,))[0]),
                         ("Put edge", "put", (e.get("pe") or (None,))[0]),
                         ("Sold C", "call", float(trk.cfg.get("sold_call") or 0) or None),
                         ("Sold P", "put", float(trk.cfg.get("sold_put") or 0) or None)):
        if not k:
            continue
        b, a = trk.quote(exp, k, 1 if side == "call" else -1)
        key.append(dict(run.price(side, k, b if b == b else 0.0), row=lab, ask=a))
    safe = []
    for side in ("put", "call"):
        for sf in run.safest(side):
            b, a = trk.quote(exp, float(sf["strike"]), 1 if side == "call" else -1)
            safe.append(dict(run.price(side, sf["strike"], b if b == b else 0.0), row=sf["name"], ask=a,
                             move_pct=sf["move_pct"], date=sf["date"], has_bid=(b == b)))
    st.session_state["bb_model"] = dict(run=run, mode=mode, exp=exp, spot=spot, src=src, table=tbl, key=key, safe=safe,
                                        win={"put": run.display_window("put"), "call": run.display_window("call")})


def _fmt(v, kind):
    if v is None or not v == v:
        return "—"
    if kind == "pct":                                   # v = chance reached (0–1) for ONE session
        p = v * 100
        yr = v * 252
        ps = f"{p:.2f}%" if p >= 0.1 else f"{p:.3f}%" if p >= 0.001 else f"{p:.1e}%"
        ys = f"{yr:.1f}×/yr" if yr >= 1 else f"{yr:.2f}×/yr" if yr >= 0.01 else f"once in {1 / yr:,.0f} yrs" if yr > 0 else "never"
        return f"{ps} · {ys}"
    if kind == "c":
        return f"{v:,.2f}¢"
    if kind == "r":
        return f"{v:,.2f}"
    return f"{v}"


def _key_table(rows):
    if not rows:
        return
    h = ("<table style='border-collapse:collapse;font-family:monospace;font-size:1.02em'><tr>"
         + "".join(f"<td style='color:#8b949e;padding:2px 12px;text-align:right'>{c}</td>"
                   for c in ("", "strike", "history move", "bid", "chance reached (per session · per year)", "exp. loss", "ratio after fees",
                             "cautious ratio"))
         + "</tr>")
    for r in rows:
        col = BLUE if r["side"] == "call" else MAG
        ok = r.get("ratio") == r.get("ratio") and r.get("ratio", 0) >= 1
        mv = f"{r['move_pct']:+.2f}% · {r['date']}" if "move_pct" in r else ""
        name = f"{r['row']} {'P' if r['side'] == 'put' else 'C'}" if "move_pct" in r else r["row"]
        nob = not r.get("has_bid", True) or not r.get("bid")
        bid = "no bid" if nob else f"{r['bid']:.2f}"
        if nob:                                      # nothing to sell there → no ratio
            r = dict(r, ratio=float("nan"), cautious_ratio=float("nan"))
            ok = False
        h += (f"<tr><td style='color:{col};font-weight:700;padding:2px 12px'>{name}</td>"
              + _cell(f"{r['strike']:,.0f}", bold=True) + _cell(mv, fg="#8b949e") + _cell(bid)
              + _cell(_fmt(r.get("touch"), "pct")) + _cell(_fmt(r.get("el_c"), "c"))
              + _cell(_fmt(r.get("ratio"), "r"), GRN_BG if ok else RED_BG, bold=True)
              + _cell(_fmt(r.get("cautious_ratio"), "r")) + "</tr>")
    st.markdown(h + "</table>", unsafe_allow_html=True)


def _best(d, spot):
    """Strike with the highest ratio after fees among live bids in the far-OTM zone the chart shows (expected loss
    ≤ 50¢, the same cap as the chart); a tie goes to the strike further from spot."""
    x = d[d["ratio"].notna() & (d["bid"] > 0) & (d["el_c"] <= 50.0)]
    if x.empty:
        return None
    x = x.assign(_far=(x["strike"] - spot).abs()).sort_values(["ratio", "_far"], ascending=False)
    return x.iloc[0].to_dict()


def _side_box(side, m, best):
    col = BLUE if side == "call" else MAG
    rows = [dict(r, lab=r["row"]) for r in m.get("safe", []) if r["side"] == side]
    rows += [dict(r, lab=f"Furthest {side}") for r in m["key"] if r["side"] == side and r["row"].endswith("edge")]
    if best is not None:
        rows.append(dict(best, lab="<span style='color:#f5c542'>★</span> Best ratio"))
    h = ("<table style='border-collapse:collapse;font-family:monospace;font-size:0.98em;margin-bottom:4px'><tr>"
         + f"<td style='color:{col};font-weight:700;padding:2px 10px'>{side.upper()}S</td>"
         + "".join(f"<td style='color:#8b949e;padding:2px 10px;text-align:right'>{c}</td>"
                   for c in ("strike", "history move", "bid", "chance / yr", "ratio")) + "</tr>")
    for r in rows:
        nob = not r.get("has_bid", True) or not r.get("bid")
        ratio = float("nan") if nob else r.get("ratio")
        ok = ratio == ratio and ratio >= 1
        mv = f"{r['move_pct']:+.2f}% · {r['date']}" if "move_pct" in r else ""
        yr = _fmt(r.get("touch"), "pct").split(" · ")[-1] if r.get("touch") == r.get("touch") else "—"
        h += (f"<tr><td style='color:{col};font-weight:700;padding:2px 10px'>{r['lab']}</td>"
              + _cell(f"{r['strike']:,.0f}", bold=True) + _cell(mv, fg="#8b949e")
              + _cell("no bid" if nob else f"{r['bid']:.2f}") + _cell(yr)
              + _cell(_fmt(ratio, "r"), GRN_BG if ok else RED_BG, bold=True) + "</tr>")
    st.markdown(h + "</table>", unsafe_allow_html=True)


def _model_block(trk: BB.Tracker):
    st.markdown("**Edge model** — expected loss of far-OTM strikes (runs only when you press the button)")
    b1, b2 = st.columns([1, 6])
    if b1.button("▶ Run model", key="bb_run"):
        with st.spinner("running edge model (downloading SPX / VIX history from Yahoo, fitting)…"):
            try:
                _run_model(trk)
            except Exception as ex:                     # noqa: BLE001
                st.session_state["bb_model"] = {"error": f"{type(ex).__name__}: {str(ex)[:200]}"}
    m = st.session_state.get("bb_model")
    if not m:
        b2.caption("not run yet")
        return
    if m.get("error"):
        b2.error(f"model run failed — {m['error']}")
        return
    i = m["run"].info
    cur = st.session_state.get("bb_mode", trk.cfg["mode"])
    b2.caption(f"last run {i['run_at_et']} ET · **{i['toggle']}** · {dt.date.fromisoformat(m['exp']):%a %d %b} · "
               f"spot {i['spot']:,.2f} ({i['spot_source'] or '?'}) · VIX {i['vix']:.2f} ({i['vix_date']})")
    if cur != m["mode"]:
        st.warning(f"These results were run for **{m['mode']}** — the toggle is now on {cur}. "
                   "Press Run model to refresh.")
    st.caption(f"SAFEST = strike just beyond the biggest one-session move since 1990 on days with VIX ≤ "
               f"{i.get('vix_bucket', '?')}, measured from {i.get('safest_measured_from', float('nan')):,.2f} — "
               "has not happened in that history, not cannot happen")
    t = m["table"]
    if len(t):
        cl, cr = st.columns(2)
        for colw, side, colr in ((cl, "put", MAG), (cr, "call", BLUE)):
            d = t[t["side"] == side]
            if d.empty:
                continue
            best = _best(d, float(m["spot"]))
            with colw:
                _side_box(side, m, best)
            # y capped at 50¢ — the same view as the edge script. Blank bids are simply not drawn.
            keep = [r["strike"] for r in m.get("safe", []) if r["side"] == side]
            keep += [r["strike"] for r in m["key"] if r["side"] == side and r["row"].endswith("edge")]
            keep.append(float(d["strike"].min() if side == "put" else d["strike"].max()))   # furthest live bid
            # v0.31.1: spot → the furthest of (last live bid, edge, SAFEST, 2nd SAFEST) + 1 % of that strike
            sp_ = float(m["spot"])
            if side == "put":
                lo, hi = min(keep) * 0.99, sp_
            else:
                lo, hi = sp_, max(keep) * 1.01
            d = d[(d["strike"] >= lo) & (d["strike"] <= hi)]
            i_ = m["run"].info
            fit = (i_.get(f"{side}_fit") or {}).get("formula", "")
            f = _fig(f"FAR OTM {m['mode']} {side.upper()}S — market bid vs expected loss · SPX {i_['spot']:,.2f} · "
                     f"VIX {i_['vix']:.2f}<br><span style='font-size:11px;color:#8b949e'>typical move ~ {fit}</span>",
                     h=420)
            f.update_layout(margin=dict(l=8, r=8, t=58, b=8), showlegend=True,
                            legend=dict(orientation="h", y=-0.14, x=0, font=dict(size=11)))
            gx = np.linspace(lo, hi, 160)
            gq = [m["run"].price(side, k, 0.0) for k in gx]
            f.add_scatter(x=gx, y=[q["el_c"] for q in gq], mode="lines", line=dict(color="#f5c542", width=2, dash="dash"),
                          name="expected loss", hoverinfo="skip")
            f.add_scatter(x=gx, y=[q["cautious_c"] for q in gq], mode="lines",
                          line=dict(color="#ff8a65", width=1.3, dash="dot"), name="cautious (95 %)", hoverinfo="skip")
            if len(d):
                f.add_scatter(x=d["strike"], y=d["bid"] * 100, mode="markers", name="live bid",
                              marker=dict(size=8, color=colr, line=dict(color="#0e1117", width=1)),
                              customdata=np.stack([d["touch"] * 100, d["touch"] * 252, d["el_c"], d["ratio"]], -1),
                              hovertemplate="%{x:,.0f} · bid %{y:.0f}¢<br>reached %{customdata[0]:.3f}% · "
                                            "~%{customdata[1]:.2f}×/yr<br>exp loss %{customdata[2]:.2f}¢ · "
                                            "ratio %{customdata[3]:.2f}<extra></extra>")
            for n_, sf in enumerate([r for r in m.get("safe", []) if r["side"] == side]):
                k = sf["strike"]
                lc = "#2ecc71" if n_ == 0 else "#c77dff"
                f.add_vline(x=k, line=dict(color=lc, width=1.6, dash="dash"))
                outward = (n_ == 0) == (side == "call")      # SAFEST label on its outer side, 2nd on the inner side
                f.add_annotation(x=k, y=47, xanchor="left" if outward else "right", xshift=6 if outward else -6,
                                 yanchor="top", align="left" if outward else "right", text=f"<b>{sf['row']}</b><br>{k:,.0f}<br>"
                                 f"({sf['move_pct']:+.1f}% {sf['date']})<br>"
                                 + ("no bid" if not sf.get("has_bid", True) or not sf.get("bid")
                                    else f"bid {sf['bid']:.2f}"),
                                 showarrow=False, font=dict(color=lc, size=11), bgcolor="rgba(14,17,23,0.75)")
                if sf.get("has_bid", True) and sf.get("bid"):
                    f.add_scatter(x=[k], y=[sf["bid"] * 100], mode="markers", showlegend=False, hoverinfo="skip",
                                  marker=dict(symbol="triangle-down", size=15, color=lc, line=dict(color="#fff", width=1)))
            if best is not None:
                f.add_scatter(x=[best["strike"]], y=[best["bid"] * 100], mode="markers", name="best ratio",
                              marker=dict(symbol="star", size=16, color="#f5c542", line=dict(color="#0e1117", width=1)),
                              hovertemplate=f"BEST ratio {best['strike']:,.0f} · {best['ratio']:.2f}×<extra></extra>")
            f.add_vline(x=sp_, line=dict(color="#e6edf3", width=2))
            f.add_annotation(x=sp_, y=1, yref="paper", yanchor="top", showarrow=False, text=f"SPX {sp_:,.2f}",
                             xanchor="right" if side == "put" else "left", xshift=-4 if side == "put" else 4,
                             font=dict(color="#e6edf3", size=11), bgcolor="rgba(14,17,23,0.8)")
            f.update_xaxes(range=[lo, hi], title_text="strike")
            f.update_yaxes(range=[0, 50], title_text="¢ per share")
            colw.plotly_chart(f, width="stretch", key=f"bb_m_{side}")
        with st.expander(f"every strike with a bid, spot to {int(t['pct_from_spot'].abs().max() + 0.5)}% "
                         f"({len(t)} strikes, {m['mode']})"):
            show = t.assign(chance=t["touch"].map(lambda v: _fmt(v, "pct")))[
                ["side", "strike", "pct_from_spot", "bid", "ask", "chance", "el_c", "cautious_c", "net_c", "ratio",
                 "cautious_ratio"]]
            st.dataframe(show.round(3), hide_index=True, width="stretch")
    st.caption(MODEL_NOTE)
    st.divider()


def render(trk: BB.Tracker):
    _model_block(trk)
    exps = trk.expiries()
    if not exps:
        st.info("SPX BB: waiting for the recorder's expiries…")
        return
    labels = {lab: f"{lab} · {dt.date.fromisoformat(d):%a %d %b}" + (" (EXPIRED)" if x else "") for lab, d, x in exps}
    c0, c2, c4 = st.columns([3, 1.2, 1.6])
    mode = trk.cfg["mode"] if trk.cfg["mode"] in labels else "0DTE"
    pick = c0.radio("Expiry (view)", list(labels), index=list(labels).index(mode), horizontal=True,
                    format_func=lambda k: labels[k], key="bb_mode")
    mb = c2.number_input("Min bid", 0.05, 1.00, float(trk.cfg["min_bid"]), 0.05, format="%.2f", key="bb_mb")
    if c4.button("📨 test Telegram", key="bb_test", disabled=not trk.tg_ok):
        trk.send(f"✅ TRISHULA SPX BB test · {now_et():%a %H:%M:%S} ET")
    c4.caption("Telegram: " + ("not configured (TG_BOT_TOKEN / TG_CHAT_ID in secrets)" if not trk.tg_ok
                               else (trk.status.get("tg") or "ready")))
    a0, t0, a1, t1, note = st.columns([1.3, 1.1, 1.3, 1.1, 3])
    _ti = lambda v: BB.THRESHOLDS.index(int(v)) if int(v) in BB.THRESHOLDS else 1
    al0 = a0.toggle("Alert 0DTE", bool(trk.cfg["alert0"]), key="bb_al0", disabled=not trk.tg_ok)
    th0 = t0.selectbox("0DTE jump (pts)", BB.THRESHOLDS, index=_ti(trk.cfg["thr0"]), key="bb_th0")
    al1 = a1.toggle("Alert 1DTE", bool(trk.cfg["alert1"]), key="bb_al1", disabled=not trk.tg_ok)
    th1 = t1.selectbox("1DTE jump (pts)", BB.THRESHOLDS, index=_ti(trk.cfg["thr1"]), key="bb_th1")
    note.caption("Alerts fire whatever the view shows: 0DTE always · 1DTE only 15:00–21:00 ET. "
                 "Each expiry keeps its own edge level (no repeats).")
    trk.set(mode=pick, min_bid=round(float(mb), 2), alert0=bool(al0), thr0=int(th0), alert1=bool(al1), thr1=int(th1))
    _live(trk)


@st.fragment(run_every=5)                                 # v0.33.0: was 15
def _live(trk: BB.Tracker):
    mode = trk.cfg["mode"]
    exp, expired = trk.exp_for(mode)
    if exp is None:
        st.info("no expiry for this toggle yet")
        return
    df = trk.frame(exp)
    rec = trk.rec
    spot, src = rec.spot_now()
    if expired and len(df):
        spot, src = float(df["spot"].iloc[-1]), "frozen"
    if expired:
        cur = df.iloc[-1] if len(df) else None
    else:
        e = trk.edges(exp, spot, float(trk.cfg["min_bid"])) if spot == spot else None
        cur = None
        if e and (e["ce"] or e["pe"]):
            ce, pe = e["ce"] or (np.nan,) * 3, e["pe"] or (np.nan,) * 3
            cur = pd.Series(dict(spot=spot, ce=ce[0], ce_bid=ce[1], ce_ask=ce[2], pe=pe[0], pe_bid=pe[1], pe_ask=pe[2]))
    dlab = f"{mode} · {dt.date.fromisoformat(exp):%a %d %b %Y}" + (" · EXPIRED 16:00 — last edges frozen" if expired else "")
    st.markdown(f"**SPX BB — {dlab}** · checked every {BB.CHECK_S}s"
                + (f" · last {trk.status['last']}" if trk.status.get("last") else "")
                + (f" · ⚠ {trk.status['error']}" if trk.status.get("error") else ""))
    if cur is None:
        st.info("waiting for quotes on this expiry… (the full strike set subscribes when the recorder starts)")
        return
    sp = float(cur["spot"])
    ce, pe = float(cur["ce"]), float(cur["pe"])
    cd, pdist = ce - sp, sp - pe
    left, mid, right = st.columns([5, 3.2, 5])

    # ── middle panel: C / P / R / W + spot + your sold strikes ─────────────────────────
    with mid:
        r_ = pdist / cd if cd > 0 else np.nan
        tbl = ("<table style='border-collapse:collapse;font-family:monospace;font-size:1.05em'>"
               "<tr><td></td><td style='color:#8b949e;padding:0 10px;text-align:right'>dist</td>"
               "<td style='color:#8b949e;padding:0 10px;text-align:right'>edge</td>"
               "<td style='color:#8b949e;padding:0 10px;text-align:right'>% spot</td>"
               "<td style='color:#8b949e;padding:0 10px;text-align:right'>bid / ask</td></tr>"
               f"<tr><td style='color:{BLUE};font-weight:700'>C</td>{_cell(f'{cd:,.0f}')}{_cell(f'{ce:,.0f}', bold=True)}"
               f"{_cell(f'{cd / sp:.2%}', '#0d2a5a')}{_cell(f'{cur.ce_bid:.2f} / {cur.ce_ask:.2f}', fg='#8b949e')}</tr>"
               f"<tr><td style='color:{MAG};font-weight:700'>P</td>{_cell(f'{pdist:,.0f}')}{_cell(f'{pe:,.0f}', bold=True)}"
               f"{_cell(f'{pdist / sp:.2%}', '#3d0f45')}{_cell(f'{cur.pe_bid:.2f} / {cur.pe_ask:.2f}', fg='#8b949e')}</tr>"
               f"<tr><td style='font-weight:700'>R</td>{_cell(f'{r_:.2f}', bold=True)}{_cell(f'{ce - pe:,.0f}', bold=True)}"
               f"<td style='color:#8b949e;padding:0 10px'>W</td><td></td></tr></table>")
        st.markdown(tbl, unsafe_allow_html=True)
        st.caption("R = put dist ÷ call dist · W = call edge − put edge")
        st.markdown(f"<div style='margin:10px 0;padding:8px;border:2px solid #f5c542;border-radius:6px;"
                    f"text-align:center;font-size:1.6em;font-weight:700;color:#f5c542'>{sp:,.2f}"
                    f"<span style='font-size:0.45em;color:#8b949e'> {'' if src == 'spx' else src}</span></div>",
                    unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        sc = s1.number_input("sold C", 0.0, 20000.0, float(trk.cfg.get("sold_call") or 0.0), 5.0, format="%.0f",
                             key="bb_sc", help="0 = none")
        sput = s2.number_input("sold P", 0.0, 20000.0, float(trk.cfg.get("sold_put") or 0.0), 5.0, format="%.0f",
                               key="bb_sp", help="0 = none")
        aa = st.number_input("Telegram when a sold strike's ASK reaches (09:30–16:00 ET)", 0.05, 50.0,
                             float(trk.cfg.get("ask_alert") or 0.50), 0.05, format="%.2f", key="bb_aa")
        trk.set(sold_call=float(sc), sold_put=float(sput), ask_alert=round(float(aa), 2))
        rows = ""
        for side, k, edge, cp, col in (("C", sc, ce, 1, BLUE), ("P", sput, pe, -1, MAG)):
            if not k:
                rows += (f"<tr><td style='color:{col};font-weight:700'>{side}</td>"
                         + _cell("—", fg="#8b949e") * 3 + "</tr>")
                continue
            buf = (k - edge) if cp > 0 else (edge - k)
            ok = buf > 0
            _, ask = (np.nan, np.nan) if expired else trk.quote(exp, k, cp)
            dpc = (k - sp) / sp if cp > 0 else (sp - k) / sp
            bg = GRN_BG if ok else RED_BG
            rows += (f"<tr><td style='color:{col};font-weight:700'>{side} {k:,.0f}</td>"
                     + _cell(f"{buf:+,.0f}", bg, "#7ee2a8" if ok else "#ff8a9a", True)
                     + _cell("—" if not ask == ask else f"{ask:.2f}", bg)
                     + _cell(f"{dpc:.2%}", "#0d2a5a" if cp > 0 else "#3d0f45") + "</tr>")
        st.markdown("<table style='border-collapse:collapse;font-family:monospace;margin-top:4px'>"
                    "<tr><td></td><td style='color:#8b949e;padding:0 10px;text-align:right'>buffer</td>"
                    "<td style='color:#8b949e;padding:0 10px;text-align:right'>ask</td>"
                    "<td style='color:#8b949e;padding:0 10px;text-align:right'>dist from spot</td></tr>"
                    + rows + "</table>", unsafe_allow_html=True)
        st.caption("buffer = how far your strike sits beyond the last 0.05 bid · green = outside the liquidity, "
                   "red = the edge has reached / passed it")

    if df.empty:
        left.info(f"chart fills as the tracker samples (every {BB.CHECK_S} s)")
        return
    # v0.33.0: build the two charts only when their data changed — otherwise re-send the identical figures
    sig = (exp, len(df), tuple(df.iloc[-1].astype(str)), len(trk.alerts), sc, sput)
    cache = st.session_state.get("_bb_figs")
    if cache and cache[0] == sig:
        with left:
            st.plotly_chart(cache[1], width="stretch", key="bb_w")
        with right:
            st.plotly_chart(cache[2], width="stretch", key="bb_e")
        return
    d = df.dropna(subset=["ce", "pe"])
    t = d["t"]
    # ── left: 0.05-bid width ────────────────────────────────────────────────────────
    with left:
        f = _fig("0.05-bid width (pts) — call edge − put edge")
        f.add_scatter(x=t, y=d["ce"] - d["pe"], mode="lines", line=dict(color="#ab47bc", width=2), name="width")
        st.plotly_chart(f, width="stretch", key="bb_w")
        fw = f
    # ── right: furthest 0.05-bid strikes, bands spot → edge ────────────────────────
    with right:
        f = _fig("Furthest 0.05-bid strikes — call (blue) vs put (magenta)")
        f.add_scatter(x=t, y=d["spot"], mode="lines", line=dict(width=0), hoverinfo="skip")
        f.add_scatter(x=t, y=d["ce"], mode="lines", line=dict(color=BLUE, width=2, shape="hv"),
                      fill="tonexty", fillcolor="rgba(47,139,255,0.18)", name="call edge")
        f.add_scatter(x=t, y=d["spot"], mode="lines", line=dict(width=0), hoverinfo="skip")
        f.add_scatter(x=t, y=d["pe"], mode="lines", line=dict(color=MAG, width=2, shape="hv"),
                      fill="tonexty", fillcolor="rgba(224,64,251,0.18)", name="put edge")
        f.add_scatter(x=t, y=d["spot"], mode="lines", line=dict(color="#e6edf3", width=1.3), name="SPX")
        al = [a for a in trk.alerts if a[1] == exp]
        if al:
            f.add_scatter(x=pd.to_datetime([a[0] for a in al]), y=[a[3] for a in al], mode="markers",
                          marker=dict(size=9, color=["#2f8bff" if a[2] == "call" else "#e040fb" for a in al],
                                      line=dict(color="#fff", width=1)), name="alert")
        if sc:
            f.add_hline(y=sc, line=dict(color=BLUE, dash="dot", width=1), annotation_text=f"sold {sc:,.0f}C")
        if sput:
            f.add_hline(y=sput, line=dict(color=MAG, dash="dot", width=1), annotation_text=f"sold {sput:,.0f}P")
        st.plotly_chart(f, width="stretch", key="bb_e")
    st.session_state["_bb_figs"] = (sig, fw, f)
