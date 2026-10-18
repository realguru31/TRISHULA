"""TASTIER — dealer-gamma dashboard (8 panels, reference screenshot layout).

Every panel is always drawn; when its data is not there yet the frame shows
why. Expiry and strike window come from the common control bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.gex import add_exposures, by_strike, gamma_flip, walls, window
from core.timeutil import ET

BG = "#000000"
GRID = "#1c2128"
GREEN, RED, BLUE, PURPLE = "#2ecc71", "#e74c3c", "#58a6ff", "#b388ff"
H_TOP, H_BOT = 420, 460


def _style(fig, title, h):
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h,
                      margin=dict(l=8, r=8, t=34, b=8), showlegend=False,
                      title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def _empty(title, msg, h):
    f = go.Figure()
    f.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                     font=dict(color="#6e7681", size=12))
    f.update_xaxes(visible=False)
    f.update_yaxes(visible=False)
    return _style(f, title, h)


def _t(ms):
    return pd.to_datetime(ms, unit="ms", utc=True).dt.tz_convert(ET)


def _history(rec, exp):
    """Chain snapshots for exp, plus the live chain as the newest column."""
    h = rec.chain_df()
    live = rec.live_chain(exp)
    if len(h):
        h = h[h["exp"] == exp]
    h = pd.concat([h, live], ignore_index=True) if len(live) else h
    return h.dropna(subset=["spot"]) if len(h) else h


def _levels(fig, spot, flip, row=None, col=None):
    kw = dict(row=row, col=col) if row else {}
    fig.add_hline(y=spot, line_dash="dash", line_color="white", line_width=1,
                  annotation_text=f"spot {spot:,.2f}", annotation_font_color="white",
                  annotation_font_size=10, **kw)
    if flip:
        fig.add_hline(y=flip, line_dash="dash", line_color=PURPLE, line_width=1,
                      annotation_text=f"flip {flip:,.1f}", annotation_font_color=PURPLE,
                      annotation_font_size=10, annotation_position="bottom right", **kw)


def render(rec, ctl):
    @st.fragment(run_every=30)
    def _tab():
        _draw(rec, ctl)

    _tab()


def _draw(rec, ctl):
    exp = ctl["exp"]
    spot, ssrc = rec.spot_now()
    ch = rec.live_chain(exp) if exp else pd.DataFrame()
    have = exp and len(ch) and ch["gamma"].notna().any() and spot == spot
    g = by_strike(ch.dropna(subset=["gamma"]), spot) if have else pd.DataFrame()
    flip = gamma_flip(g, spot) if have else None
    cw, pw = walls(g, spot) if have else (None, None)
    gv = window(g, spot, ctl["mode"], ctl["n"], ctl["pct"]) if have else g

    # ── header strip ──────────────────────────────────────────────────
    prints = rec.prints_df()
    if len(prints) and prints["delta"].isna().any():       # replayed seed prints: current delta stand-in
        dm = {k: v[1] for k, v in list(rec.greeks.items())}
        prints = prints.assign(delta=prints["delta"].fillna(prints["sym"].map(dm)))
    cvd = float((prints["aggr"] * prints["size"] * prints["delta"].fillna(0) * 100).sum()) if len(prints) else None
    m = st.columns(7)
    m[0].metric(f"SPX · {ssrc}", f"{spot:,.2f}" if spot == spot else "—")
    m[1].metric("Total net GEX", f"${g['net'].sum()/1e9:,.2f}B" if have else "—")
    m[2].metric("Regime", ("Positive γ" if g["net"].sum() > 0 else "Negative γ") if have else "—")
    m[3].metric("Gamma flip", f"{flip:,.1f}" if flip else "—")
    m[4].metric("Call wall", f"{cw:,.0f}" if cw else "—")
    m[5].metric("Put wall", f"{pw:,.0f}" if pw else "—")
    m[6].metric("CVD (Δ)", f"{cvd/1e3:+,.0f}K" if cvd is not None else "—")

    # ── row 1 ─────────────────────────────────────────────────────────
    r1 = st.columns([1.35, 1, 1, 1.35])
    with r1[0]:
        st.plotly_chart(_price_panel(rec, prints), width="stretch", key="p_price")
    with r1[1]:
        if have and len(gv):
            f = go.Figure()
            f.add_bar(y=gv["strike"], x=gv["call"] / 1e9, orientation="h", marker_color=GREEN)
            f.add_bar(y=gv["strike"], x=gv["put"] / 1e9, orientation="h", marker_color=RED)
            f.update_layout(barmode="relative", xaxis_title="$B / 1%")
            _levels(f, spot, flip)
            f.update_yaxes(range=[gv["strike"].min() - 5, gv["strike"].max() + 5])
            st.plotly_chart(_style(f, "GEX by strike · POS calls / NEG puts", H_TOP), width="stretch", key="p_gex")
        else:
            st.plotly_chart(_empty("GEX by strike", "waiting for greeks / OI", H_TOP), width="stretch", key="p_gex")
    with r1[2]:
        if have and len(gv):
            cum = g.set_index("strike")["net"].cumsum().reindex(gv["strike"]) / 1e9
            f = go.Figure()
            f.add_bar(y=cum.index, x=cum.values, orientation="h", marker_color=GREEN, opacity=0.5)
            f.add_scatter(y=cum.index, x=cum.values, mode="lines", line=dict(color=BLUE, width=2))
            f.update_layout(xaxis_title="$B cumulative")
            _levels(f, spot, flip)
            f.update_yaxes(range=[gv["strike"].min() - 5, gv["strike"].max() + 5])
            st.plotly_chart(_style(f, "Cumulative net gamma", H_TOP), width="stretch", key="p_cum")
        else:
            st.plotly_chart(_empty("Cumulative net gamma", "waiting for greeks / OI", H_TOP), width="stretch", key="p_cum")
    with r1[3]:
        hist = _history(rec, exp) if exp else pd.DataFrame()
        st.plotly_chart(_regime_panel(hist), width="stretch", key="p_regime")
        st.plotly_chart(_imbalance_panel(prints, rec.spot_df()), width="stretch", key="p_imb")

    # ── row 2 ─────────────────────────────────────────────────────────
    r2 = st.columns([1, 1.5, 1.5])
    surf = _surface(hist, spot, ctl) if len(hist) else None
    with r2[0]:
        st.plotly_chart(_flow_panel(surf), width="stretch", key="p_flow")
    with r2[1]:
        st.plotly_chart(_heat(surf, "gex", "Gamma surface · net GEX by strike × time",
                              [[0, "#08306b"], [0.5, "#000000"], [1, "#b2182b"]]), width="stretch", key="p_gsurf")
    with r2[2]:
        st.plotly_chart(_heat(surf, "charm", "Charm surface · net charm by strike × time",
                              [[0, "#d98c00"], [0.5, "#000000"], [1, "#00bcd4"]]), width="stretch", key="p_csurf")
    n_snap = surf["ts_ms"].nunique() if surf is not None else 0
    st.caption(f"{exp} · {len(ch)} legs live · {n_snap} snapshots in surfaces · OI = last settled · "
               f"Velocity / Absorb / Pressure overlays pending definitions · refresh 30 s")


# ── panels ───────────────────────────────────────────────────────────
def _price_panel(rec, prints):
    c = rec.candles_df()
    title = "SPX price · 1m · MA9 / MA21 · per-bar delta"
    if c.empty:
        sp = rec.spot_df()
        if sp.empty:
            return _empty("SPX price", "waiting for SPX candles", H_TOP)
        sp = sp.dropna(subset=["spot"])
        sp["m"] = (sp["ts_ms"] // 60000) * 60000
        c = sp.groupby("m")["spot"].agg(["first", "max", "min", "last"]).reset_index()
        c.columns = ["ts_ms", "open", "high", "low", "close"]
    c = c.tail(390 * 2)
    c["t"] = _t(c["ts_ms"])
    f = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
    f.add_candlestick(x=c["t"], open=c["open"], high=c["high"], low=c["low"], close=c["close"],
                      increasing_line_color=GREEN, decreasing_line_color=RED, row=1, col=1)
    f.add_scatter(x=c["t"], y=c["close"].rolling(9).mean(), line=dict(color="#f0c040", width=1), row=1, col=1)
    f.add_scatter(x=c["t"], y=c["close"].rolling(21).mean(), line=dict(color=PURPLE, width=1), row=1, col=1)
    if len(prints):
        p = prints.copy()
        p["m"] = (p["ts_ms"] // 60000) * 60000
        p["d"] = p["aggr"] * p["size"] * p["delta"].fillna(0) * 100
        b = p.groupby("m")["d"].sum().reset_index()
        f.add_bar(x=_t(b["m"]), y=b["d"], marker_color=np.where(b["d"] >= 0, GREEN, RED), row=2, col=1)
    f.update_layout(xaxis_rangeslider_visible=False)
    return _style(f, title, H_TOP)


def _regime_panel(hist):
    h = H_TOP // 2 + 10
    if hist.empty or hist["gamma"].isna().all():
        return _empty("GEX regime · call share of gross gamma", "waiting for snapshots", h)
    e = add_exposures(hist.dropna(subset=["gamma"]))
    e["callg"] = np.where(e["cp"] == 1, e["gex"], 0)
    e["absg"] = e["gex"].abs()
    r = e.groupby("ts_ms").agg(callg=("callg", "sum"), absg=("absg", "sum"), spot=("spot", "last")).reset_index()
    r["share"] = 100 * r["callg"] / r["absg"].replace(0, np.nan)
    r["t"] = _t(r["ts_ms"])
    f = make_subplots(specs=[[{"secondary_y": True}]])
    f.add_scatter(x=r["t"], y=r["share"], mode="lines+markers" if len(r) < 3 else "lines",
                  fill="tozeroy", line=dict(color="white", width=1.5), fillcolor="rgba(46,204,113,0.35)")
    f.add_scatter(x=r["t"], y=r["spot"], mode="lines", line=dict(color="#8b949e", width=1, dash="dot"),
                  secondary_y=True)
    f.add_hline(y=50, line_color="#444", line_width=1)
    f.update_yaxes(range=[0, 100], secondary_y=False)
    return _style(f, "GEX regime · call share of gross gamma (%)", h)


def _imbalance_panel(prints, spot_df):
    h = H_TOP // 2 - 10
    if prints.empty:
        return _empty("Imbalance · CVD", "no prints yet (market closed)", h)
    p = prints.sort_values("ts_ms").copy()
    p["d"] = p["aggr"] * p["size"] * p["delta"].fillna(0) * 100
    p["cvd"] = p["d"].cumsum()
    p["t"] = _t(p["ts_ms"])
    one_h = p.set_index("t")["d"].rolling("60min").sum()
    f = make_subplots(specs=[[{"secondary_y": True}]])
    f.add_scatter(x=p["t"], y=p["cvd"], mode="lines", line=dict(color=GREEN, width=1), fill="tozeroy",
                  fillcolor="rgba(231,76,60,0.25)" if p["cvd"].iloc[-1] < 0 else "rgba(46,204,113,0.25)")
    f.add_scatter(x=one_h.index, y=one_h.values, mode="lines", line=dict(color="#8b949e", width=1, dash="dot"))
    if len(spot_df):
        s = spot_df.dropna(subset=["spot"])
        f.add_scatter(x=_t(s["ts_ms"]), y=s["spot"], mode="lines", line=dict(color="white", width=1),
                      secondary_y=True)
    return _style(f, f"Imbalance · CVD {p['cvd'].iloc[-1]/1e3:+,.0f}K · 1h {one_h.iloc[-1]/1e3:+,.0f}K", h)


def _surface(hist, spot, ctl):
    e = add_exposures(hist.dropna(subset=["gamma"]))
    if e.empty:
        return None
    e = window(e, spot, ctl["mode"], ctl["n"], ctl["pct"])
    return e.groupby(["ts_ms", "strike"]).agg(gex=("gex", "sum"), charm=("charm", "sum"),
                                              spot=("spot", "last")).reset_index()


def _flow_panel(surf):
    title = "0DTE GEX flow · top 7 strikes (net GEX over time)"
    if surf is None or surf.empty:
        return _empty(title, "waiting for snapshots", H_BOT)
    last = surf[surf["ts_ms"] == surf["ts_ms"].max()]
    top = last.reindex(last["gex"].abs().sort_values(ascending=False).index)["strike"].head(7)
    f = go.Figure()
    for k in top:
        s = surf[surf["strike"] == k]
        f.add_scatter(x=_t(s["ts_ms"]), y=s["gex"] / 1e9, mode="lines+markers" if len(s) < 3 else "lines",
                      name=f"{k:,.0f}")
    f.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.12, font=dict(size=10)),
                    yaxis_title="$B / 1%")
    fig = _style(f, title, H_BOT)
    fig.update_layout(showlegend=True)
    return fig


def _heat(surf, col, title, scale):
    if surf is None or surf.empty:
        return _empty(title, "waiting for snapshots", H_BOT)
    z = surf.pivot_table(index="strike", columns="ts_ms", values=col, aggfunc="sum").sort_index()
    cap = float(np.nanpercentile(np.abs(z.values), 98)) or 1.0
    t = pd.to_datetime(z.columns, unit="ms", utc=True).tz_convert(ET)
    f = go.Figure(go.Heatmap(z=z.values, x=t, y=z.index, colorscale=scale, zmin=-cap, zmax=cap,
                             showscale=False))
    sp = surf.groupby("ts_ms")["spot"].last()
    f.add_scatter(x=pd.to_datetime(sp.index, unit="ms", utc=True).tz_convert(ET), y=sp.values,
                  mode="lines+markers" if len(sp) < 3 else "lines", line=dict(color="white", width=1.5))
    return _style(f, title, H_BOT)
