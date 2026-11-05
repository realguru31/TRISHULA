"""v0.24.0 — VS3D ▸ Lean: SPX candles painted by the 0DTE / 1DTE options-flow lean (single-leg or all prints).
Every setting is a toggle; the stored minutes are raw, so any setting can be replayed on any saved day."""
from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import lean as LN
from core import state as ST

BG = "#0e1117"
COL = {1: "#2f8cff", -1: "#ff2dc4", 0: "#5a5d6e"}
LIVE = "today (live)"
_K = "ln_"


def _preset_apply():
    p = st.session_state.get(_K + "preset")
    if p in LN.LOCKED:
        r = LN.LOCKED[p]
        st.session_state.update({_K + "bar": r["bar"], _K + "flow": r["flow"],
                                 _K + "src": {"roll": "rolling window", "open": "since open", "bar": "per bar"}[r["src"]],
                                 _K + "win": int(r["win"]) if r["src"] == "roll" else st.session_state.get(_K + "win", 15),
                                 _K + "mode": r["mode"], _K + "X": float(r["X"]), _K + "conf": bool(r["conf"]),
                                 _K + "cool": int(r["cool"]), _K + "skip": bool(r["skip"]), _K + "hold": bool(r["hold"])})


def _defaults():
    if _K + "init" in st.session_state:
        return
    st.session_state[_K + "init"] = True
    st.session_state[_K + "preset"] = "A"
    st.session_state[_K + "kind"] = "single-leg"
    _preset_apply()


def _controls(days):
    _defaults()
    c = st.columns([1.3, 1.1, 0.8, 1.0, 1.1])
    c[0].selectbox("day", [LIVE] + days, key=_K + "day")
    c[1].selectbox("preset (locked test rules)", ["A", "B", "C", "D", "custom"], key=_K + "preset", on_change=_preset_apply,
                   help="A your 4 Nov screen · B best on history · C 5-min band · D per bar — see the locked test below")
    c[2].selectbox("bars", [1, 5], key=_K + "bar", format_func=lambda x: f"{x} min")
    c[3].selectbox("flow", ["0DTE", "0+1DTE"], key=_K + "flow")
    c[4].selectbox("prints", ["single-leg", "all"], key=_K + "kind", help="single-leg = spread / complex legs removed")
    c = st.columns([1.2, 0.8, 1.0, 1.6])
    c[0].selectbox("lean", ["rolling window", "since open", "per bar"], key=_K + "src")
    c[1].number_input("window (min)", 1, 120, step=1, key=_K + "win")
    c[2].selectbox("mode", ["sticky", "band"], key=_K + "mode",
                   help="band: blue ≥ +X, magenta ≤ −X, grey between · sticky: holds the colour until the other side is crossed")
    c[3].slider("X = |lean| threshold", 0.0, 0.30, step=0.005, key=_K + "X", format="%.3f")
    c = st.columns([1.2, 1.4, 1.0, 1.2])
    c[0].checkbox("2-bar break confirm", key=_K + "conf", help="a colour shows only on a close beyond the prior 2 bars' high / low")
    c[1].slider("cooldown (grey bars before the opposite colour)", 0, 10, key=_K + "cool")
    c[2].checkbox("skip first 10 min", key=_K + "skip")
    c[3].checkbox("grey holds the trade", key=_K + "hold", help="off = grey closes the trade (flat)")
    s = st.session_state
    src = {"rolling window": "roll", "since open": "open", "per bar": "bar"}[s[_K + "src"]]
    rule = dict(bar=int(s[_K + "bar"]), flow=s[_K + "flow"], src=src, win=int(s[_K + "win"]), mode=s[_K + "mode"],
                X=float(s[_K + "X"]), conf=bool(s[_K + "conf"]), cool=int(s[_K + "cool"]), skip=10 if s[_K + "skip"] else 0,
                hold=bool(s[_K + "hold"]))
    match = [k for k, r in LN.LOCKED.items()
             if all(rule[f] == v for f, v in r.items() if f != "win" or r["src"] == "roll") and s[_K + "kind"] == "single-leg"]
    st.caption(f"settings = locked rule {match[0]}" if match else "custom settings (not one of the locked rules A–D)")
    return rule, s[_K + "kind"], s[_K + "day"]


