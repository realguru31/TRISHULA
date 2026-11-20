"""v0.39.0 OrderFlow tab (VS3D sub-tab next to Lean) — options delta map (candles, default) or footprint.
Colours as Lean: blue = customers bought deltas (calls bought / puts sold) · magenta = sold deltas."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import lean as LN
from core import orderflow as OF
from core.timeutil import ET, now_et

BG = "#0e1117"
BLUE, MAG = "#2f8cff", "#ff2dc4"


def _rgba(hexc, a):
    h = hexc.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a:.2f})"


def _frame(rec, exp, legs):
    a = OF.minutes(rec, exp)
    b = LN.spx_minutes(rec)
    if not len(a) or not len(b):
        return None, None
    day = pd.Timestamp(now_et().date())
    t0 = int(pd.Timestamp(day + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)
    t1 = int(pd.Timestamp(day + pd.Timedelta("16h")).tz_localize(ET).timestamp() * 1000)
    k = "sl" if legs == "single-leg" else "al"
    a = a[(a["m"] >= t0) & (a["m"] < t1)][["m", "row", f"{k}_buy", f"{k}_sell"]].rename(
        columns={f"{k}_buy": "buy", f"{k}_sell": "sell"})
    b = b[(b["m"] >= t0) & (b["m"] < t1)]
    for x in (a, b):
        x["t"] = pd.to_datetime(x["m"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return a, b


def _ohlc(b, bar):
    return b.groupby(b["t"].dt.floor(bar)).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))


def delta_map(a, b, legs, bar="5min"):
    g = a.assign(col=a["t"].dt.floor(bar)).groupby(["col", "row"], as_index=False)[["buy", "sell"]].sum()
    g["net"] = (g["buy"] - g["sell"]) / 1000
    M = g.pivot_table(index="row", columns="col", values="net", aggfunc="sum").sort_index()
    nz = np.abs(M.values[np.isfinite(M.values) & (M.values != 0)])
    lim = float(np.percentile(nz, 97)) if len(nz) else 1.0
    o = _ohlc(b, bar)
    half = pd.Timedelta(bar) / 2
    cum = a.groupby("t")[["buy", "sell"]].sum()
    cum = ((cum["buy"] - cum["sell"]).cumsum() / 1e6)
    f = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.74, 0.26], vertical_spacing=0.03,
                      specs=[[{}], [{"secondary_y": True}]])
    f.add_heatmap(x=M.columns + half, y=M.index + OF.ROW / 2, z=M.values, zmin=-lim, zmax=lim, zmid=0,
                  colorscale=[[0, MAG], [0.5, BG], [1, BLUE]], colorbar=dict(title="k Δ", len=0.55, y=0.7),
                  hovertemplate="%{x|%H:%M} · SPX %{y:.0f} · %{z:+,.0f}k Δ<extra></extra>", row=1, col=1)
    f.add_candlestick(x=o.index + half, open=o.o, high=o.h, low=o.l, close=o.c, increasing_line_color="#c9d1d9",
                      decreasing_line_color="#6e7681", increasing_fillcolor="rgba(0,0,0,0)",
                      decreasing_fillcolor="rgba(0,0,0,0)", showlegend=False, row=1, col=1)
    f.add_scatter(x=cum.index, y=cum.values, mode="lines", line=dict(color=BLUE, width=2), name="cum options Δ (M)",
                  row=2, col=1)
    sx = b.set_index("t")["c"]
    f.add_scatter(x=sx.index, y=sx.values, mode="lines", line=dict(color="#c9d1d9", width=1.2), name="SPX",
                  row=2, col=1, secondary_y=True)
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=820,
                    xaxis_rangeslider_visible=False, margin=dict(l=50, r=20, t=40, b=20),
                    legend=dict(x=0.01, y=0.24, bgcolor="rgba(0,0,0,0)"),
                    title=dict(text=f"OPTIONS DELTA MAP · {legs} · {bar} × {OF.ROW:g}-pt · blue = deltas bought · "
                                    f"magenta = sold · colour cap ±{lim:,.0f}k", font=dict(size=13)))
    f.update_yaxes(title_text="SPX", row=1, col=1)
    f.update_yaxes(title_text="cum Δ (M)", row=2, col=1, secondary_y=False)
    f.update_yaxes(title_text="SPX", row=2, col=1, secondary_y=True)
    return f


def footprint(a, b, legs, bar="15min", last=None):
    g = a.assign(col=a["t"].dt.floor(bar)).groupby(["col", "row"], as_index=False)[["buy", "sell"]].sum()
    if last:                                         # v0.39.0: the last N bars so the numbers stay readable
        keep = sorted(g["col"].unique())[-last:]
        g = g[g["col"].isin(keep)]
        b = b[b["t"] >= keep[0]] if keep else b
    g["net"] = g["buy"] - g["sell"]
    bars = sorted(g["col"].unique())
    bi = {x: i for i, x in enumerate(bars)}
    g["x"] = g["col"].map(bi)
    lim = float(np.percentile(np.abs(g["net"]), 95)) if len(g) else 1.0
    lim = lim or 1.0
    o = _ohlc(b, bar)
    W = 0.86
    f = go.Figure()
    shapes, notes = [], []
    for r in g.itertuples():
        v = max(-1.0, min(1.0, r.net / lim))
        shapes.append(dict(type="rect", x0=r.x - W / 2, x1=r.x + W / 2, y0=r.row, y1=r.row + OF.ROW, layer="below",
                           line=dict(width=0.3, color="#30363d"),
                           fillcolor=_rgba(BLUE if v > 0 else MAG, 0.10 + 0.75 * abs(v))))
        notes.append(dict(x=r.x, y=r.row + OF.ROW / 2, text=f"{r.sell / 1000:.0f} × {r.buy / 1000:.0f}",
                          showarrow=False, font=dict(size=9, color="#e6edf3")))
    for x0, i in bi.items():
        if x0 in o.index:
            c = o.loc[x0]
            xl = i - W / 2 - 0.06
            shapes.append(dict(type="line", x0=xl, x1=xl, y0=c.l, y1=c.h, line=dict(color="#c9d1d9", width=1)))
            shapes.append(dict(type="rect", x0=xl - 0.04, x1=xl + 0.04, y0=min(c.o, c.c), y1=max(c.o, c.c),
                               line=dict(color="#c9d1d9", width=1), fillcolor="#c9d1d9" if c.c >= c.o else BG))
        tot = g[g["col"] == x0]
        net = tot["net"].sum() / 1000
        notes.append(dict(x=i, y=float(tot["row"].min()) - 3, text=f"<b>{net:+,.0f}k</b>", showarrow=False,
                          font=dict(size=11, color=BLUE if net > 0 else MAG)))
    f.add_scatter(x=list(bi.values()), y=[float(g["row"].mean())] * len(bi), mode="markers",
                  marker=dict(opacity=0), hoverinfo="skip", showlegend=False)
    f.update_layout(shapes=shapes, annotations=notes, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                    height=max(700, int((g["row"].max() - g["row"].min()) / OF.ROW * 22) + 120) if len(g) else 700,
                    margin=dict(l=55, r=20, t=40, b=30), showlegend=False,
                    title=dict(text=f"OPTIONS DELTA FOOTPRINT · {legs} · {bar} × {OF.ROW:g}-pt · cell = sold × bought "
                                    f"(k Δ) · colour = net (cap ±{lim / 1000:,.0f}k) · bar total under each bar",
                               font=dict(size=13)))
    f.update_xaxes(tickvals=list(bi.values()), ticktext=[pd.Timestamp(x).strftime("%H:%M") for x in bars],
                   range=[-0.8, len(bars) - 0.3] if bars else None, showgrid=False)
    if len(g):
        f.update_yaxes(range=[float(g["row"].min()) - 6, float(g["row"].max()) + 4], dtick=10, gridcolor="#21262d",
                       title="SPX")
    return f


def render(rec):
    rec = getattr(rec, "_rec", rec)
    st.caption("OrderFlow — options delta at the SPX price where it traded (OFL Delta Map idea with options delta): "
               "customer Δ = aggressor × option delta × size × 100 · blue = deltas bought (calls bought / puts sold) · "
               "magenta = deltas sold · 0DTE · RTH. 18 Nov check: tracks the bar's move (single-leg a bit tighter than "
               "all prints), does NOT predict the next bar — read it for divergences / exhaustion at turns.")
    c1, c2, c4, c3 = st.columns([1.5, 1.4, 1.4, 3])
    view = c1.segmented_control("view", ["candles", "footprint"], default="candles", key="of_view",
                                label_visibility="collapsed") or "candles"
    legs = c2.segmented_control("prints", ["single-leg", "all"], default="single-leg", key="of_legs",
                                label_visibility="collapsed") or "single-leg"
    span = c4.segmented_control("footprint span", ["last 3h", "full day"], default="last 3h", key="of_span",
                                label_visibility="collapsed", help="footprint only: 15-min bars; the full day squeezes the "
                                                                  "numbers") or "last 3h"
    exps = rec.status().get("expiries") or []
    if not exps:
        st.info("waiting for the chain")
        return
    a, b = _frame(rec, str(exps[0]), legs)
    if a is None or not len(a) or len(b) < 2:
        st.info("waiting for RTH prints and bars (09:30 ET)")
        return
    c3.caption(f"{exps[0]} · {len(a):,} minute × row cells · bought {a['buy'].sum() / 1e6:,.2f}M Δ · "
               f"sold {a['sell'].sum() / 1e6:,.2f}M Δ · net {(a['buy'].sum() - a['sell'].sum()) / 1e6:+,.2f}M")
    fig = delta_map(a, b, legs) if view == "candles" else footprint(a, b, legs, last=12 if span == "last 3h" else None)
    st.plotly_chart(fig, width="stretch", key=f"of_{view}")
