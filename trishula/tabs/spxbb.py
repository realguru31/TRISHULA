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
    st.session_state["bb_model"] = dict(run=run, mode=mode, exp=exp, spot=spot, src=src, table=tbl, key=key,
                                        win={"put": run.display_window("put"), "call": run.display_window("call")})


def _fmt(v, kind):
    if v is None or not v == v:
        return "—"
    if kind == "one_in":
        return "1 in ∞" if v == float("inf") else f"1 in {v:,.0f}" if v >= 10 else f"1 in {v:,.1f}"
    if kind == "c":
        return f"{v:,.2f}¢"
    if kind == "r":
        return f"{v:,.2f}"
    return f"{v}"


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
    if m["key"]:
        h = ("<table style='border-collapse:collapse;font-family:monospace'><tr>"
             + "".join(f"<td style='color:#8b949e;padding:0 10px;text-align:right'>{c}</td>"
                       for c in ("", "strike", "bid", "chance reached", "exp. loss", "ratio after fees", "cautious ratio"))
             + "</tr>")
        for r in m["key"]:
            col = BLUE if r["side"] == "call" else MAG
            ok = r.get("ratio") == r.get("ratio") and r.get("ratio", 0) >= 1
            h += (f"<tr><td style='color:{col};font-weight:700;padding:0 10px'>{r['row']}</td>"
                  + _cell(f"{r['strike']:,.0f}", bold=True) + _cell(f"{r['bid']:.2f}")
                  + _cell(_fmt(r.get("one_in"), "one_in")) + _cell(_fmt(r.get("el_c"), "c"))
                  + _cell(_fmt(r.get("ratio"), "r"), GRN_BG if ok else RED_BG)
                  + _cell(_fmt(r.get("cautious_ratio"), "r")) + "</tr>")
        st.markdown(h + "</table>", unsafe_allow_html=True)
    t = m["table"]
    if len(t):
        cl, cr = st.columns(2)
        for colw, side, colr in ((cl, "put", MAG), (cr, "call", BLUE)):
            d = t[t["side"] == side]
            if d.empty:
                continue
            lo, hi = m["win"][side]
            f = _fig(f"{side}s — expected loss vs bid (¢ per share) · {m['mode']}", h=300)
            f.add_bar(x=d["strike"], y=d["bid"] * 100, marker_color=colr, opacity=0.45, name="bid ¢")
            f.add_scatter(x=d["strike"], y=d["el_c"], mode="lines+markers", line=dict(color="#f5c542", width=2),
                          name="exp. loss ¢")
            f.add_scatter(x=d["strike"], y=d["cautious_c"], mode="lines", line=dict(color="#ff8a65", width=1, dash="dot"),
                          name="cautious ¢")
            f.update_xaxes(range=[lo, hi])
            f.update_yaxes(rangemode="tozero")
            colw.plotly_chart(f, width="stretch", key=f"bb_m_{side}")
        with st.expander(f"every strike with a bid, spot to {int(t['pct_from_spot'].abs().max() + 0.5)}% "
                         f"({len(t)} strikes, {m['mode']})"):
            show = t.assign(chance=t["one_in"].map(lambda v: _fmt(v, "one_in")))[
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
    c0, c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1.2, 1.6])
    mode = trk.cfg["mode"] if trk.cfg["mode"] in labels else "0DTE"
    pick = c0.radio("Expiry", list(labels), index=list(labels).index(mode), horizontal=True,
                    format_func=lambda k: labels[k], key="bb_mode")
    thr = c1.selectbox("Alert threshold (pts)", BB.THRESHOLDS, index=BB.THRESHOLDS.index(int(trk.cfg["threshold"]))
                       if int(trk.cfg["threshold"]) in BB.THRESHOLDS else 1, key="bb_thr")
    mb = c2.number_input("Min bid", 0.05, 1.00, float(trk.cfg["min_bid"]), 0.05, format="%.2f", key="bb_mb")
    al = c3.toggle("Telegram alerts", bool(trk.cfg["alerts"]), key="bb_al", disabled=not trk.tg_ok)
    if c4.button("📨 test Telegram", key="bb_test", disabled=not trk.tg_ok):
        trk.send(f"✅ TRISHULA SPX BB test · {now_et():%a %H:%M:%S} ET")
    trk.set(mode=pick, threshold=int(thr), min_bid=round(float(mb), 2), alerts=bool(al))
    c4.caption("Telegram: " + ("not configured (TG_BOT_TOKEN / TG_CHAT_ID in secrets)" if not trk.tg_ok
                               else (trk.status.get("tg") or "ready")))
    _live(trk)


@st.fragment(run_every=15)
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
        trk.set(sold_call=float(sc), sold_put=float(sput))
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
        left.info("chart fills as the tracker samples (every 15 s)")
        return
    d = df.dropna(subset=["ce", "pe"])
    t = d["t"]
    # ── left: 0.05-bid width ────────────────────────────────────────────────────────
    with left:
        f = _fig("0.05-bid width (pts) — call edge − put edge")
        f.add_scatter(x=t, y=d["ce"] - d["pe"], mode="lines", line=dict(color="#ab47bc", width=2), name="width")
        st.plotly_chart(f, width="stretch", key="bb_w")
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
