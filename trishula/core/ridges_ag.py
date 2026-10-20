"""AG-style ridges (v0.12 prototype): quiet ridges + spikes as their own marks + a contract pane.

Design (from the AG reference, 20 Oct 7675P):
  · ridge height = minute volume / chain p99 (window), lightly smoothed and capped, so routine
    activity sits near the floor; every ridge stays inside the box
  · a flagged spike is its OWN element: a tall vertical line whose height ∝ how unusual it was;
    the top-N by premium are bold red, the rest faint
  · the pinned contract's ridge is red; under the 3-D view a contract pane shows its option price
    (step line, spike minutes magenta, session-low dashed) and per-minute volume bars
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BG = "#0d1530"
RIDGE = [[0.0, "#1b6f8f"], [0.5, "#38bdf8"], [1.0, "#a5f3fc"]]
SPIKE = "#ff2d2d"
QUIET = 0.14          # ridge amplitude as a share of the box height


def _lab(k, cp):
    return f"{k:,.0f}{'C' if cp == 1 else 'P'}"


def volume_matrix(mt: pd.DataFrame, idx: pd.DatetimeIndex, side: str) -> pd.DataFrame:
    """minutes × strike (C, P or C+P summed)."""
    m = mt if side == "C+P" else mt[mt["cp"] == (1 if side == "C" else -1)]
    V = m.pivot_table(index="m", columns="strike", values="size", aggfunc="sum")
    return V.reindex(idx).fillna(0.0)


def rank_spikes(spk: pd.DataFrame, top: int) -> pd.DataFrame:
    if spk is None or spk.empty:
        return spk
    s = spk.copy()
    s["score"] = s["prem"] * np.clip(s["z"].fillna(4.0), 1.0, 10.0)
    s["bold"] = s["score"].rank(ascending=False, method="first") <= top
    s["ht"] = 0.30 + 0.62 * np.sqrt(s["score"] / s["score"].max())        # tallest = strongest (premium × z)
    return s


def figure(mt, spk, bars, t0, t1, strikes, pin=None, side="C+P", top=3, contract=None, h=860,
           eye=(0.35, -1.5, 1.15), title=""):
    idx = pd.date_range(t0, t1, freq="1min")
    V = volume_matrix(mt[(mt["m"] >= t0) & (mt["m"] <= t1)], idx, side)
    ks = [k for k in strikes if k in V.columns]
    if not ks:
        f = go.Figure()
        f.add_annotation(text="no prints in this window yet", x=0.5, y=0.5, xref="paper", yref="paper",
                         showarrow=False, font=dict(color="#6e7681"))
        f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=420,
                        title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01))
        return f
    V = V[ks]
    sides = {"C": [1], "P": [-1]}.get(side, [1, -1])
    sm = V.rolling(3, center=True, min_periods=1).mean()
    q = float(np.nanpercentile(V.values[V.values > 0], 99)) if (V.values > 0).any() else 1.0
    Hq = (sm / q).clip(upper=1.0) * QUIET
    has_pane = contract is not None
    f = make_subplots(rows=3 if has_pane else 1, cols=1, specs=[[{"type": "scene"}]] + ([[{}], [{}]] if has_pane else []),
                      row_heights=[0.60, 0.27, 0.13] if has_pane else [1.0], vertical_spacing=0.035,
                      shared_xaxes=False)
    # quiet ridges
    for k in ks:
        z = Hq[k].values
        f.add_scatter3d(x=idx, y=[k] * len(idx), z=z, mode="lines", row=1, col=1,
                        line=dict(width=3, color=np.clip(z / QUIET, 0, 1), colorscale=RIDGE, cmin=0, cmax=1),
                        hovertemplate=f"{k:,.0f}<br>%{{x|%H:%M}}<extra></extra>", showlegend=False)
    # pinned contract ridge (its own volume) in red
    if pin is not None:
        pk, pcp = pin
        pv = mt[(mt["strike"] == pk) & (mt["cp"] == pcp)].set_index("m")["size"].groupby(level=0).sum().reindex(idx).fillna(0)
        pz = (pv.rolling(3, center=True, min_periods=1).mean() / q).clip(upper=1.0) * QUIET
        f.add_scatter3d(x=idx, y=[pk] * len(idx), z=pz.values, mode="lines", row=1, col=1,
                        line=dict(width=6, color=SPIKE), hoverinfo="skip", showlegend=False)
    # spikes as their own marks
    s = (rank_spikes(spk[(spk["m"] >= t0) & (spk["m"] <= t1) & spk["strike"].isin(ks) & spk["cp"].isin(sides)], top)
         if spk is not None and len(spk) else None)
    if s is not None and len(s):
        for _, r in s.sort_values("bold").iterrows():
            zt = float(r["ht"])
            bold = bool(r["bold"]) or (pin is not None and (r["strike"], r["cp"]) == pin)
            col = SPIKE if bold else "rgba(255,90,90,0.35)"
            f.add_scatter3d(x=[r["m"], r["m"]], y=[r["strike"]] * 2, z=[0, zt], mode="lines", row=1, col=1,
                            line=dict(width=9 if bold else 3, color=col), showlegend=False,
                            hovertemplate=(f"{_lab(r['strike'], r['cp'])} {r['m']:%H:%M} · {r['size']:,.0f}c "
                                           f"{r['side']} · ${r['prem']/1e3:,.0f}k · z{r['z']:.1f}<extra></extra>"))
        # one label per bold minute (same-minute legs share it: packages / ladders)
        for m_, g in s[s["bold"] | ((s["strike"] == (pin or (None, None))[0]) & (s["cp"] == (pin or (None, None))[1]))].groupby("m"):
            g = g.sort_values("prem", ascending=False)
            r = g.iloc[0]
            zt = float(g["ht"].max())
            legs = " + ".join(_lab(k, cp) for k, cp in zip(g["strike"], g["cp"]))
            f.add_scatter3d(x=[m_], y=[r["strike"]], z=[zt + 0.06], mode="text", row=1, col=1,
                            text=[f"{legs} {m_:%H:%M} · {int(g['size'].sum())}c {r['side'][0]} · ${g['prem'].sum()/1e3:,.0f}k"],
                            textfont=dict(color="#ffd7d7", size=11), hoverinfo="skip", showlegend=False)
    # price path on the floor
    if bars is not None and len(bars):
        b = bars[(bars["t"] >= t0) & (bars["t"] <= t1)]
        f.add_scatter3d(x=b["t"], y=b["c"].astype(float), z=np.zeros(len(b)) + 0.002, mode="lines", row=1, col=1,
                        line=dict(color="white", width=4), hoverinfo="skip", showlegend=False)
    ax = dict(gridcolor="#24305a", backgroundcolor=BG, showbackground=True, color="#8b9bc4", zeroline=False)
    f.update_scenes(xaxis=dict(title="", tickformat="%H:%M", **ax), yaxis=dict(title="", range=[min(ks) - 2, max(ks) + 2], **ax),
                    zaxis=dict(title="", range=[0, 1.05], showticklabels=False, **ax),
                    aspectmode="manual", aspectratio=dict(x=1.6, y=1.5, z=0.45),
                    camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]), up=dict(x=0, y=0, z=1)))
    # contract pane
    if has_pane:
        c = contract
        px = c["px"]
        f.add_scatter(x=px.index, y=px.values, mode="lines", line=dict(color="#7cc4ff", width=1.4, shape="hv"),
                      row=2, col=1, showlegend=False, hovertemplate="%{x|%H:%M} $%{y:.2f}<extra></extra>")
        if len(c.get("hot", [])):
            for t in c["hot"]:
                seg = px[(px.index >= t - pd.Timedelta(minutes=8)) & (px.index <= t + pd.Timedelta(minutes=8))]
                f.add_scatter(x=seg.index, y=seg.values, mode="lines", line=dict(color="#ff2fd6", width=2.4, shape="hv"),
                              row=2, col=1, showlegend=False, hoverinfo="skip")
        lo_, hi_ = float(px.min()), float(px.max())
        span = max(hi_ - lo_, 0.05)
        top_ = hi_ + 0.10 * span
        for t, txt in c.get("marks", []):
            f.add_scatter(x=[t, t], y=[lo_, top_], mode="lines", row=2, col=1, showlegend=False,
                          line=dict(color=SPIKE, dash="dot", width=1), hoverinfo="skip")
            f.add_annotation(x=t, y=top_, text=txt, showarrow=False, xanchor="left", xshift=3, yanchor="top",
                             row=2, col=1, font=dict(color="#ffb4b4", size=11), bgcolor="rgba(13,21,48,0.75)")
        f.update_yaxes(range=[lo_ - 0.06 * span, hi_ + 0.14 * span], row=2, col=1)
        lo = float(px.min())
        f.add_scatter(x=[t0, t1], y=[lo, lo], mode="lines+text", text=["", f"low ${lo:.2f}"], textposition="bottom left",
                      textfont=dict(color="#c9d1d9", size=11), line=dict(color="#c9d1d9", dash="dash", width=1),
                      row=2, col=1, showlegend=False, hoverinfo="skip")
        f.add_bar(x=c["vol"].index, y=c["vol"].values, marker_color="#38bdf8", row=3, col=1, showlegend=False,
                  hovertemplate="%{x|%H:%M} %{y:,.0f}c<extra></extra>")
        for r in (2, 3):
            f.update_xaxes(range=[t0, t1], gridcolor="#1c2547", tickformat="%H:%M", row=r, col=1, showticklabels=(r == 3))
            f.update_yaxes(gridcolor="#1c2547", side="right", row=r, col=1)
        ytop = float(f.layout.yaxis.domain[1]) if f.layout.yaxis.domain else 0.4
        f.add_annotation(text=c["header"], xref="paper", yref="paper", x=0.01, y=ytop + 0.004, showarrow=False,
                         font=dict(color="#7ee787", size=14, family="monospace"), xanchor="left", yanchor="bottom")
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h, bargap=0.1,
                    margin=dict(l=6, r=6, t=34, b=6), title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01))
    return f
