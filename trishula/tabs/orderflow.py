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


def _frame(rec, exp, legs, drop_mid=False):
    a = OF.minutes(rec, exp)
    b = LN.spx_minutes(rec)
    if not len(a) or not len(b):
        return None, None
    day = pd.Timestamp(now_et().date())
    t0 = int(pd.Timestamp(day + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)
    t1 = int(pd.Timestamp(day + pd.Timedelta("16h")).tz_localize(ET).timestamp() * 1000)
    k = ("sl" if legs == "single-leg" else "al") + ("x" if drop_mid else "")
    a = a[(a["m"] >= t0) & (a["m"] < t1)][["m", "row", f"{k}_buy", f"{k}_sell"]].rename(
        columns={f"{k}_buy": "buy", f"{k}_sell": "sell"})
    b = b[(b["m"] >= t0) & (b["m"] < t1)]
    for x in (a, b):
        x["t"] = pd.to_datetime(x["m"], unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return a, b


def _xframe(rec, mkt, legs, drop_mid=False):
    """v0.40.0: ES / SPY options — same frame, rows and candles from the underlying price at each print."""
    a, b = OF.xminutes(rec, mkt)
    if not len(a) or not len(b):
        return None, None
    day = pd.Timestamp(now_et().date())
    t0 = int(pd.Timestamp(day + pd.Timedelta("9h30min")).tz_localize(ET).timestamp() * 1000)
    t1 = int(pd.Timestamp(day + pd.Timedelta("16h")).tz_localize(ET).timestamp() * 1000)
    k = ("sl" if legs == "single-leg" else "al") + ("x" if drop_mid else "")
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
UNU = {"big orders": "big", "bursts": "burst", "paying up": "pay", "new positions": "new"}
SHAPE = {"big": "circle", "burst": "diamond", "pay": "triangle-up", "new": "square", "multi": "star"}
LBL = {"big": "big order", "burst": "burst", "pay": "paying up", "new": "new position", "multi": "2+ flags"}


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
        txt = [f"{a_}{b_} {'bot' if c_ == 'bought' else 'sold'} {d_} · ${e_}k" for a_, b_, d_, c_, e_ in
               zip(cd[:, 0], cd[:, 1], cd[:, 2], cd[:, 4], cd[:, 5])]
        if k == "new" and "oi" in d:                     # new positions: say how big the position was
            txt = [f"{a_}{b_} vol > OI {o_:,.0f}" for a_, b_, o_ in zip(cd[:, 0], cd[:, 1], d["oi"].values)]
        fig.add_scatter(x=x, y=y, mode="markers+text", text=txt, textposition="top center", name=LBL[k],
                        textfont=dict(size=10, color="#e6edf3"), customdata=cd, showlegend=False,
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
    pick = st.pills("unusual", list(UNU), selection_mode="multi", key="of_unu", label_visibility="collapsed",
                    default=["bursts", "paying up", "new positions"],      # v0.42.2: the write-up's "paid up, in a
                    help="defaults follow the 'zero' write-up: paid up (paying up), in a hurry (bursts — our proxy for "
                         "sweeps, which our feed cannot see), on purpose / opening (new positions)") or []
    on = [UNU[x] for x in pick]
    p = dict(UN.DEF)
    if not on:
        return on, p, None
    N = [5, 10, 20]
    fn = lambda v: f"top {v}"                            # noqa: E731
    if "big" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**big orders**")
        p["big_n"] = c[1].segmented_control("big n", N, default=10, key="of_big_n", format_func=fn) or 10
        c[2].caption("by delta notional · prints on one contract, same side, same second = one order")
    if "burst" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**bursts**")
        p["burst_k"] = c[1].segmented_control("burst k", [2.0, 3.0, 5.0, 10.0], default=3.0, key="of_burst_k",
                                              format_func=lambda v: f"> {v:g}× median") or 3.0
        p["burst_win"] = c[2].segmented_control("burst median", [15, 30, 60], default=30, key="of_burst_win",
                                                format_func=lambda v: f"median of {v} min") or 30
        p["burst_n"] = c[3].segmented_control("burst n", N, default=10, key="of_burst_n", format_func=fn) or 10
    if "pay" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**paying up**")
        p["pay_mode"] = c[1].segmented_control("pay mode", ["at or through", "through only"], default="at or through",
                                               key="of_pay_mode") or "at or through"
        p["pay_n"] = c[2].segmented_control("pay n", N, default=10, key="of_pay_n", format_func=fn) or 10
    if "new" in on:
        c = st.columns([1.2, 2, 3, 2])
        c[0].markdown("**new positions**")
        p["new_ratio"] = c[1].segmented_control("new ratio", [1.0, 1.5, 2.0], default=1.0, key="of_new_ratio",
                                                format_func=lambda v: f"volume ≥ {v:g}× OI") or 1.0
        p["new_min_oi"] = c[2].segmented_control("new min oi", [50, 100, 500, 1000], default=100, key="of_new_min_oi",
                                                 format_func=lambda v: f"OI ≥ {v:,}") or 100
        p["new_n"] = c[3].segmented_control("new n", N, default=10, key="of_new_n", format_func=fn) or 10
    p["drop_cross"] = st.toggle("drop crosses / blocks at mid", value=True, key="of_cross",
                                help="a print at the middle of the bid/ask AND in the day's top 0.5 % by size (≥ 50 "
                                     "contracts) is usually a negotiated cross or hedge, not someone paying up")
    c = st.columns([1.2, 2, 3, 2])
    c[0].markdown("**table**")
    tb = dict(n=c[1].segmented_control("rows", [20, 50, 100], default=20, key="of_tab_n",
                                       format_func=lambda v: f"top {v}") or 20,
              sort=c[2].segmented_control("sort", ["delta $", "premium", "size", "time"], default="delta $",
                                          key="of_tab_sort", format_func=lambda v: f"by {v}") or "delta $",
              min_flags=c[3].segmented_control("min flags", [1, 2], default=1, key="of_tab_min",
                                               format_func=lambda v: "any flag" if v == 1 else "2+ flags") or 1)
    return on, p, tb


# ── v0.42.0 fade or follow at the day's extremes ─────────────────────────────────────────────────────────────────────
def extremes_panel(rec, sess=False):
    """Score of the last 15 finished events of each kind (earlier saved days + today) → FADE / FOLLOW / SIT OUT, and
    today's events for the chart. Cached on the recorder per minute."""
    from core import extremes as XT
    from core import lean as LN
    key = (int(now_et().timestamp() // 60), sess)
    c = getattr(rec, "_xt_cache", None)
    if c and c[0] == key:
        return c[1]
    today = now_et().strftime("%Y-%m-%d")
    try:
        d = LN.live_day(rec)
        ev_t = XT.events(d).assign(day=today) if d else pd.DataFrame()
    except Exception:                                    # noqa: BLE001
        ev_t = pd.DataFrame()
    try:
        ev_h = XT.history(today)
    except Exception:                                    # noqa: BLE001
        ev_h = pd.DataFrame()
    ev = pd.concat([x for x in (ev_h, ev_t) if len(x)], ignore_index=True) if (len(ev_h) or len(ev_t)) else pd.DataFrame()
    sc = XT.score(ev, sess) if len(ev) else {"fade": (0, np.nan, np.nan), "follow": (0, np.nan, np.nan), "verdict": "SIT OUT"}
    if sess and len(ev_t) and "sess_ok" in ev_t:
        ev_t = ev_t[ev_t["sess_ok"].fillna(False).astype(bool)]
    log = pd.DataFrame()
    try:                                                 # v0.42.1: paper-grade today's calls on live 1DTE bid/ask
        exps = [str(e) for e in (getattr(rec, "exps", None) or [])]
        if len(exps) > 1 and len(ev_t):
            log = XT.grade(ev_t, rec.chain_df(), exps[1], int(now_et().timestamp() * 1000))
            _save_calls(rec, today, log, sess)
    except Exception:                                    # noqa: BLE001
        pass
    out = (sc, ev_t, len(set(ev_h["day"])) if len(ev_h) else 0, log)
    try:
        rec._xt_cache = (key, out)
    except Exception:                                    # noqa: BLE001
        pass
    return out



def _save_calls(rec, day, log, sess):
    """Once after 16:00 ET: today's graded calls → state/calls/YYYY-MM-DD.json (the scorecard collects over days)."""
    if not len(log) or now_et().hour < 16 or getattr(rec, "_calls_saved", None) == day:
        return
    from core import state as ST
    try:
        rows = log.assign(t=log["t"].astype(str)).to_dict(orient="records")
        ST.save_file(f"state/calls/{day}.json", {"day": day, "session_filter": sess, "calls": rows}, f"calls {day}")
        rec._calls_saved = day
    except Exception:                                    # noqa: BLE001
        pass


def noise_box(a_all: pd.DataFrame, spot: float) -> str:
    """zero's NOISE FILTER: flow read (single-leg, not mid) vs set aside (spread legs + mid prints), today, $ delta."""
    if a_all is None or not len(a_all) or not spot:
        return ""
    tot = float((a_all["al_buy"] + a_all["al_sell"]).sum())
    read = float((a_all["slx_buy"] + a_all["slx_sell"]).sum()) if "slx_buy" in a_all else tot
    aside = max(tot - read, 0.0)
    return (f"noise filter · read ${read * spot / 1e9:,.2f}B Δ · set aside ${aside * spot / 1e9:,.2f}B "
            f"({aside / tot:.0%} — spread legs + mid prints)" if tot > 0 else "")

def extremes_caption(sc, ndays):
    def one(k):
        n, r, a = sc[k]
        return f"{k} {n} events · {r:.0%} right · {a:+.1f} pts" if n else f"{k} — no events yet"
    col = {"FADE": "#ffd400", "FOLLOW": "#26c6da"}.get(sc["verdict"], "#8b949e")
    return (f"**At the day's highs / lows lately → <span style='color:{col}'>{sc['verdict']}</span>** · last 15 finished "
            f"events of each kind ({ndays} saved days + today), SPX 30 min later · {one('fade')} · {one('follow')} · "
            "fade = money leaning against the new high/low · follow = money pushing through it · neither working → sit out")


def add_extremes(fig, ev_t, view, a, last=None, rowcol=None):
    if ev_t is None or not len(ev_t):
        return
    kw = rowcol or {}
    t = pd.Series(pd.to_datetime(ev_t["t"]).values)
    x = t.values if view == "candles" else _fp_x(t, a, "15min", last)
    up = ev_t["dir"].values > 0
    res = ["open" if not np.isfinite(p) else f"{p:+.1f} pts" for p in ev_t["pts"].values]
    txt = [("FADE" if k == "fade" else "FOLLOW") for k in ev_t["kind"].values]
    fig.add_scatter(x=x, y=ev_t["px"].values, mode="markers+text", text=txt,
                    textposition=["bottom center" if u else "top center" for u in up],
                    textfont=dict(size=10, color="#e6edf3"), showlegend=False,
                    customdata=np.stack([ev_t["side"].values, np.round(ev_t["lean"].values, 3), res], axis=1),
                    marker=dict(symbol=np.where(up, "triangle-up", "triangle-down"), size=13,
                                color=np.where(ev_t["kind"].values == "fade", "#ffd400", "#26c6da"),
                                line=dict(color="#0b0f14", width=1)),
                    hovertemplate="new %{customdata[0]} · lean %{customdata[1]} · %{text} · 30 min: %{customdata[2]}"
                                  "<extra></extra>", **kw)

def render(rec):
    rec = getattr(rec, "_rec", rec)
    st.caption("OrderFlow — options delta at the SPX price where it traded (OFL Delta Map idea with options delta): "
               "customer Δ = aggressor × option delta × size × 100 · blue = deltas bought (calls bought / puts sold) · "
               "magenta = deltas sold · 0DTE · RTH. 18 Nov check: tracks the bar's move (single-leg a bit tighter than "
               "all prints), does NOT predict the next bar — read it for divergences / exhaustion at turns.")
    c1, c2, c5, c4, c3 = st.columns([1.5, 1.4, 1.5, 1.4, 3])
    view = c1.segmented_control("view", ["candles", "footprint"], default="candles", key="of_view",
                                label_visibility="collapsed") or "candles"
    legs = c2.segmented_control("prints", ["single-leg", "all"], default="single-leg", key="of_legs",
                                label_visibility="collapsed") or "single-leg"
    mid = c5.segmented_control("mid prints", ["keep mid", "drop mid"], default="drop mid", key="of_mid",
                               label_visibility="collapsed",
                               help="default drop mid (as the 'zero' write-up). drop mid = ignore prints traded inside the bid/ask (two sides meeting halfway); applies "
                                    "to the map, footprint and unusual options") or "keep mid"
    drop_mid = mid != "keep mid"
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
    prm["drop_mid"] = drop_mid
    day = pd.Timestamp(now_et().date())
    sel = None
    tsel = (st.session_state.get("of_tab") or {}).get("selection", {}).get("rows", []) if on else []
    prev = st.session_state.get("_of_tab_rows")
    if tsel and prev is not None and tsel[0] < len(prev):
        r = prev.iloc[tsel[0]]
        sel = (r["mkt"], int(r["_ts"]), float(r["_S"]))
    tabs = []
    xt = None
    if st.toggle("fade / follow at highs & lows", key="of_xt", value=True,
                 help="v0.42.0 (from the 'zero' write-up): at each new session high / low after 10:00, did the last 15 min "
                      "of single-leg 0DTE money lean AGAINST it (→ fade) or push THROUGH it (→ follow)? Scored on the last "
                      "15 finished events of each kind from the saved days + today, SPX 30 min later. Neither working → "
                      "SIT OUT. Collecting — tune once ~20 days are in."):
        flt = st.segmented_control("fade/follow filter", ["session flow agrees", "all events"],
                                   default="session flow agrees", key="of_xt_flt", label_visibility="collapsed",
                                   help="session flow agrees = only take an event when the day's money since 09:30 points "
                                        "the same way as the trade (zero's SES driver). 5–23 Nov: follow 61 % right, "
                                        "+4.4 pts, 1.8 a day vs 56 % / +2.4 / 3.6 a day for all events.") or "session flow agrees"
        try:
            xt = extremes_panel(rec, sess=flt == "session flow agrees")
            st.markdown(extremes_caption(xt[0], xt[2]), unsafe_allow_html=True)
            lg = xt[3]
            if len(lg):
                show = lg.assign(time=pd.to_datetime(lg["t"]).dt.strftime("%H:%M"),
                                 result=[("open " if o else "") + (f"{p:+.0%}" if p == p else "—")
                                         for o, p in zip(lg["open"], lg["pct"])],
                                 spx=[("open" if o else f"{x:+.1f}") for o, x in zip(lg["open"], lg["spx_pts"])])
                st.dataframe(show[["time", "kind", "trade", "contract", "entry", "exit", "result", "spx"]], hide_index=True,
                             width="stretch", key="of_xt_log",
                             column_config={"entry": st.column_config.NumberColumn("entry (ask)", format="%.2f"),
                                            "exit": st.column_config.NumberColumn("exit (bid, 30 min)", format="%.2f"),
                                            "spx": st.column_config.TextColumn("SPX pts 30 min")})
                st.caption("call log — paper trades on live quotes: 1DTE one strike in the money, bought at the ask, "
                           "sold at the bid 30 min later (zero's method). Saved to the state branch after 16:00.")
        except Exception as e:                           # noqa: BLE001
            st.caption(f"fade / follow: {type(e).__name__}: {e}")
    for m in (["SPX", "ES", "SPY"] if mkt == "3 stacked" else [mkt]):
        if m == "SPX":
            a, b = _frame(rec, str(exps[0]), legs, drop_mid)
            row, lbl = OF.ROW, str(exps[0])
        else:
            a, b = _xframe(rec, m, legs, drop_mid)
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
                xe = str(exps[0]) if m == "SPX" else (getattr(rec, "xinfo", {}) or {}).get(m, {}).get("exp", "")
                g, bu = UN.result(rec, m, str(exps[0]), day, legs, on, prm, x_exp=xe)
                if len(g):
                    tabs.append(UN.table(g, on, m, tb["n"], tb["sort"], tb["min_flags"]))
                    cnt = " · unusual: " + " · ".join(
                        f"{LBL[k]} {(len(bu) if k == 'burst' else int(g[k].sum())):,}" for k in on)
            except Exception as e:                       # noqa: BLE001
                st.caption(f"unusual: {type(e).__name__}: {e}")
        if m == "SPX":
            try:
                nb = noise_box(OF.minutes(rec, str(exps[0])), float(b["c"].iloc[-1]))
                if nb:
                    st.caption(nb)
            except Exception:                            # noqa: BLE001
                pass
        st.caption(f"{lbl} · {len(a):,} minute × row cells · bought {a['buy'].sum() / 1e6:,.2f}M Δ · "
                   f"sold {a['sell'].sum() / 1e6:,.2f}M Δ · net {(a['buy'].sum() - a['sell'].sum()) / 1e6:+,.2f}M{cnt}")
        h = 560 if mkt == "3 stacked" else 820
        fig = delta_map(a, b, legs, row=row, name=m, height=h) if view == "candles" else \
            footprint(a, b, legs, last=last, row=row, name=m)
        if on and g is not None:
            add_marks(fig, g, bu, on, view, a, last=last, sel=sel[1:] if sel and sel[0] == m else None,
                      rowcol=dict(row=1, col=1) if view == "candles" else None)
        if m == "SPX" and xt is not None:
            add_extremes(fig, xt[1], view, a, last=last, rowcol=dict(row=1, col=1) if view == "candles" else None)
        st.plotly_chart(fig, width="stretch", key=f"of_{view}_{m}")
    if on:
        t = pd.concat([x for x in tabs if len(x)], ignore_index=True) if any(len(x) for x in tabs) else pd.DataFrame()
        if len(t):
            if len(tabs) > 1:
                t = t.sort_values({"delta $": "delta $M", "premium": "premium $", "size": "size", "time": "_ts"}[tb["sort"]],
                                  ascending=False).head(tb["n"]).reset_index(drop=True)
            st.session_state["_of_tab_rows"] = t
            st.dataframe(t.drop(columns=["_ts", "_S"]), hide_index=True, width="stretch", key="of_tab",
                         on_select="rerun", selection_mode="single-row",
                         column_config={"premium $": st.column_config.NumberColumn(format="$%d"),
                                        "strike": st.column_config.NumberColumn(format="%.0f")})
        else:
            st.caption("no unusual trades for the switched-on flags yet")
