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
from core import unusual as UN
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


def _xframe(rec, mkt, legs):
    """v0.40.0: ES / SPY options — same frame, rows and candles from the underlying price at each print."""
    a, b = OF.xminutes(rec, mkt)
    if not len(a) or not len(b):
        return None, None
    day = pd.Timestamp(now_et().date())
    t0 = int(pd.Timestamp(day + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)
    t1 = int(pd.Timestamp(day + pd.Timedelta("16h")).tz_localize(ET).timestamp() * 1000)
    k = "sl" if legs == "single-leg" else "al"
    a = a[(a["m"] >= t0) & (a["m"] < t1)][["m", "row", f"{k}_buy", f"{k}_sell"]].rename(
        columns={f"{k}_buy": "buy", f"{k}_sell": "sell"})
    b = b[(b["m"] >= t0) & (b["m"] < t1)].copy()
    for x in (a, b):
        x["t"] = pd.to_datetime(x["m"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return a, b


def _ohlc(b, bar):
    return b.groupby(b["t"].dt.floor(bar)).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))


def delta_map(a, b, legs, bar="5min", row=OF.ROW, name="SPX", height=820):
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
    f.add_heatmap(x=M.columns + half, y=M.index + row / 2, z=M.values, zmin=-lim, zmax=lim, zmid=0,
                  colorscale=[[0, MAG], [0.5, BG], [1, BLUE]], colorbar=dict(title="k Δ", len=0.55, y=0.7),
                  hovertemplate="%{x|%H:%M} · " + name + " %{y:" + (".1f" if row < 1 else ".0f") + "} · %{z:+,.0f}k Δ<extra></extra>", row=1, col=1)
    f.add_candlestick(x=o.index + half, open=o.o, high=o.h, low=o.l, close=o.c, increasing_line_color="#c9d1d9",
                      decreasing_line_color="#6e7681", increasing_fillcolor="rgba(0,0,0,0)",
                      decreasing_fillcolor="rgba(0,0,0,0)", showlegend=False, row=1, col=1)
    f.add_scatter(x=cum.index, y=cum.values, mode="lines", line=dict(color=BLUE, width=2), name="cum options Δ (M)",
                  row=2, col=1)
    sx = b.set_index("t")["c"]
    f.add_scatter(x=sx.index, y=sx.values, mode="lines", line=dict(color="#c9d1d9", width=1.2), name=name,
                  row=2, col=1, secondary_y=True)
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=height,
                    xaxis_rangeslider_visible=False, margin=dict(l=50, r=20, t=40, b=20),
                    legend=dict(x=0.01, y=0.24, bgcolor="rgba(0,0,0,0)"),
                    title=dict(text=f"{name} OPTIONS DELTA MAP · {legs} · {bar} × {row:g}-pt · blue = deltas bought · "
                                    f"magenta = sold · colour cap ±{lim:,.0f}k", font=dict(size=13)))
    f.update_yaxes(title_text=name, row=1, col=1)
    f.update_yaxes(title_text="cum Δ (M)", row=2, col=1, secondary_y=False)
    f.update_yaxes(title_text=name, row=2, col=1, secondary_y=True)
    return f


