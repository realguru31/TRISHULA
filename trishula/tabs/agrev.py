"""AG-REV v0 — live classified tape.

Doubles as the RTH diagnostic for gates G1-G3: are prints arriving with a
quote attached, how often is aggressorSide populated, what share is
spread-leg. Signals (Q1-Q5, W, B) and the 3D panels arrive per APPROVE.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.classify import NAMES
from core.signs import coverage_text
from core.timeutil import ET

BG = "#000000"


def render(rec):
    @st.fragment(run_every=15)
    def _tab():
        exps = rec.status()["expiries"]
        if not exps:
            st.info(f"Recorder: {rec.status()['state']} — waiting for the chain (refreshes every 15 s).")
            return
        c1, c2 = st.columns([1, 1])
        exp = c1.selectbox("Expiry", exps, key="agrev_exp")
        legs = c2.radio("Legs", ["Single", "All", "Multi"], horizontal=True, key="agrev_legs")
        _live(rec, exp, legs)

    _tab()


def _live(rec, exp, legs):
    df = rec.prints_df(exp)
    if df.empty:
        st.info("No prints recorded yet for this expiry (market closed, or waiting for the first trade).")
        return
    if legs == "Single":
        df = df[~df["spread_leg"]]
    elif legs == "Multi":
        df = df[df["spread_leg"]]
    all_df = rec.prints_df(exp)

    n = len(all_df)
    m = st.columns(6)
    m[0].metric("Prints", f"{n:,}")
    m[1].metric("Quote on print", f"{(all_df['quote_src'] == 0).mean():.0%}")
    m[2].metric("aggressorSide set", f"{all_df['aggr_side'].isin(['BUY', 'SELL']).mean():.0%}")
    m[3].metric("Spread-leg share", f"{all_df['spread_leg'].mean():.0%}")
    m[4].metric("Unclassified", f"{(all_df['bucket'] == 9).mean():.0%}")
    prem = (df["aggr"] * df["size"] * df["px"] * 100 * df["cp"]).sum()
    m[5].metric("Net bullish premium", f"${prem/1e6:+,.1f}M")

    st.caption(coverage_text(rec.dsign_table(exp)) + " · MID prints signed by aggressorSide")

    d = df.sort_values("ts_ms").copy()
    d["t"] = pd.to_datetime(d["ts_ms"], unit="ms", utc=True).dt.tz_convert(ET)
    d["bull"] = d["aggr"] * d["size"] * d["px"] * 100 * d["cp"]
    d["cum_bull"] = d["bull"].cumsum() / 1e6
    f = go.Figure()
    f.add_scatter(x=d["t"], y=d["cum_bull"], mode="lines", line=dict(color="#2ecc71", width=1.5),
                  fill="tozeroy", name="cum bullish premium")
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=320,
                    margin=dict(l=10, r=10, t=30, b=10), yaxis_title="$M",
                    title=dict(text=f"Cumulative bullish premium · {legs.lower()} legs", font=dict(size=13)))
    st.plotly_chart(f, width="stretch")

    # CVD (contracts): seed (replayed) + live, split marker where live recording starts
    d["cvd"] = (np.sign(d["aggr"]) * d["size"]).cumsum()
    g = go.Figure()
    for src, col in (("replay", "#8b949e"), ("live", "#58a6ff")):
        m = d["src"] == src if "src" in d else (d.index == d.index)
        if m.any():
            g.add_scatter(x=d.loc[m, "t"], y=d.loc[m, "cvd"], mode="lines", name=src,
                          line=dict(color=col, width=1.4))
    g.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=260,
                    margin=dict(l=10, r=10, t=30, b=10), yaxis_title="contracts",
                    legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
                    title=dict(text=f"CVD · seed (grey, replayed) + live (blue) · {legs.lower()} legs",
                               font=dict(size=13)))
    st.plotly_chart(g, width="stretch")

    a, b = st.columns([1, 2])
    bc = df["bucket"].map(NAMES).value_counts().rename_axis("bucket").reset_index(name="prints")
    a.dataframe(bc, hide_index=True, width="stretch")
    show = d.tail(200).iloc[::-1][["t", "strike", "cp", "px", "size", "bid", "ask", "bucket",
                                   "aggr_side", "spread_leg", "eth", "delta"]].copy()
    show["t"] = show["t"].dt.strftime("%H:%M:%S")
    show["cp"] = show["cp"].map({1: "C", -1: "P"})
    show["bucket"] = show["bucket"].map(NAMES)
    b.dataframe(show, hide_index=True, width="stretch", height=360)