def _figure(b, col, lean, rule, tr):
    x = [t.strftime("%H:%M") for t in b.index]
    f = go.Figure()
    for k in (1, -1, 0):
        idx = np.where(col == k)[0]
        f.add_trace(go.Candlestick(x=[x[i] for i in idx], open=b.o.values[idx], high=b.h.values[idx], low=b.l.values[idx],
                                   close=b.c.values[idx], increasing=dict(line=dict(color=COL[k], width=1), fillcolor=COL[k]),
                                   decreasing=dict(line=dict(color=COL[k], width=1), fillcolor=COL[k]),
                                   showlegend=False, hoverinfo="x+y", yaxis="y"))
    if len(tr):
        pos = {t: i for i, t in enumerate(b.index)}
        for side, sym, colr in (("LONG", "triangle-up", COL[1]), ("SHORT", "triangle-down", COL[-1])):
            e = tr[tr.side == side]
            f.add_trace(go.Scatter(x=[x[pos[t]] for t in e.entry], y=[b.l.values[pos[t]] - 2 if side == "LONG" else b.h.values[pos[t]] + 2 for t in e.entry],
                                   mode="markers", marker=dict(symbol=sym, size=11, color=colr, line=dict(color="white", width=1)),
                                   hovertext=[f"{side} {p:.2f}" for p in e.px_in], hoverinfo="text", showlegend=False, yaxis="y"))
    net = (b.b - b.r).values
    f.add_trace(go.Bar(x=x, y=net, marker_color=[COL[k] for k in col], yaxis="y2", showlegend=False,
                       hovertemplate="net Δ$ %{y:.1f}M<extra></extra>"))
    f.add_trace(go.Scatter(x=x, y=100 * lean, mode="lines", line=dict(color="#ffd600", width=2), yaxis="y3", showlegend=False,
                           hovertemplate="lean %{y:.1f}%<extra></extra>"))
    for v, c_ in ((rule["X"], COL[1]), (-rule["X"], COL[-1])):
        f.add_trace(go.Scatter(x=[x[0], x[-1]], y=[100 * v] * 2, mode="lines", line=dict(color=c_, width=1, dash="dot"),
                               yaxis="y3", hoverinfo="skip", showlegend=False))
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=760, margin=dict(t=10, l=60, r=20, b=30),
                    xaxis=dict(type="category", categoryorder="array", categoryarray=x, rangeslider=dict(visible=False), nticks=26),
                    yaxis=dict(domain=[0.40, 1], title="SPX"), yaxis2=dict(domain=[0.18, 0.36], title="net Δ$ M"),
                    yaxis3=dict(domain=[0, 0.15], title="lean %"), hovermode="x")
    return f


def _history_zip(days) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("settings.json", json.dumps({"locked": LN.LOCKED, "saved": _saved_settings()}, indent=1))
        for d in days:
            j = LN.load_day(d)
            if j:
                z.writestr(f"lean_{d}.json", json.dumps(j))
    return buf.getvalue()


def _saved_settings() -> list[dict]:
    try:
        return ST.read_file("state/lean_settings.json") or []
    except Exception:                                    # noqa: BLE001
        return []


def _settings_box(rule, kind):
    """⭐ settings we thought were good — kept on the state branch, go into the history zip."""
    with st.expander("⭐ saved settings (kept with the data, in the history zip)"):
        ss = st.session_state.get("ln_saved")
        if ss is None:
            ss = st.session_state["ln_saved"] = _saved_settings()
        c1, c2 = st.columns([3, 1])
        note = c1.text_input("note", key="ln_note", placeholder="why this one, e.g. 'clean trend day 5 Nov'")
        if c2.button("⭐ save current settings", key="ln_save", disabled=not ST.status.get("configured")):
            from core.timeutil import now_et
            ss = ss + [dict(rule, prints=kind, note=note, saved=now_et().strftime("%Y-%m-%d %H:%M ET"))]
            try:
                ST.save_file("state/lean_settings.json", ss, f"lean settings +1 ({len(ss)})", wait=True)
                st.session_state["ln_saved"] = ss
                st.success("saved")
            except Exception as e:                       # noqa: BLE001
                st.error(f"save failed: {type(e).__name__}: {e}")
        locked = [dict(r, prints="single-leg", note=f"locked rule {k} (pre-registered 5 Nov)", saved="2026-11-05") for k, r in LN.LOCKED.items()]
        st.dataframe(pd.DataFrame(locked + ss), hide_index=True, width="stretch")


