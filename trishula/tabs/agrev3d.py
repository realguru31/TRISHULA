"""AG-REV interactive 3-D views (Plotly, rotatable), modelled on the reference shots:
  · RIDGES — one line per strike, height = contracts per minute (capped), colour low→high,
    white SPX path, spike contracts (core/spikes.py) bright orange/red with a ring at each
    spike, everything else dimmed; one contract can be pinned (the 7645P example).
    Toolbar: C / P / both · 3-D / 2-D · trim · heat · cap.
  · SURFACE — cumulative dealer γ from flow per strike × minute as a 3-D surface with the
    white spot path on top and the decay projection to the right of now.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import session as S
from core import spikes as SP

BG = "#0b1020"
HEAT = [[0.0, "#1e3a8a"], [0.35, "#22d3ee"], [0.7, "#facc15"], [1.0, "#fb923c"]]
DIM = "rgba(56,189,248,0.35)"


def toolbar():
    ss = st.session_state
    c = st.columns([1.1, 0.9, 0.7, 0.7, 2.2, 1.6])
    c[0].segmented_control("side", ["C", "P", "C+P"], default="C+P", key="r3_side", label_visibility="collapsed")
    c[1].segmented_control("view", ["3D", "2D"], default="3D", key="r3_view", label_visibility="collapsed")
    c[2].toggle("trim", value=True, key="r3_trim", help="hide strikes that never traded more than 10 % of the cap")
    c[3].toggle("heat", value=True, key="r3_heat", help="colour lines by intensity (low → high)")
    c[4].select_slider("cap", options=[250, 500, 1000, 2000, 4000, 6000, 8000, 10000], value=4000, key="r3_cap",
                       format_func=lambda v: f"cap {v / 1000:g}kc" if v >= 1000 else f"cap {v}c",
                       label_visibility="collapsed", help="contracts per minute at full line height")
    with c[5].popover("⚡ spike filter"):
        st.slider("own-history z ≥", 1.5, 6.0, SP.DEFAULTS["zthr"], 0.5, key="sp_zthr")
        st.slider("top % of all contracts that minute", 1.0, 20.0, SP.DEFAULTS["top_pct"], 1.0, key="sp_top")
        st.number_input("min contracts / minute", 1, 5000, SP.DEFAULTS["min_size"], 10, key="sp_min")
        st.number_input("min premium $ / minute", 0, 5_000_000, int(SP.DEFAULTS["min_prem"]), 5_000, key="sp_prem")
        st.slider("baseline window (min)", 15, 240, SP.DEFAULTS["win"], 15, key="sp_win")
        st.slider("warm-up (min) before own-history counts", 5, 60, SP.DEFAULTS["min_hist"], 5, key="sp_hist")
        st.caption("A minute is a spike when it is unusual for THAT contract (robust z on its own trailing "
                   "history, GTH and RTH baselines separate) AND big for the whole chain that minute AND above the "
                   "size floor. Until a contract has warm-up history, only the cross-section + floor rules fire.")
    cfg = dict(zthr=ss.get("sp_zthr", SP.DEFAULTS["zthr"]), top_pct=ss.get("sp_top", SP.DEFAULTS["top_pct"]),
               min_size=ss.get("sp_min", SP.DEFAULTS["min_size"]), min_prem=ss.get("sp_prem", SP.DEFAULTS["min_prem"]),
               win=ss.get("sp_win", SP.DEFAULTS["win"]), min_hist=ss.get("sp_hist", SP.DEFAULTS["min_hist"]))
    return dict(side=ss.get("r3_side") or "C+P", view=ss.get("r3_view") or "3D", trim=ss.get("r3_trim", True),
                heat=ss.get("r3_heat", True), cap=int(ss.get("r3_cap", 4000)), spike=cfg)


def spikes_for(rec, p, day, exp, cfg):
    key = ("spk", exp, str(day), len(p), S.gth(), getattr(rec, "ts_ms", None), tuple(sorted(cfg.items())))
    cache = rec.ui_state.setdefault("_spikes", {})
    if key in cache:
        return cache[key]
    mt = SP.minute_table(p)
    res = SP.detect(mt, day, cfg) + (mt,)
    while len(cache) >= 6:
        cache.pop(next(iter(cache)))
    cache[key] = res
    return res


def _label(strike, cp):
    return f"{strike:,.0f}{'C' if cp == 1 else 'P'}"


def ridges(mt, spk, bars, spot, ridge_each, tb, pin, day, h=620):
    sides = {"C": [1], "P": [-1]}.get(tb["side"], [1, -1])
    title = (f"RIDGES · contracts/min per strike · cap {tb['cap']:,} · ⚡ {len(spk)} spikes"
             + (f" · pinned {pin}" if pin else ""))
    f = go.Figure()
    if mt is None or mt.empty or not spot == spot:
        f.add_annotation(text="no prints for this session yet", x=0.5, y=0.5, xref="paper", yref="paper",
                         showarrow=False, font=dict(color="#6e7681"))
        return _style(f, title, h, three=False)
    m = mt[mt["cp"].isin(sides) & ((mt["strike"] - spot).abs() <= ridge_each * 5.0)]
    if m.empty:
        return _style(f, title, h, three=tb["view"] == "3D")
    idx = pd.date_range(S.open_dt(day), m["m"].max(), freq="1min")
    spk_syms = set(spk["sym"]) if len(spk) else set()
    cap = float(tb["cap"])
    three = tb["view"] == "3D"
    spacing = 5.0
    peak_all = float(m.groupby("sym")["size"].max().max() or 1.0)
    cnorm = min(cap, peak_all)                     # colour spans the busiest visible minute (≤ cap)
    for (sym, k, cp), g in m.groupby(["sym", "strike", "cp"]):
        lab = _label(k, cp)
        v = g.set_index("m")["size"].reindex(idx, fill_value=0.0).clip(upper=cap)
        if tb["trim"] and v.max() < 0.10 * min(cap, peak_all) and sym not in spk_syms and lab != pin:
            continue
        y0 = float(k) + (0.0 if len(sides) == 1 else (0.9 if cp == 1 else -0.9))
        pinned = lab == pin
        hot = sym in spk_syms
        if pinned:                                 # pinned contract: whole line orange (7645P example)
            col, width = "#ff9100", 7
        elif tb["heat"]:                           # heat colouring; spike contracts a touch thicker,
            col, width = None, (4 if hot else 3)   # the spike itself is ringed
        else:
            col, width = ("#ff3d00" if hot else DIM), (4 if hot else 2)
        name = f"{lab}{' ⚡' if hot else ''}"
        if three:
            line = dict(width=width, color=col) if col else dict(width=width, color=(v / cnorm).clip(upper=1).values,
                                                                  colorscale=HEAT, cmin=0, cmax=1)
            f.add_scatter3d(x=v.index, y=[y0] * len(v), z=v.values, mode="lines", line=line, name=name,
                            hovertemplate=f"{lab}<br>%{{x|%H:%M}} · %{{z:,.0f}} c<extra></extra>", showlegend=False)
        else:
            yy = y0 + v.values / cap * spacing * 3.0
            if col:
                f.add_scatter(x=v.index, y=yy, mode="lines", line=dict(width=width / 2, color=col), name=name,
                              customdata=v.values, hovertemplate=f"{lab}<br>%{{x|%H:%M}} · %{{customdata:,.0f}} c<extra></extra>",
                              showlegend=False)
            else:
                f.add_scatter(x=v.index, y=yy, mode="markers+lines", line=dict(width=1, color="rgba(56,189,248,0.5)"),
                              marker=dict(size=2, color=(v / cnorm).clip(upper=1).values, colorscale=HEAT, cmin=0, cmax=1),
                              customdata=v.values, hovertemplate=f"{lab}<br>%{{x|%H:%M}} · %{{customdata:,.0f}} c<extra></extra>",
                              name=name, showlegend=False)
    if len(spk):
        s = spk[spk["cp"].isin(sides) & ((spk["strike"] - spot).abs() <= ridge_each * 5.0)]
        if len(s):
            y0 = s["strike"] + (0.0 if len(sides) == 1 else np.where(s["cp"] == 1, 0.9, -0.9))
            zz = s["size"].clip(upper=cap)
            txt = [f"{_label(k, cp)} {sz:,.0f}c {sd} z{z:.1f}" if z == z else f"{_label(k, cp)} {sz:,.0f}c {sd}"
                   for k, cp, sz, sd, z in zip(s["strike"], s["cp"], s["size"], s["side"], s["z"])]
            if three:
                f.add_scatter3d(x=s["m"], y=y0, z=zz, mode="markers", marker=dict(symbol="circle-open", size=9, color="#e040fb",
                                line=dict(width=3, color="#e040fb")), text=txt, hovertemplate="%{text}<extra></extra>",
                                name="spike", showlegend=False)
            else:
                f.add_scatter(x=s["m"], y=y0 + zz / cap * spacing * 3.0, mode="markers",
                              marker=dict(symbol="circle-open", size=13, color="#e040fb", line=dict(width=2.5)),
                              text=txt, hovertemplate="%{text}<extra></extra>", name="spike", showlegend=False)
    if bars is not None and len(bars):
        if three:
            f.add_scatter3d(x=bars["t"], y=bars["c"].astype(float), z=np.zeros(len(bars)), mode="lines",
                            line=dict(color="white", width=4), name="SPX", hoverinfo="skip", showlegend=False)
        else:
            f.add_scatter(x=bars["t"], y=bars["c"].astype(float), mode="lines", line=dict(color="white", width=1.6),
                          name="SPX", hoverinfo="skip", showlegend=False)
    if not three and S.gth():
        f.add_vline(x=S.rth_open_dt(day), line_dash="dash", line_color="#8a93a6", line_width=1)
    return _style(f, title, h, three=three)


def surface(g, proj, bars, day, h=620):
    title = "SURFACE · cumulative dealer γ from flow (cyan = dealers long γ / red-orange = short) · white = spot · right of now = decay projection"
    f = go.Figure()
    if g is None or g.empty:
        f.add_annotation(text="no prints for this session yet", x=0.5, y=0.5, xref="paper", yref="paper",
                         showarrow=False, font=dict(color="#6e7681"))
        return _style(f, title, h, three=False)
    x = list(g.index)
    z = g.values.T
    if proj:
        x += [t for t, _ in proj]
        z = np.hstack([z, np.column_stack([v for _, v in proj])])
    ks = np.asarray(g.columns, float)
    f.add_surface(x=x, y=ks, z=z, cmin=-2, cmax=2, showscale=False, opacity=0.95,
                  colorscale=[[0, "#ff6d00"], [0.25, "#d50000"], [0.5, "#311b92"], [0.75, "#1e88e5"], [1, "#18ffff"]],
                  hovertemplate="%{y:,.0f} · %{x|%H:%M}<br>γ %{z:+.2f}<extra></extra>")
    if bars is not None and len(bars):
        b = bars[(bars["c"] >= ks.min()) & (bars["c"] <= ks.max())]
        f.add_scatter3d(x=b["t"], y=b["c"].astype(float), z=np.full(len(b), 2.3), mode="lines",
                        line=dict(color="white", width=5), hoverinfo="skip", showlegend=False)
    return _style(f, title, h, three=True, zlabel="dealer γ (norm)")


def spikes_table(spk):
    if spk is None or spk.empty:
        st.caption("⚡ no spikes yet with the current filter")
        return
    t = spk.iloc[::-1].copy()
    t["time"] = t["m"].dt.strftime("%H:%M")
    t["contract"] = [_label(k, cp) for k, cp in zip(t["strike"], t["cp"])]
    t["premium $"] = t["prem"].round(0)
    t["z"] = t["z"].round(1)
    st.dataframe(t[["time", "contract", "size", "premium $", "side", "z"]], hide_index=True, width="stretch", height=260)


def _style(f, title, h, three=True, zlabel="contracts / min"):
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h,
                    margin=dict(l=4, r=4, t=34, b=4), title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01),
                    showlegend=False)
    if three:
        ax = dict(gridcolor="#1f2a44", backgroundcolor=BG, showbackground=True, color="#8b949e")
        f.update_layout(scene=dict(xaxis=dict(title="", **ax), yaxis=dict(title="strike", **ax),
                                   zaxis=dict(title=zlabel, **ax), aspectmode="manual",
                                   aspectratio=dict(x=1.9, y=1.25, z=0.55),
                                   camera=dict(eye=dict(x=-0.35, y=-1.75, z=1.05))))
    else:
        f.update_xaxes(gridcolor="#1f2a44"); f.update_yaxes(gridcolor="#1f2a44")
    return f