def footprint(a, b, legs, bar="15min", last=None, row=OF.ROW, name="SPX"):
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
        shapes.append(dict(type="rect", x0=r.x - W / 2, x1=r.x + W / 2, y0=r.row, y1=r.row + row, layer="below",
                           line=dict(width=0.3, color="#30363d"),
                           fillcolor=_rgba(BLUE if v > 0 else MAG, 0.10 + 0.75 * abs(v))))
        notes.append(dict(x=r.x, y=r.row + row / 2, text=f"{r.sell / 1000:.0f} × {r.buy / 1000:.0f}",
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
        notes.append(dict(x=i, y=float(tot["row"].min()) - 1.5 * row, text=f"<b>{net:+,.0f}k</b>", showarrow=False,
                          font=dict(size=11, color=BLUE if net > 0 else MAG)))
    f.add_scatter(x=list(bi.values()), y=[float(g["row"].mean())] * len(bi), mode="markers",
                  marker=dict(opacity=0), hoverinfo="skip", showlegend=False)
    f.update_layout(shapes=shapes, annotations=notes, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                    height=max(700, int((g["row"].max() - g["row"].min()) / row * 22) + 120) if len(g) else 700,
                    margin=dict(l=55, r=20, t=40, b=30), showlegend=False,
                    title=dict(text=f"{name} OPTIONS DELTA FOOTPRINT · {legs} · {bar} × {row:g}-pt · cell = sold × bought "
                                    f"(k Δ) · colour = net (cap ±{lim / 1000:,.0f}k) · bar total under each bar",
                               font=dict(size=13)))
    f.update_xaxes(tickvals=list(bi.values()), ticktext=[pd.Timestamp(x).strftime("%H:%M") for x in bars],
                   range=[-0.8, len(bars) - 0.3] if bars else None, showgrid=False)
    if len(g):
        f.update_yaxes(range=[float(g["row"].min()) - 3 * row, float(g["row"].max()) + 2 * row], dtick=5 * row,
                       gridcolor="#21262d", title=name)
    return f



# ── v0.41.0 unusual options marks ────────────────────────────────────────────────────────────────────────────────────
UNU = {"big prints": "big", "bursts": "burst", "paying up": "pay", "new positions": "new"}
SHAPE = {"big": "circle", "burst": "diamond", "pay": "triangle-up", "new": "square", "multi": "star"}
LBL = {"big": "big print", "burst": "burst", "pay": "paying up", "new": "new position", "multi": "2+ flags"}


def _t(ms):
    return pd.to_datetime(pd.Series(ms, dtype="int64"), unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)


def _fp_x(t, a, bar, last):
    """footprint x (bar index + position inside the bar) for times t; NaN outside the shown bars."""
    bars = sorted(a.assign(col=a["t"].dt.floor(bar))["col"].unique())
    if last:
        bars = bars[-last:]
    bi = {x: i for i, x in enumerate(bars)}
    fl = t.dt.floor(bar)
    i = fl.map(bi).astype(float)
    frac = (t - fl) / pd.Timedelta(bar)
    return (i - 0.43 + 0.86 * frac).values


def add_marks(fig, g, bursts, on, view, a, last=None, sel=None, rowcol=None):
    """Unusual marks on the candles (or footprint) at the underlying price and time; size by contracts."""
    if g is None or not len(g):
        return
    kw = rowcol or {}
    pts = g[g[on].any(axis=1)] if on else g.iloc[:0]
    smax = float(max(pts["size"].max() if len(pts) else 1, bursts["v"].max() if len(bursts) else 1))

    def xy(ms, S):
        t = _t(ms)
        return (t.values if view == "candles" else _fp_x(t, a, "15min", last)), np.asarray(S, float)

    def sz(v):
        return 7 + 24 * np.sqrt(np.asarray(v, float) / smax)
    nf = pts[on].sum(1) if len(pts) else pd.Series(dtype=float)
    groups = [("multi", pts[nf >= 2])] + [(k, pts[(nf == 1) & pts[k]]) for k in on if k != "burst"]
    for k, d in groups:
        if not len(d):
            continue
        x, y = xy(d["ts_ms"].values, d["S"].values)
        bull = (d["new_bull"] if k == "new" and "new_bull" in d else d["bull"]).values
        cd = np.stack([[f"{v:g}" for v in d["strike"]], np.where(d["cp"] > 0, "C", "P"), [f"{v:,.0f}" for v in d["size"]],
                       [f"{v:.2f}" for v in d["px"]], np.where(d["aggr"] > 0, "bought", "sold"),
                       [f"{v / 1e3:,.0f}" for v in d["prem"]]], axis=1)
        fig.add_scatter(x=x, y=y, mode="markers", name=LBL[k], customdata=cd, showlegend=False,
                        marker=dict(symbol=SHAPE[k], size=sz(d["size"].values), color=np.where(bull > 0, BLUE, MAG),
                                    line=dict(color="white", width=0.8), opacity=0.9),
                        hovertemplate=f"{LBL[k]} · %{{customdata[0]}}%{{customdata[1]}} · %{{customdata[2]}} @ "
                                      "%{customdata[3]} %{customdata[4]} · $%{customdata[5]}k<extra></extra>", **kw)
    if "burst" in on and len(bursts):
        x, y = xy(bursts["ts_ms"].values, bursts["S"].values)
        cd = np.stack([[f"{v:g}" for v in bursts["k"]], [f"{v:,.0f}" for v in bursts["v"]],
                       [f"{v:.1f}" for v in bursts["v"] / bursts["med"].clip(lower=1)]], axis=1)
        fig.add_scatter(x=x, y=y, mode="markers", name="burst", customdata=cd, showlegend=False,
                        marker=dict(symbol="diamond", size=sz(bursts["v"].values), color=np.where(bursts["b"] > 0, BLUE, MAG),
                                    line=dict(color="white", width=0.6), opacity=0.75),
                        hovertemplate="burst · %{customdata[0]} · %{customdata[1]} contracts this minute · "
                                      "%{customdata[2]}× its median<extra></extra>", **kw)
    if sel is not None:
        x, y = xy(np.array([sel[0]]), np.array([sel[1]]))
        fig.add_scatter(x=x, y=y, mode="markers", showlegend=False, hoverinfo="skip",
                        marker=dict(symbol="circle-open", size=38, color="#ffd600", line=dict(width=3)), **kw)


def unusual_controls():
    """Toggles 1–4 + the settings of each switched-on flag (shown only when on) + table settings."""
    pick = st.pills("unusual", list(UNU), selection_mode="multi", key="of_unu", label_visibility="collapsed") or []
    on = [UNU[x] for x in pick]
    p = dict(UN.DEF)
    if not on:
        return on, p, None
    W = [15, 30, 60, 120, "day"]
    if "big" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**big prints**")
        p["big_pct"] = c[1].segmented_control("big cut", [99.0, 99.5, 99.9, 99.97, 99.99], default=99.9, key="of_big_pct",
                                              format_func=lambda v: f"top {round(100 - v, 2):g} %") or 99.9
        p["big_win"] = c[2].segmented_control("big lookback", W, default=60, key="of_big_win",
                                              format_func=lambda v: "full day" if v == "day" else f"{v} min") or 60
        p["big_floor"] = c[3].segmented_control("big floor", [3.0, 5.0, 10.0], default=5.0, key="of_big_floor",
                                                format_func=lambda v: f"≥ {v:g}× median") or 5.0
    if "burst" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**bursts**")
        p["burst_k"] = c[1].segmented_control("burst k", [2.0, 3.0, 5.0, 10.0, 20.0], default=3.0, key="of_burst_k",
                                              format_func=lambda v: f"{v:g}×") or 3.0
        p["burst_win"] = c[2].segmented_control("burst median", [15, 30, 60], default=30, key="of_burst_win",
                                                format_func=lambda v: f"median {v} min") or 30
    if "pay" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**paying up**")
        p["pay_mode"] = c[1].segmented_control("pay mode", ["at or through", "through only"], default="at or through",
                                               key="of_pay_mode") or "at or through"
        p["pay_pct"] = c[2].segmented_control("pay cut", [99.0, 99.5, 99.9, 99.97, 99.99], default=99.9, key="of_pay_pct",
                                              format_func=lambda v: f"size top {round(100 - v, 2):g} %") or 99.9
        p["pay_win"] = c[3].segmented_control("pay lookback", W, default=60, key="of_pay_win",
                                              format_func=lambda v: "day" if v == "day" else f"{v}m") or 60
    if "new" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**new positions**")
        p["new_ratio"] = c[1].segmented_control("new ratio", [1.0, 1.5, 2.0], default=1.0, key="of_new_ratio",
                                                format_func=lambda v: f"volume ≥ {v:g}× OI") or 1.0
        p["new_min_oi"] = c[2].segmented_control("new min oi", [50, 100, 500, 1000], default=100, key="of_new_min_oi",
                                                 format_func=lambda v: f"OI ≥ {v:,}") or 100
    c = st.columns([1.2, 2, 3, 2])
    c[0].markdown("**table**")
    tb = dict(n=c[1].segmented_control("rows", [20, 50, 100], default=20, key="of_tab_n",
                                       format_func=lambda v: f"top {v}") or 20,
              sort=c[2].segmented_control("sort", ["premium", "size", "time"], default="premium", key="of_tab_sort",
                                          format_func=lambda v: f"by {v}") or "premium",
              min_flags=c[3].segmented_control("min flags", [1, 2], default=1, key="of_tab_min",
                                               format_func=lambda v: "any flag" if v == 1 else "2+ flags") or 1)
    return on, p, tb

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
    mkt = c3.segmented_control("market", ["SPX", "ES", "SPY", "3 stacked"], default="SPX", key="of_mkt",
                               label_visibility="collapsed") or "SPX"
    exps = rec.status().get("expiries") or []
    if not exps:
        st.info("waiting for the chain")
        return
    last = 12 if span == "last 3h" else None
    on, prm, tb = unusual_controls()
    day = pd.Timestamp(now_et().date())
    sel = None
    tsel = (st.session_state.get("of_tab") or {}).get("selection", {}).get("rows", []) if on else []
    prev = st.session_state.get("_of_tab_rows")
    if tsel and prev is not None and tsel[0] < len(prev):
        r = prev.iloc[tsel[0]]
        sel = (r["mkt"], int(r["_ts"]), float(r["_S"]))
    tabs = []
    for m in (["SPX", "ES", "SPY"] if mkt == "3 stacked" else [mkt]):
        if m == "SPX":
            a, b = _frame(rec, str(exps[0]), legs)
            row, lbl = OF.ROW, str(exps[0])
        else:
            a, b = _xframe(rec, m, legs)
            row = OF.XROW[m]
            inf = (getattr(rec, "xinfo", {}) or {}).get(m, {})
            lbl = f"{m} options {inf.get('exp', '')}" + (" · no spread-leg flag on the ES feed" if m == "ES" else "")
        if a is None or not len(a) or len(b) < 2:
            st.info(f"{m}: waiting for RTH prints and bars (09:30 ET)")
            continue
        g = bu = None
        cnt = ""
        if on:
            try:
                fx = UN.frame(rec, m, str(exps[0]) if m == "SPX" else (getattr(rec, "xinfo", {}) or {}).get(m, {}).get("exp", ""))
                g, bu = UN.detect(fx, m, day, legs, on, prm)
                if len(g):
                    tabs.append(UN.table(g, on, m, tb["n"], tb["sort"], tb["min_flags"]))
                    cnt = " · unusual: " + " · ".join(
                        f"{LBL[k]} {(len(bu) if k == 'burst' else int(g[k].sum())):,}" for k in on)
            except Exception as e:                       # noqa: BLE001
                st.caption(f"unusual: {type(e).__name__}: {e}")
        st.caption(f"{lbl} · {len(a):,} minute × row cells · bought {a['buy'].sum() / 1e6:,.2f}M Δ · "
                   f"sold {a['sell'].sum() / 1e6:,.2f}M Δ · net {(a['buy'].sum() - a['sell'].sum()) / 1e6:+,.2f}M{cnt}")
        h = 560 if mkt == "3 stacked" else 820
        fig = delta_map(a, b, legs, row=row, name=m, height=h) if view == "candles" else \
            footprint(a, b, legs, last=last, row=row, name=m)
        if on and g is not None:
            add_marks(fig, g, bu, on, view, a, last=last, sel=sel[1:] if sel and sel[0] == m else None,
                      rowcol=dict(row=1, col=1) if view == "candles" else None)
        st.plotly_chart(fig, width="stretch", key=f"of_{view}_{m}")
    if on:
        t = pd.concat([x for x in tabs if len(x)], ignore_index=True) if any(len(x) for x in tabs) else pd.DataFrame()
        if len(t):
            if len(tabs) > 1:
                t = t.sort_values({"premium": "premium $", "size": "size", "time": "_ts"}[tb["sort"]],
                                  ascending=False).head(tb["n"]).reset_index(drop=True)
            st.session_state["_of_tab_rows"] = t
            st.dataframe(t.drop(columns=["_ts", "_S"]), hide_index=True, width="stretch", key="of_tab",
                         on_select="rerun", selection_mode="single-row",
                         column_config={"premium $": st.column_config.NumberColumn(format="$%d"),
                                        "strike": st.column_config.NumberColumn(format="%.0f")})
        else:
            st.caption("no unusual trades for the switched-on flags yet")