def render(rec):
    rec = getattr(rec, "_rec", rec)                      # always live (replay player does not apply here)
    st.caption("Lean candles — each SPX candle painted by the options-flow lean: blue bullish · magenta bearish · grey noise. "
               "Flow = delta $ of calls bought / puts sold (bull) vs puts bought / calls sold (bear), from the recorded "
               "prints (100 % of the day). Research: RESEARCH_LOG §10–12 — on all-prints history NO setting beat chance; "
               "this tab collects single-leg days for the locked test below. ▲▼ = executed at every colour change.")
    configured = ST.status.get("configured")
    try:
        days = LN.saved_days() if configured else []
    except Exception as e:                               # noqa: BLE001
        days = []
        st.caption(f"saved days unavailable: {type(e).__name__}: {e}")
    rule, kind, day = _controls(days)
    if day == LIVE:
        d = LN.live_day(rec)
    else:
        d = LN.load_day(day)
    if not d:
        st.info("no data yet (waiting for the chain / prints)")
        return
    b = LN.bars(d, rule["flow"], kind, rule["bar"])
    if len(b) < 3:
        st.info("waiting for RTH bars (09:30 ET)")
        return
    col, lean = LN.colours(b, **rule)
    tr = LN.trades(b, col, rule["hold"])
    st.plotly_chart(_figure(b, col, lean, rule, tr), width="stretch", key="lean_fig")
    tot = (b.b + b.r).sum()
    rw = pd.DataFrame(d.get("rows") or [], columns=["m", "g", "sl_b", "sl_r", "al_b", "al_r"])
    sl_share = (rw.sl_b + rw.sl_r).sum() / max((rw.al_b + rw.al_r).sum(), 1e-9) if len(rw) else float("nan")
    n = len(tr)
    st.markdown(f"{d['day']} · {n} trades · {tr.pts.sum() if n else 0:+.1f} pts gross · "
                f"**{tr.net.sum() if n else 0:+.1f} pts net** (0.5 pt / round trip) · win {100 * (tr.pts > 0).mean() if n else 0:.0f}% · "
                f"blue {int((col == 1).sum())} · magenta {int((col == -1).sum())} · grey {int((col == 0).sum())}")
    st.caption(f"flow in view {tot:,.0f} $M Δ · single-leg = {100 * sl_share:.0f}% of all-prints flow · "
               + (f"saved to trishula-state {LN._save['last']} ET" if LN._save.get("last") else "not saved yet this session")
               + (f" · ⚠ save error {LN._save['err']}" if LN._save.get("err") else "")
               + ("" if configured else " · ⚠ GITHUB_STATE_TOKEN missing — days are NOT being saved"))
    _settings_box(rule, kind)
    if n:
        show = tr.assign(entry=tr.entry.dt.strftime("%H:%M"), exit=tr.exit.dt.strftime("%H:%M")).round(2)
        st.dataframe(show, hide_index=True, width="stretch", height=min(36 * (n + 1), 320))
    with st.expander(f"🧪 Locked test A–D on saved single-leg days ({len(days)} saved)"):
        st.caption("Pre-registered 5 Nov 2026 before any single-leg day existed. PASS = ≥ 15 days, total > 0, both halves "
                   "> 0, above the 95th percentile of 200 time-shifted-flow runs, and better than the same rule on all prints.")
        for k, r in LN.LOCKED.items():
            how = "per bar" if r["src"] == "bar" else "rolling %dm" % r["win"]
            brk = "2-bar break · " if r["conf"] else ""
            st.caption(f"{k}: {r['bar']}-min · {r['flow']} · {how} · {r['mode']} {r['X']:.0%} · {brk}cooldown {r['cool']}")
        c1, c2 = st.columns(2)
        if c1.button("run the locked test", key="ln_test", disabled=not days):
            with st.spinner("running A–D + 200 null runs each…"):
                ds = [x for x in (LN.load_day(dd) for dd in sorted(days)) if x]
                st.session_state["ln_test_res"] = LN.locked_test(ds)
        if st.session_state.get("ln_test_res") is not None:
            st.dataframe(st.session_state["ln_test_res"], hide_index=True, width="stretch")
        if c2.button("📦 prepare lean history", key="ln_hist", disabled=not days):
            st.session_state["ln_hist_zip"] = _history_zip(days)
        if st.session_state.get("ln_hist_zip"):
            c2.download_button(f"⬇ lean history ({len(st.session_state['ln_hist_zip']) / 1e3:.0f} KB)",
                               st.session_state["ln_hist_zip"], file_name="trishula_lean_history.zip", key="ln_hist_dl")
