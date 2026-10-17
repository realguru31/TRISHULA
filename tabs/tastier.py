"""TASTIER v0 — header cards, GEX by strike, cumulative net gamma.

Live from the recorder's in-memory chain (no waiting for a snapshot).
GEX per leg = s x gamma x OI x 100 x S^2 x 0.01  (USD per 1% move),
s = +1 call / -1 put (dealer convention). Remaining panels arrive per APPROVE.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

BG = "#000000"


def gex_by_strike(ch: pd.DataFrame, spot: float) -> pd.DataFrame:
    c = ch.dropna(subset=["gamma"]).copy()
    c["oi"] = c["oi"].fillna(0)
    c["gex"] = c["cp"] * c["gamma"] * c["oi"] * 100 * spot * spot * 0.01
    g = c.pivot_table(index="strike", columns="cp", values="gex", aggfunc="sum").fillna(0)
    g = g.rename(columns={1: "call", -1: "put"})
    for col in ("call", "put"):
        if col not in g:
            g[col] = 0.0
    g["net"] = g["call"] + g["put"]
    return g.sort_index().reset_index()


def gamma_flip(g: pd.DataFrame, spot: float):
    k, cum = g["strike"].values, np.cumsum(g["net"].values)
    xs = [k[i] + (k[i + 1] - k[i]) * (-cum[i]) / (cum[i + 1] - cum[i])
          for i in range(len(k) - 1) if cum[i] * cum[i + 1] < 0]
    return min(xs, key=lambda x: abs(x - spot)) if xs else None


def _layout(fig, title, h=520):
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h,
                      margin=dict(l=10, r=10, t=36, b=10), title=dict(text=title, font=dict(size=13)),
                      showlegend=False)
    return fig


def render(rec):
    @st.fragment(run_every=30)
    def _tab():
        exps = rec.status()["expiries"]
        if not exps:
            st.info(f"Recorder: {rec.status()['state']} — waiting for the chain (refreshes every 30 s).")
            return
        c1, c2 = st.columns([1, 3])
        exp = c1.selectbox("Expiry", exps, index=0, key="tastier_exp",
                           format_func=lambda e: f"{e} ({'0 DTE' if e == exps[0] else '1 DTE'})")
        rng = c2.slider("Strikes each side of spot", 10, 40, 20, key="tastier_rng")
        _live(rec, exp, rng)

    _tab()


def _live(rec, exp, rng):
    spot, ssrc = rec.spot_now()
    ch = rec.live_chain(exp)
    if ch.empty or ch["gamma"].notna().sum() == 0 or not spot == spot:
        st.warning("Waiting for greeks / OI from DXLink…")
        return
    g = gex_by_strike(ch, spot)
    flip = gamma_flip(g, spot)
    up, dn = g[g["strike"] > spot], g[g["strike"] < spot]
    cw = float(up.loc[up["call"].idxmax(), "strike"]) if len(up) else None
    pw = float(dn.loc[dn["put"].idxmin(), "strike"]) if len(dn) else None
    tot = g["net"].sum()

    m = st.columns(5)
    m[0].metric(f"SPX ({ssrc})", f"{spot:,.2f}")
    m[1].metric("Total net GEX", f"${tot/1e9:,.2f}B")
    m[2].metric("Gamma flip", f"{flip:,.1f}" if flip else "—")
    m[3].metric("Call wall", f"{cw:,.0f}" if cw else "—")
    m[4].metric("Put wall", f"{pw:,.0f}" if pw else "—")

    atm = (g["strike"] - spot).abs().idxmin()
    v = g.iloc[max(0, atm - rng): atm + rng + 1]
    a, b = st.columns(2)
    f1 = go.Figure()
    f1.add_bar(y=v["strike"], x=v["call"] / 1e9, orientation="h", marker_color="#2ecc71", name="POS (calls)")
    f1.add_bar(y=v["strike"], x=v["put"] / 1e9, orientation="h", marker_color="#e74c3c", name="NEG (puts)")
    f1.update_layout(barmode="relative", xaxis_title="$B per 1%")
    cum = np.cumsum(g["net"].values) / 1e9
    f2 = go.Figure()
    f2.add_bar(y=g["strike"], x=cum, orientation="h", marker_color="#2ecc71", opacity=0.55)
    f2.add_scatter(y=g["strike"], x=cum, mode="lines", line=dict(color="#58a6ff", width=2))
    f2.update_layout(xaxis_title="$B cumulative")
    for f in (f1, f2):
        f.add_hline(y=spot, line_dash="dash", line_color="white",
                    annotation_text=f"spot {spot:,.2f}", annotation_font_color="white")
        if flip:
            f.add_hline(y=flip, line_dash="dash", line_color="#b388ff",
                        annotation_text=f"flip {flip:,.1f}", annotation_font_color="#b388ff")
        f.update_yaxes(range=[v["strike"].min() - 5, v["strike"].max() + 5])
    a.plotly_chart(_layout(f1, "GEX by strike  · POS calls / NEG puts"), width="stretch")
    b.plotly_chart(_layout(f2, "Cumulative net gamma"), width="stretch")
    st.caption(f"{exp} · {len(ch)} legs · OI = yesterday's settled book · refresh 30 s")

