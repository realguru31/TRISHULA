"""AG-style ridges: quiet ridges · spikes as ridge PEAKS · direction colours · contract pane.

Design (AG reference, 20 Oct 7675P; user notes 20 Oct):
  · ridge height = minute volume vs the busiest minutes of its own segment (overnight and regular
    hours scaled separately, so the 09:30 burst does not flatten the night), 3-min smoothing, kept low
  · a spike is the ridge itself shooting up and back down at the spike minute (no separate poles);
    height ∝ strength (premium × z); the top-N per segment are bold, the rest thinner and lower
  · colour = direction: calls SOLD / puts BOUGHT = bearish red (labels light pink);
    calls BOUGHT / puts SOLD = bullish green (labels light green); mid/unknown grey
  · the pinned contract/strike ridge is amber; the contract pane shows its price (C and P when a
    strike is pinned in C+P), spike markers in the same direction colours, session low, volume bars
  · empty margin after "now" (18 % of the window, 20 min – 4 h) so the newest spikes are readable
L22 (v0.16.3, side-by-side with AG's 20 Oct 7750P chart): ridge height = CONTRACTS per minute, unsmoothed,
  on ONE linear scale for the whole window (premium / smoothing / "unusualness" z-scores all looked unlike AG) (AG's overnight reads flat next to the open); each ridge has one
  colour along its length = contracts traded at that strike in the window (AG's low → high legend).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BG = "#0d1530"
RIDGE = [[0.0, "#1b6f8f"], [0.35, "#22d3ee"], [0.6, "#a3e635"], [0.8, "#facc15"], [1.0, "#fb923c"]]   # AG: cyan → green → yellow → orange
RISE, FALL = "#ff2fd6", "#ff3b3b"     # pane: rising stretch magenta, falling stretch red (AG)
PIN = "#fbbf24"
QUIET = 0.16
RIDGE_TOP = 0.45                # the window's biggest minute reaches this height (spikes go to 0.92)
DIR = {"bear": ("#ff3b3b", "#ffb4c8"), "bull": ("#22c55e", "#b6f5c8"), "mid": ("#9ca3af", "#d1d5db")}
SER = {1: "#7cc4ff", -1: "#ffb86b"}           # pane price lines: call blue · put orange


def _rgba(hex_, a):
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _lab(k, cp):
    return f"{k:,.0f}{'C' if cp == 1 else 'P'}"


def direction(cp, side) -> str:
    s = str(side or "").upper()
    if s.startswith("B"):
        return "bull" if cp == 1 else "bear"
    if s.startswith("S"):
        return "bear" if cp == 1 else "bull"
    return "mid"


def margin(t0, t1):
    return min(max((t1 - t0) * 0.18, pd.Timedelta(minutes=20)), pd.Timedelta(hours=4))


def volume_matrix(mt: pd.DataFrame, idx: pd.DatetimeIndex, side: str, val: str = "prem") -> pd.DataFrame:
    m = mt if side == "C+P" else mt[mt["cp"] == (1 if side == "C" else -1)]
    V = m.pivot_table(index="m", columns="strike", values=val, aggfunc="sum")
    return V.reindex(idx).fillna(0.0)


W_NIGHT, W_PRE = 0.25, 0.6        # L20g: AG-style non-linear time — overnight ¼ width, the hour before the open 0.6


def tmap(t0, rth_open):
    """Minutes → x position: overnight compressed, regular hours full width (AG's axis is non-linear).
    Returns f(times) -> float array, plus tick values / labels."""
    t0 = pd.Timestamp(t0)
    ro = pd.Timestamp(rth_open) if rth_open is not None else None
    pre = ro - pd.Timedelta(minutes=60) if ro is not None else None

    def f(ts):
        t = pd.to_datetime(pd.Series(np.atleast_1d(ts)))
        m = ((t - t0).dt.total_seconds() / 60.0).values
        if ro is None or ro <= t0:
            return m
        a = max((pre - t0).total_seconds() / 60.0, 0.0)
        b = (ro - t0).total_seconds() / 60.0
        return (W_NIGHT * np.clip(m, None, a) + W_PRE * np.clip(np.clip(m, a, b) - a, 0, None)
                + np.clip(m - b, 0, None) + np.where(m < 0, 0, 0))

    def ticks(t1):
        t1 = pd.Timestamp(t1)
        out = []
        night = pd.date_range(t0.ceil("3h"), min(t1, ro or t1), freq="3h") if (ro is None or ro > t0) else []
        out += [x for x in night if ro is None or x < ro - pd.Timedelta(minutes=90)]
        if ro is not None and ro <= t1:
            step = "30min" if (t1 - max(ro, t0)) <= pd.Timedelta(hours=3) else "1h"
            out += list(pd.date_range(max(ro, t0.ceil(step)), t1, freq=step))
        elif ro is None:
            out = list(pd.date_range(t0.ceil("1h"), t1, freq="1h"))
        out = sorted(set(out))
        return list(f(out)), [f"{x:%H:%M}" for x in out]
    return f, ticks


def _seg(idx, rth_open):
    return (idx >= rth_open) if rth_open is not None else np.zeros(len(idx), bool)


def rank_spikes(spk: pd.DataFrame, top: int, rth_open=None) -> pd.DataFrame:
    if spk is None or spk.empty:
        return spk
    s = spk.copy()
    s["score"] = s["prem"] * np.clip(s["z"].fillna(4.0), 1.0, 10.0)
    s["seg"] = (s["m"] >= rth_open) if rth_open is not None else False
    s["bold"] = s.groupby("seg")["score"].rank(ascending=False, method="first") <= top     # top-N per segment
    s["ht"] = 0.30 + 0.62 * np.sqrt(s["score"] / s.groupby("seg")["score"].transform("max"))
    s["ht"] = np.where(s["bold"], s["ht"], 0.18 + 0.5 * (s["ht"] - 0.30))                  # faint = lower
    s["dir"] = [direction(cp, sd) for cp, sd in zip(s["cp"], s["side"])]
    return s


UNUSUAL_WIN, UNUSUAL_MIN = 30, 10       # L23: own-history window / warm-up (minutes)


def unusual(V: pd.DataFrame, win: int = UNUSUAL_WIN, min_hist: int = UNUSUAL_MIN) -> pd.DataFrame:
    """Robust z of each column vs its own trailing `win` minutes (median / MAD, current minute excluded), ≥ 0."""
    b = V.shift(1)
    med = b.rolling(win, min_periods=min_hist).median()
    mad = (b - med).abs().rolling(win, min_periods=min_hist).median()
    return ((V - med) / (1.4826 * mad + 1.0)).clip(lower=0).fillna(0.0)


def figure(mt, spk, bars, t0, t1, strikes, pin=None, side="C+P", top=1, contract=None, h=860,
           eye=(0.35, -1.5, 1.15), title="", rth_open=None, height="AG"):
    """height: "AG" = contracts / min on one scale · "unusual" = vs each strike's own last 30 min (L23)."""
    """pin: (strike, cp) for a contract, or (strike, 0) for a whole strike (C+P)."""
    idx = pd.date_range(t0, t1, freq="1min")
    V = volume_matrix(mt[(mt["m"] >= t0) & (mt["m"] <= t1)], idx, side, "size")     # L22: contracts / min (AG)
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
    sm = V                                                     # L22: no smoothing — AG's spikes are single minutes
    if height == "unusual":                                    # L23: baseline needs the 30 min before the window
        h0 = t0 - pd.Timedelta(minutes=UNUSUAL_WIN)
        ih = pd.date_range(h0, t1, freq="1min")
        Vh = volume_matrix(mt[(mt["m"] >= h0) & (mt["m"] <= t1)], ih, side, "size").reindex(columns=ks).fillna(0.0)
        sm = unusual(Vh).reindex(idx).fillna(0.0)
    # L20e: ONE linear scale for the window, set by its biggest (3-min smoothed) minute — like AG's $k axis.
    # A percentile cap saturated the regular session (100× the overnight premium) into a loud wall at "now";
    # on the max scale a typical RTH minute sits ~3 % high and only real bursts stand up.
    q = float(np.nanmax(sm.values)) if np.isfinite(sm.values).any() and float(np.nanmax(sm.values)) > 0 else 1.0
    Hq = (sm / q) * RIDGE_TOP
    X, XT = tmap(t0, rth_open)
    x_end_t = t1 + margin(t0, t1)
    x_end = float(X([t1])[0]) + 0.18 * float(X([t1])[0]) if float(X([t1])[0]) > 0 else 30.0
    s = (rank_spikes(spk[(spk["m"] >= t0) & (spk["m"] <= t1) & spk["strike"].isin(ks) & spk["cp"].isin(sides)], top, rth_open)
         if spk is not None and len(spk) else None)
    has_pane = bool(contract)
    f = make_subplots(rows=3 if has_pane else 1, cols=1,
                      specs=[[{"type": "scene"}]] + ([[{"secondary_y": True}], [{}]] if has_pane else []),
                      row_heights=[0.60, 0.27, 0.13] if has_pane else [1.0], vertical_spacing=0.035)
    pin_k = pin[0] if pin else None
    pin_cp = pin[1] if pin else None
    act = volume_matrix(mt[(mt["m"] >= t0) & (mt["m"] <= t1)], idx, side, "size").reindex(columns=ks).fillna(0).sum()
    act = (act / float(act.max())) ** 1.6 if float(act.max()) > 0 else act * 0      # L20: one colour per ridge (AG)
    # quiet ridges
    xi, hh = X(idx), [f"{t:%H:%M}" for t in idx]
    for k in ks:
        z = Hq[k].values
        heat = np.full(len(z), float(np.clip(act[k], 0, 1)))
        col_ = PIN if (pin_k == k and (pin_cp == 0 or side != "C+P")) else None
        f.add_scatter3d(x=xi, y=[k] * len(idx), z=z, mode="lines", row=1, col=1, text=hh,
                        line=dict(width=6, color=col_) if col_ else
                        dict(width=3, color=heat, colorscale=RIDGE, cmin=0, cmax=1),
                        hovertemplate=f"{k:,.0f}<br>%{{text}}<extra></extra>", showlegend=False)
    if pin is not None and pin_cp in (1, -1) and side == "C+P":     # pinned contract inside a C+P ridge
        if height == "unusual":
            ih = pd.date_range(t0 - pd.Timedelta(minutes=UNUSUAL_WIN), t1, freq="1min")
            pv = mt[(mt["strike"] == pin_k) & (mt["cp"] == pin_cp)].set_index("m")["size"].groupby(level=0).sum().reindex(ih).fillna(0)
            pv = unusual(pv.to_frame())[pv.name].reindex(idx).fillna(0)
        else:
            pv = mt[(mt["strike"] == pin_k) & (mt["cp"] == pin_cp)].set_index("m")["size"].groupby(level=0).sum().reindex(idx).fillna(0)
        pz = (pv / q).clip(upper=1.0) * RIDGE_TOP
        f.add_scatter3d(x=xi, y=[pin_k] * len(idx), z=np.maximum(pz.values, 0.004), mode="lines", row=1, col=1,
                        line=dict(width=6, color=PIN), hoverinfo="skip", showlegend=False)
    # L12: spikes as ridge peaks (up and back down within ±1 min), direction colour
    if s is not None and len(s):
        one = pd.Timedelta(minutes=1)
        # L20f: only the top-N spikes (and the pinned strike's) are drawn — the rest stay in the table / strip;
        # 89 faint peaks packed into the newest RTH hours made "now" unreadable
        keep = s["bold"] | ((s["strike"] == pin_k) & s["cp"].isin([pin_cp] if pin_cp in (1, -1) else [1, -1]))
        for _, r in s[keep].sort_values("bold").iterrows():
            k, m = float(r["strike"]), r["m"]
            base = float(Hq[k].get(m, 0.0)) if k in Hq else 0.0
            b0 = float(Hq[k].get(m - one, base)); b1 = float(Hq[k].get(m + one, base))
            bold = bool(r["bold"]) or (pin_k == k and (pin_cp in (0, r["cp"])))
            line_c = DIR[r["dir"]][0] if bold else _rgba(DIR[r["dir"]][0], 0.55)
            f.add_scatter3d(x=X([m - one, m, m + one]), y=[k] * 3, z=[b0, float(r["ht"]), b1], mode="lines", row=1, col=1,
                            line=dict(width=7 if bold else 3, color=line_c), showlegend=False,
                            hovertemplate=(f"{_lab(k, r['cp'])} {m:%H:%M} · {r['size']:,.0f}c {r['side']} · "
                                           f"${r['prem'] / 1e3:,.0f}k" + (f" · z{r['z']:.1f}" if r['z'] == r['z'] else "")
                                           + "<extra></extra>"))
        # labels: one per bold minute (same-minute legs share it), stacked per contract, flipped left near the edge
        lab = s[s["bold"] | ((s["strike"] == pin_k) & s["cp"].isin([pin_cp] if pin_cp in (1, -1) else [1, -1]))]
        stack: dict = {}
        edge_x = 0.80 * float(X([t1])[0])
        # L17d: one label per strike per cluster of spikes within 3 min ("7,700P ×3 · 860c · $310k")
        for k_, g in lab.sort_values("m").groupby("strike"):
            cl = (g["m"].diff() > pd.Timedelta(minutes=3)).cumsum()
            for _, h_ in g.groupby(cl):
                r = h_.sort_values("prem", ascending=False).iloc[0]
                names = sorted({_lab(k, cp) for k, cp in zip(h_["strike"], h_["cp"])})
                nb, nr = (h_["dir"] == "bull").sum(), (h_["dir"] == "bear").sum()
                dn = "bull" if nb > nr else ("bear" if nr > nb else str(r["dir"]))
                m0, m1 = h_["m"].min(), h_["m"].max()
                tt = f"{m0:%H:%M}" if m0 == m1 else f"{m0:%H:%M}–{m1:%H:%M}"
                cnt = f" ×{len(h_)}" if len(h_) > 1 else ""
                sd = "" if len(h_) > 1 else f" {str(r['side'])[:1]}"
                key = float(k_)
                n = stack.get(key, 0); stack[key] = n + 1
                f.add_scatter3d(x=X([m1]), y=[key], z=[min(float(h_["ht"].max()) + 0.06 + 0.07 * n, 1.08)], mode="text", row=1, col=1,
                                text=[f"{'+'.join(names)}{cnt} {tt} · {int(h_['size'].sum())}c{sd} · ${h_['prem'].sum() / 1e3:,.0f}k"],
                                textposition="middle left" if float(X([m1])[0]) >= edge_x else "middle right",
                                textfont=dict(color=DIR[dn][1], size=11), hoverinfo="skip", showlegend=False)
    # price path on the floor, clipped to the ridge strike range (L11c)
    if bars is not None and len(bars):
        b = bars[(bars["t"] >= t0) & (bars["t"] <= t1)].copy()
        lo_k, hi_k = min(ks) - 2.5, max(ks) + 2.5
        y = b["c"].astype(float).where((b["c"] >= lo_k) & (b["c"] <= hi_k))
        f.add_scatter3d(x=X(b["t"]), y=y, z=np.zeros(len(b)) + 0.002, mode="lines", row=1, col=1, connectgaps=False,
                        line=dict(color="white", width=4), hoverinfo="skip", showlegend=False)
    # L20: 3-D scenes ignore a date range → an invisible point at the far end makes the right margin real
    f.add_scatter3d(x=[0.0, x_end], y=[min(ks), max(ks)], z=[0, 0], mode="markers", marker=dict(size=1, opacity=0),
                    hoverinfo="skip", showlegend=False, row=1, col=1)
    ax = dict(gridcolor="#24305a", backgroundcolor=BG, showbackground=True, color="#8b9bc4", zeroline=False)
    tv, tt = XT(t1)
    f.update_scenes(xaxis=dict(title="", range=[0.0, x_end], tickvals=tv, ticktext=tt, **ax),
                    yaxis=dict(title="", range=[min(ks) - 2, max(ks) + 2], **ax),
                    zaxis=dict(title="", range=[0, 1.12], showticklabels=False, **ax),
                    aspectmode="manual", aspectratio=dict(x=1.6, y=1.5, z=0.45),
                    camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]), up=dict(x=0, y=0, z=1)))
    if has_pane:
        _pane(f, contract, t0, x_end_t)
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h, bargap=0.1, barmode="stack",
                    margin=dict(l=6, r=6, t=34, b=6), title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01))
    return f


