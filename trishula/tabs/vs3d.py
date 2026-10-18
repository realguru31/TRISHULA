"""VS3D — vs3dgbt port on tastytrade data.

Live now (naive, OI-signed, as vs3dgbt showed before its flow seed):
  VS3D combined · Book (by strike) · Terrain (gradient) · GEX³ panel 1.
Flow-signed lenses, Interval, Market Read, DT follow once the signed seed
source is confirmed (Colab test: TimeAndSale replay / Candle bid-ask volume).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.gex import add_exposures, window
from core.timeutil import ET

BG = "#0e1117"
TEAL, RED, VIOLET = "#26a69a", "#ef5350", "#c084fc"
SUBTABS = ["VS3D (combined)", "Book (by strike)", "Terrain (gradient)", "Interval (bubbles)",
           "Market Read", "GEX³ (3-lens)", "DT"]


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


def book_frame(ch: pd.DataFrame) -> pd.DataFrame:
    """Naive per-$1 exposure in SPX index units: calls +, puts − (vs3dgbt convention)."""
    c = ch.dropna(subset=["gamma"]).copy()
    c["pd"] = c["cp"] * c["gamma"] * c["oi"].fillna(0) * 100
    b = c.pivot_table(index="strike", columns="cp", values="pd", aggfunc="sum").fillna(0)
    b = b.rename(columns={1: "call_pd", -1: "put_pd"})
    for col in ("call_pd", "put_pd"):
        if col not in b:
            b[col] = 0.0
    return b.reset_index()


def atm_straddle(ch: pd.DataFrame, spot: float):
    if ch.empty or not spot == spot:
        return None
    k = ch.loc[(ch["strike"] - spot).abs().idxmin(), "strike"]
    legs = ch[ch["strike"] == k]
    mids = ((legs["bid"] + legs["ask"]) / 2).dropna()
    return float(mids.sum()) if len(mids) == 2 else None


def book_fig(b, spot, strad, side, h=820):
    c, p = b["call_pd"] / 50.0, b["put_pd"] / 50.0          # e-minis per $1
    v = c if side == "Calls" else p if side == "Puts" else c + p
    cols = [TEAL if x >= 0 else RED for x in v]
    f = go.Figure(go.Bar(y=b["strike"], x=v, orientation="h", marker_color=cols, width=3.6,
                         hovertemplate="%{y:.0f}: %{x:,.1f} e-mini / $1<extra></extra>"))
    f.add_hline(y=spot, line_dash="dash", line_color="white", line_width=1,
                annotation_text=f"{spot:,.2f}", annotation_font_color="white")
    if strad:
        for yy, tag in ((spot + strad, f"+{strad:.2f}"), (spot - strad, f"-{strad:.2f}")):
            f.add_hline(y=yy, line_dash="dot", line_color=VIOLET, line_width=1,
                        annotation_text=f"{yy:,.2f} ({tag})", annotation_font_color=VIOLET,
                        annotation_font_size=10)
    f.add_vline(x=0, line_color="#666", line_width=1)
    f.update_xaxes(title=dict(text="e-minis per $1 (naive calls+ / puts−)", font=dict(size=10, color="#aaa")))
    return _style(f, f"Positions by strike · {side} · naive", h)


def terrain_fig(hist, spot, ctl, h=820):
    title = "Terrain · naive e-minis per $1 by strike × time"
    if hist.empty or hist["gamma"].isna().all():
        return _empty(title, "waiting for snapshots", h)
    e = hist.dropna(subset=["gamma"]).copy()
    e["v"] = e["cp"] * e["gamma"] * e["oi"].fillna(0) * 100 / 50.0
    e = window(e, spot, ctl["mode"], ctl["n"], ctl["pct"])
    z = e.pivot_table(index="strike", columns="ts_ms", values="v", aggfunc="sum").sort_index()
    cap = float(np.nanpercentile(np.abs(z.values), 98)) or 1.0
    t = pd.to_datetime(z.columns, unit="ms", utc=True).tz_convert(ET)
    f = go.Figure(go.Heatmap(z=z.values, x=t, y=z.index, zmin=-cap, zmax=cap, showscale=True,
                             colorscale=[[0, RED], [0.5, BG], [1, TEAL]],
                             colorbar=dict(thickness=8, len=0.6)))
    sp = e.groupby("ts_ms")["spot"].last()
    f.add_scatter(x=pd.to_datetime(sp.index, unit="ms", utc=True).tz_convert(ET), y=sp.values,
                  mode="lines+markers" if len(sp) < 3 else "lines", line=dict(color="white", width=1.5))
    return _style(f, title, h)


def render(rec, ctl):
    tabs = st.tabs(SUBTABS)

    @st.fragment(run_every=30)
    def _live():
        exp = ctl["exp"]
        spot, ssrc = rec.spot_now()
        ch = rec.live_chain(exp) if exp else pd.DataFrame()
        ok = exp and len(ch) and ch["gamma"].notna().any() and spot == spot
        b = window(book_frame(ch), spot, ctl["mode"], ctl["n"], ctl["pct"]) if ok else pd.DataFrame()
        strad = atm_straddle(ch, spot) if ok else None
        h = rec.chain_df()
        if len(h):
            h = h[h["exp"] == exp]
        hist = pd.concat([h, ch], ignore_index=True) if len(ch) else h
        side = st.session_state.get("vs3d_side", "Total")
        head = (f"{exp} · spot {spot:,.2f} ({ssrc}) · ATM straddle "
                f"{strad:,.2f}" if strad else f"{exp} · spot {spot:,.2f} ({ssrc})") if ok else "waiting for chain"

        with tabs[0]:
            st.caption(head + " · signing: NAIVE (calls+ / puts−) until the flow seed is wired")
            a, c = st.columns([1, 1.6])
            a.plotly_chart(book_fig(b, spot, strad, side) if ok and len(b) else
                           _empty("Positions by strike", "waiting for greeks / OI", 820),
                           width="stretch", key="vs_c_book")
            c.plotly_chart(terrain_fig(hist, spot, ctl), width="stretch", key="vs_c_terr")
        with tabs[1]:
            st.caption(head)
            st.plotly_chart(book_fig(b, spot, strad, side, 900) if ok and len(b) else
                            _empty("Positions by strike", "waiting for greeks / OI", 900),
                            width="stretch", key="vs_book")
        with tabs[2]:
            st.plotly_chart(terrain_fig(hist, spot, ctl, 900), width="stretch", key="vs_terr")
        with tabs[5]:
            st.caption("GEX³ panel 1 · convention (naive). Panel 2 flow-signed and panel 3 Δ-OI arrive with the seed "
                       "and the second recorded session.")
            if ok:
                e = add_exposures(ch.dropna(subset=["gamma"]), spot)
                g = e.groupby("strike")["gex"].sum().reset_index()
                g = window(g, spot, ctl["mode"], ctl["n"], ctl["pct"])
                f = go.Figure(go.Bar(y=g["strike"], x=g["gex"] / 1e9, orientation="h", width=3.6,
                                     marker_color=[TEAL if x >= 0 else RED for x in g["gex"]]))
                f.add_hline(y=spot, line_dash="dash", line_color="white", line_width=1)
                f.update_xaxes(title=dict(text="$B per 1% (convention)", font=dict(size=10, color="#aaa")))
                st.plotly_chart(_style(f, "GEX³ · panel 1 · convention", 820), width="stretch", key="vs_g3")
            else:
                st.plotly_chart(_empty("GEX³ · panel 1", "waiting for greeks / OI", 820), width="stretch", key="vs_g3")

    with tabs[1]:
        st.segmented_control("Side", ["Total", "Calls", "Puts"], default="Total", key="vs3d_side")
    for i, msg in ((3, "Interval bubbles need recorded snapshots + prints across the session; "
                       "they start filling from Sunday 19:00 ET recording."),
                   (4, "Market Read needs the opening straddle, VIX 5-min tape and the 09:35 card lock; "
                       "it activates on the first RTH session recorded."),
                   (6, "DT needs per-minute signed net flow per strike — live from the recorded tape once "
                       "prints flow (Sunday evening onward).")):
        with tabs[i]:
            st.info(msg)
    _live()