def swings(px: pd.Series, th: float = 0.20):
    """Zig-zag on the option price: stretches whose move from the last pivot is ≥ th (20 %) →
    [(start, end, +1 rising / −1 falling)]. AG colours these magenta / red."""
    v = px.values.astype(float)
    if len(v) < 3:
        return []
    piv, d, ext_i = [0], 0, 0
    for i in range(1, len(v)):
        if d >= 0 and v[i] >= v[ext_i] or d <= 0 and v[i] <= v[ext_i]:
            if d == 0 and i > 0:
                d = 1 if v[i] > v[piv[-1]] else (-1 if v[i] < v[piv[-1]] else 0)
            ext_i = i
        elif abs(v[i] - v[ext_i]) >= th * max(abs(v[ext_i]), 0.05):
            piv.append(ext_i); d = -d if d else (1 if v[i] > v[ext_i] else -1); ext_i = i
    piv.append(ext_i)
    out = []
    for a, b in zip(piv[:-1], piv[1:]):
        if b > a and abs(v[b] - v[a]) >= th * max(abs(v[a]), 0.05):
            out.append((px.index[a], px.index[b], 1 if v[b] > v[a] else -1))
    return out


def _pane(f, contract, t0, x_end):
    """contract: dict (one contract) or list of dicts (call + put of a pinned strike).
    One contract: AG look — blue line, rising stretches magenta, falling red.
    Call + put (L17b/c): each on its own price axis (call left, put right), lines keep their colours
    (call blue / put orange) and the rising/falling stretches are a translucent underlay."""
    cs = contract if isinstance(contract, list) else [contract]
    multi = len(cs) > 1
    for c in cs:
        px = c["px"]
        sec = multi and c.get("cp") == -1
        base_c = SER.get(c.get("cp"), "#7cc4ff") if multi else "#7cc4ff"
        lo_, hi_ = float(px.min()), float(px.max())
        span = max(hi_ - lo_, 0.05)
        top_ = hi_ + 0.10 * span
        if multi:
            for a, b, sgn in swings(px):
                seg = px[(px.index >= a) & (px.index <= b)]
                f.add_scatter(x=seg.index, y=seg.values, mode="lines", row=2, col=1, secondary_y=sec, showlegend=False,
                              line=dict(color=_rgba(RISE if sgn > 0 else FALL, 0.35), width=7, shape="hv"), hoverinfo="skip")
        f.add_scatter(x=px.index, y=px.values, mode="lines", line=dict(color=base_c, width=1.5, shape="hv"),
                      row=2, col=1, secondary_y=sec, showlegend=False,
                      hovertemplate=f"{c.get('name', '')} %{{x|%H:%M}} $%{{y:.2f}}<extra></extra>")
        if not multi:
            for a, b, sgn in swings(px):                                # L15b: AG-style rising / falling stretches
                seg = px[(px.index >= a) & (px.index <= b)]
                f.add_scatter(x=seg.index, y=seg.values, mode="lines", row=2, col=1, showlegend=False, hoverinfo="skip",
                              line=dict(color=RISE if sgn > 0 else FALL, width=2.2, shape="hv"))
        for t, txt, dn in c.get("marks", []):
            f.add_scatter(x=[t, t], y=[lo_, top_], mode="lines", row=2, col=1, secondary_y=sec, showlegend=False,
                          line=dict(color=DIR[dn][0], dash="dot", width=1), hoverinfo="skip")
            if not multi:
                f.add_annotation(x=t, y=top_, text=txt, showarrow=False, xanchor="left", xshift=3, yanchor="top",
                                 row=2, col=1, font=dict(color=DIR[dn][1], size=11), bgcolor="rgba(13,21,48,0.75)")
        f.add_scatter(x=[t0, x_end], y=[lo_, lo_], mode="lines+text", text=["", f"{c.get('name', '')} low ${lo_:.2f}"],
                      textposition="bottom left", textfont=dict(color=base_c if multi else "#c9d1d9", size=10),
                      line=dict(color=base_c if multi else "#c9d1d9", dash="dash", width=1),
                      row=2, col=1, secondary_y=sec, showlegend=False, hoverinfo="skip")
        f.update_yaxes(range=[lo_ - 0.06 * span, hi_ + 0.14 * span], row=2, col=1, secondary_y=sec,
                       tickfont=dict(color=base_c if multi else "#c9d1d9"), gridcolor="#1c2547",
                       side=("right" if sec or not multi else "left"), showgrid=not sec)
        f.add_bar(x=c["vol"].index, y=c["vol"].values, marker_color=base_c if multi else "#38bdf8", row=3, col=1,
                  showlegend=False, hovertemplate=f"{c.get('name', '')} %{{x|%H:%M}} %{{y:,.0f}}c<extra></extra>")
    for r in (2, 3):
        f.update_xaxes(range=[t0, x_end], gridcolor="#1c2547", tickformat="%H:%M", row=r, col=1, showticklabels=(r == 3))
    f.update_yaxes(gridcolor="#1c2547", side="right", row=3, col=1)
    ytop = float(f.layout.yaxis.domain[1]) if f.layout.yaxis.domain else 0.4
    hdr = "   ".join(c["header"] for c in cs)
    f.add_annotation(text=hdr, xref="paper", yref="paper", x=0.01, y=ytop + 0.004, showarrow=False,
                     font=dict(color="#7ee787", size=14, family="monospace"), xanchor="left", yanchor="bottom")
