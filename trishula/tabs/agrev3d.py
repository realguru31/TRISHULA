"""AG-REV interactive 3-D views (Plotly, rotatable), modelled on the reference shots:
  · RIDGES — one line per strike, height = contracts per minute (capped), colour low→high,
    white SPX path, spike contracts (core/spikes.py) bright orange/red with a ring at each
    spike, everything else dimmed; one contract can be pinned (the 7645P example).
    Toolbar: C / P / both · 3-D / 2-D · trim · heat · cap.
  · SURFACE — cumulative dealer γ from flow per strike × minute as a 3-D surface with the
    white spot path on top and the decay projection to the right of now.
"""
from __future__ import annotations

import datetime as dt

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
    c = st.columns([1.0, 1.55, 1.6, 1.3, 1.3, 1.5, 1.4])
    c[0].segmented_control("side", ["C", "P", "C+P"], default="C+P", key="r3_side", label_visibility="collapsed")
    c[1].segmented_control("view", ["ridgeline", "3D", "map"], default="ridgeline", key="r3_view", label_visibility="collapsed",
                           help="ridgeline (default, v0.18) = flat AG-style ridges: each ridge sits AT its strike, SPX on the "
                                "same price axis, nearer ridges hide the ones behind · 3D = the 3-D ridges (AG camera) · "
                                "map = the older 2-D view")
    c[2].segmented_control("window", ["RTH", "2h", "4h", "session"], default="RTH", key="r3_win",
                           label_visibility="collapsed", help="RTH = from 09:30 (before the open: the last 4 h) · 2h / 4h = "
                                                              "the last hours · session = from 20:15 ET (overnight squeezed)")
    c[6].segmented_control("expiries", ["0+1DTE", "selected"], default="0+1DTE", key="r3_exp", label_visibility="collapsed",
                           help="0+1DTE (default, v0.18) = the selected expiry AND the next one summed per strike — AG's "
                                "ridges include tomorrow's contracts (22 Oct 7750C, 7720P) · selected = only the control-bar expiry")
    c[3].segmented_control("bold", ["top 1", "top 3", "top 5"], default="top 1", key="r3_top",
                           label_visibility="collapsed",
                           help="how many spikes are drawn bold red (ranked by premium × z); the rest stay faint")
    c[5].segmented_control("height", ["AG", "unusual"], default="AG", key="r3_height", label_visibility="collapsed",
                           help="AG = contracts per minute on one scale (AG's ridges: where the volume is) · "
                                "unusual = each strike vs its OWN last 30 min (robust z, unsmoothed): steady heavy volume "
                                "fades, only what is new for that strike stands up")
    with c[4].popover("⚡ spike filter"):
        st.toggle("single-leg tape only", value=SP.SINGLE_LEG, key="sp_single",
                  help="spreadLeg prints are packages; unflagged package legs (same minute, same size) are merged anyway")
        g, r = st.columns(2)
        g.markdown("**🌙 overnight (GTH)**")
        g.slider("own-history z ≥", 1.5, 8.0, SP.DEFAULTS["zthr"], 0.5, key="sp_zthr")
        g.slider("top % of chain", 0.5, 20.0, SP.DEFAULTS["top_pct"], 0.5, key="sp_top")
        g.number_input("min contracts / min", 1, 10000, SP.DEFAULTS["min_size"], 10, key="sp_min")
        g.number_input("min premium $ / min", 0, 10_000_000, int(SP.DEFAULTS["min_prem"]), 5_000, key="sp_prem")
        r.markdown("**☀ regular hours (RTH)**")
        r.slider("own-history z ≥ ", 1.5, 8.0, SP.RTH_DEFAULTS["zthr"], 0.5, key="sp_rzthr")
        r.slider("top % of chain ", 0.5, 20.0, SP.RTH_DEFAULTS["top_pct"], 0.5, key="sp_rtop")
        r.number_input("min contracts / min ", 1, 10000, int(SP.RTH_DEFAULTS["min_size"]), 10, key="sp_rmin")
        r.number_input("min premium $ / min ", 0, 10_000_000, int(SP.RTH_DEFAULTS["min_prem"]), 5_000, key="sp_rprem")
        st.slider("baseline window (min)", 15, 240, SP.DEFAULTS["win"], 15, key="sp_win")
        st.slider("warm-up (min) before own-history counts", 5, 60, SP.DEFAULTS["min_hist"], 5, key="sp_hist")
        st.caption("A minute is a spike when it is unusual for THAT contract (robust z on its own trailing history) "
                   "AND big for the whole chain that minute AND above the size floor. Overnight and RTH have their own "
                   "baselines and thresholds (defaults tuned on Friday's and Sunday night's real tape).")
    cfg = dict(zthr=ss.get("sp_zthr", SP.DEFAULTS["zthr"]), top_pct=ss.get("sp_top", SP.DEFAULTS["top_pct"]),
               min_size=ss.get("sp_min", SP.DEFAULTS["min_size"]), min_prem=ss.get("sp_prem", SP.DEFAULTS["min_prem"]),
               win=ss.get("sp_win", SP.DEFAULTS["win"]), min_hist=ss.get("sp_hist", SP.DEFAULTS["min_hist"]),
               single=bool(ss.get("sp_single", SP.SINGLE_LEG)),
               rth=dict(zthr=ss.get("sp_rzthr", SP.RTH_DEFAULTS["zthr"]), top_pct=ss.get("sp_rtop", SP.RTH_DEFAULTS["top_pct"]),
                        min_size=ss.get("sp_rmin", SP.RTH_DEFAULTS["min_size"]),
                        min_prem=ss.get("sp_rprem", SP.RTH_DEFAULTS["min_prem"])))
    return dict(height=ss.get("r3_height") or "AG", side=ss.get("r3_side") or "C+P", view=ss.get("r3_view") or "ridgeline",
                exp=ss.get("r3_exp") or "0+1DTE", trim=True, heat=True, cap=4000,
                win=ss.get("r3_win") or "RTH", top=int((ss.get("r3_top") or "top 1").split()[-1]), spike=cfg)


# ── AG-style ridges (v0.12): quiet ridges · spikes as marks · contract pane ──
def window_bounds(day, mt, asof_ms, win):
    import datetime as _dt
    t1 = (pd.Timestamp(asof_ms, unit="ms", tz="UTC").tz_convert("America/New_York").tz_localize(None).floor("1min")
          if asof_ms else (mt["m"].max() if len(mt) else S.close_dt(day)))
    t1 = min(pd.Timestamp(t1), pd.Timestamp(S.close_dt(day)))
    t0 = pd.Timestamp(S.open_dt(day))
    if win == "RTH":                                # v0.18: from 09:30; before the open the last 4 h
        rth = pd.Timestamp(_dt.datetime.combine(day, _dt.time(9, 30)))
        t0 = max(t0, rth if t1 >= rth + pd.Timedelta(minutes=30) else t1 - pd.Timedelta(hours=4))
    elif win != "session":
        t0 = max(t0, t1 - pd.Timedelta(hours=int(win[:-1])))
    if t1 - t0 < pd.Timedelta(minutes=30):          # early in a session: extend BACKWARD, never into the future
        t0 = t1 - pd.Timedelta(minutes=30)
    return t0, t1


def tetris_build(rec, exp, day, asof_ms, ks, bars, mt, model, palette, overlay, smooth):
    """L18: Tetris figures (3-D blocks, top-down, legend), cached on the inputs."""
    from core import tetris as TT
    if not ks or bars is None or bars.empty:
        return None
    t0 = pd.Timestamp(S.open_dt(day))
    t1 = (pd.Timestamp(asof_ms, unit="ms", tz="UTC").tz_convert("America/New_York").tz_localize(None) if asof_ms
          else pd.Timestamp(bars["t"].max()))
    t1 = min(t1, pd.Timestamp(S.close_dt(day)))
    idx = pd.date_range(t0.floor(TT.BUCKET), t1.floor(TT.BUCKET), freq=TT.BUCKET)
    if len(idx) < 3:
        return None
    key = ("tt", S.gth(), exp, str(day), idx[-1], model, palette, overlay, smooth, tuple(ks), len(mt))
    cache = rec.ui_state.setdefault("_tetris", {})
    if key in cache:
        return cache[key]
    if model == "G":
        return _tetris_g(rec, exp, day, idx, t0, t1, ks, bars, mt, palette, overlay, smooth, key, cache)
    with rec.lock:
        legs = [(sym, k, cp) for sym, (ex, k, cp) in rec.legs.items() if ex == exp and k in set(ks)]
        oi = {s_: rec.oi.get(s_, float("nan")) for s_, _, _ in legs}
        iv = {s_: (rec.greeks.get(s_) or (float("nan"),))[0] for s_, _, _ in legs}
    L = pd.DataFrame([(s_, k, cp, oi[s_], iv[s_]) for s_, k, cp in legs], columns=["sym", "strike", "cp", "oi", "iv"])
    if L.empty or not L["oi"].fillna(0).gt(0).any():
        return None
    b = bars.dropna(subset=["c"])
    Sp = b.set_index(pd.to_datetime(b["t"]))["c"].astype(float)
    Sb = Sp.groupby(Sp.index.floor(TT.BUCKET)).last().reindex(idx).ffill().bfill()
    ov = None
    if overlay.startswith("+") and mt is not None and len(mt):
        start = t0 if "20:15" in overlay else pd.Timestamp(dt.datetime.combine(day, dt.time(9, 30)))
        m = mt[(mt["m"] >= start) & (mt["m"] <= t1)]
        if len(m):
            ov = (m.assign(b=m["m"].dt.floor(TT.BUCKET)).pivot_table(index="b", columns="sym", values="size", aggfunc="sum")
                  .reindex(idx).fillna(0.0).cumsum())
    expiry = pd.Timestamp(dt.datetime.combine(dt.date.fromisoformat(exp), dt.time(16, 0)))
    M = TT.greek_field(L, Sb, expiry, model, ov)
    if M.empty:
        return None
    V = TT.per_strike_peak(M, float(smooth))
    B = TT.bands(V, palette)
    ttl = (f"TETRIS · {exp} · model {'A · OI×γ' if model == 'A' else 'E · OI×vega'} · {overlay} · "
           f"{idx[0]:%H:%M}–{idx[-1]:%H:%M} ET · each strike scaled to its own peak")
    res = (TT.figure(V, B, Sp, palette, ttl), TT.topdown(V, B, Sp, palette), TT.legend_html(palette))
    while len(cache) >= 4:
        cache.pop(next(iter(cache)))
    cache[key] = res
    return res


def _tetris_g(rec, exp, day, idx, t0, t1, ks, bars, mt, palette, overlay, smooth, key, cache):
    """v0.18 model G: price grid × γ of ALL recorded expiries up to Friday (0DTE→Fri; in practice the 0DTE and
    1DTE legs the recorder holds) weighted by OI + contracts traded (overlay), live IV from the recorded chain
    snapshots, each time column scaled to its peak (research/l25)."""
    from core import tetris as TT
    e0 = dt.date.fromisoformat(exp)
    fri = e0 + dt.timedelta(days=(4 - e0.weekday()) % 7)
    with rec.lock:
        legs = [(sym, ex, k, cp) for sym, (ex, k, cp) in rec.legs.items() if exp <= ex <= str(fri)]
        oi = {s_: rec.oi.get(s_, float("nan")) for s_, _, _, _ in legs}
        iv = {s_: (rec.greeks.get(s_) or (float("nan"),))[0] for s_, _, _, _ in legs}
    L = pd.DataFrame([(s_, ex, k, cp, oi[s_], iv[s_]) for s_, ex, k, cp in legs], columns=["sym", "exp", "strike", "cp", "oi", "iv"])
    if L.empty or not L["oi"].fillna(0).gt(0).any():
        return None
    lo, hi = min(ks) - 300, max(ks) + 300                          # gamma reaches the grid from strikes outside it
    L = L[(L["strike"] >= lo) & (L["strike"] <= hi)].reset_index(drop=True)
    b = bars.dropna(subset=["c"])
    Sp = b.set_index(pd.to_datetime(b["t"]))["c"].astype(float)
    Sb = Sp.groupby(Sp.index.floor(TT.BUCKET)).last().reindex(idx).ffill().bfill()
    ov = None
    if overlay.startswith("+") and mt is not None and len(mt):
        start = t0 if "20:15" in overlay else pd.Timestamp(dt.datetime.combine(day, dt.time(9, 30)))
        m = mt[(mt["m"] >= start) & (mt["m"] <= t1)]
        if len(m):
            ov = (m.assign(b=m["m"].dt.floor(TT.BUCKET)).pivot_table(index="b", columns="sym", values="size", aggfunc="sum",
                                                                    observed=True)
                  .reindex(idx).fillna(0.0).cumsum())
    ivp = None
    try:
        h = rec.chain_df()
        if len(h) and "iv" in h:
            h = h[h["sym"].astype(str).isin(set(L["sym"]))]
            if len(h):
                h = h.assign(b=pd.to_datetime(h["ts_ms"], unit="ms", utc=True).dt.tz_convert("America/New_York")
                             .dt.tz_localize(None).dt.floor(TT.BUCKET), sym=h["sym"].astype(str))
                ivp = h.pivot_table(index="b", columns="sym", values="iv", aggfunc="last")
    except Exception:                                              # noqa: BLE001
        ivp = None
    # research grid: ±130 pts around price (21 Oct: 7590–7850), 5-pt levels — the ridge strikes (±60) are too narrow
    # to show the warm core above / blue / purple layering
    s_lo, s_hi = float(np.nanmin(Sb.values)), float(np.nanmax(Sb.values))
    grid = list(np.arange(np.floor((min(s_lo, min(ks)) - 130) / 5) * 5, np.ceil((max(s_hi, max(ks)) + 120) / 5) * 5 + 5, 5.0))
    M = TT.price_grid_field(L, Sb, grid, ov, ivp)
    if M.empty:
        return None
    V = TT.per_time_peak(M, float(smooth))
    B = TT.bands(V, palette, TT.G_SHARE)                            # colour shares measured on AG's 21 Oct chart
    exps = sorted(L["exp"].unique())
    ttl = (f"TETRIS · G · price-grid γ · {' + '.join(pd.Timestamp(e).strftime('%d %b') for e in exps)} · {overlay} · "
           f"live IV · {idx[0]:%H:%M}–{idx[-1]:%H:%M} ET · each time column scaled to its peak")
    res = (TT.figure(V, B, Sp, palette, ttl), TT.topdown(V, B, Sp, palette), TT.legend_html(palette))
    while len(cache) >= 4:
        cache.pop(next(iter(cache)))
    cache[key] = res
    return res


def ridge_strikes(mt, spot, ctl, ridge_each, bars, t0, t1):
    """L16a: strikes follow the control bar (Strikes each side / % move), RidgeEachSide as the floor;
    L16b: and always cover the price path inside the window (the 7,670 open was below the grid)."""
    if mt is None or mt.empty or not spot == spot:
        return []
    half = ridge_each * 5.0
    if ctl:
        half = max(half, (ctl["pct"] / 100 * spot) if ctl.get("mode") == "% move" else ctl["n"] * 5.0)
    lo, hi = spot - half, spot + half
    if bars is not None and len(bars):
        b = bars[(bars["t"] >= t0) & (bars["t"] <= t1)]
        c = pd.to_numeric(b["c"], errors="coerce").dropna()
        if len(c):
            lo, hi = min(lo, float(c.min()) - 10), max(hi, float(c.max()) + 10)
    return [float(k) for k in sorted(mt["strike"].unique()) if lo <= k <= hi]


def ridgeline_strikes(mt, spot, bars, t0, t1, half=60.0, pad=15.0):
    """v0.18: ±60 pts around spot, widened to cover the price path in the window (+15)."""
    if mt is None or mt.empty or not spot == spot:
        return []
    lo, hi = spot - half, spot + half
    if bars is not None and len(bars):
        b = bars[(bars["t"] >= t0) & (bars["t"] <= t1)]
        c = pd.to_numeric(b["c"], errors="coerce").dropna()
        if len(c):
            lo, hi = min(lo, float(c.min()) - pad), max(hi, float(c.max()) + pad)
    return [float(k) for k in sorted(mt["strike"].unique()) if lo <= k <= hi]


def auto_pin(spk, t0, t1, ks, side):
    """Strongest spike in the window (premium × z) — the default pinned contract."""
    if spk is None or spk.empty:
        return None
    sides = {"C": [1], "P": [-1]}.get(side, [1, -1])
    s = spk[(spk["m"] >= t0) & (spk["m"] <= t1) & spk["strike"].isin(ks) & spk["cp"].isin(sides)]
    if s.empty:
        return None
    r = s.assign(sc=s["prem"] * np.clip(s["z"].fillna(4.0), 1, 10)).sort_values("sc").iloc[-1]
    return float(r["strike"]), int(r["cp"])


def contract_data(p, spk, pin, t0, t1, exp, greeks: dict, c1=None):
    """Price (last trade per minute, stepped), volume per minute, spike marks and header for one
    contract (cp = ±1). Returns None when it never traded."""
    from core.ridges_ag import direction
    k, cp = pin
    q = p[(p["strike"] == k) & (p["cp"] == cp)] if len(p) else p
    cc = c1[(c1["strike"] == k) & (c1["cp"] == cp)] if (c1 is not None and len(c1)) else None
    if (q is None or q.empty) and (cc is None or cc.empty):
        return None
    if q is not None and len(q):
        q = q.assign(m=q["ts"].dt.floor("1min"))
        px = q.groupby("m")["px"].last()
        vol = q.groupby("m")["size"].sum()
    else:
        px, vol = pd.Series(dtype=float), pd.Series(dtype=float)
    if cc is not None and len(cc):                              # L16d: candles cover what the replay lost
        cpx = cc.groupby("m")["close"].last()
        cvol = cc.groupby("m")["size"].sum()
        px = cpx.combine_first(px) if len(px) else cpx
        vol = cvol.combine_first(vol) if len(vol) else cvol
        px = px.sort_index(); vol = vol.sort_index()
    idx = pd.date_range(t0, t1, freq="1min")
    pre = px[px.index < t0]
    px = px.reindex(px.index.union(idx)).ffill()
    if len(pre):
        px = px.fillna(pre.iloc[-1])
    px = px.reindex(idx).dropna()
    vol = vol.reindex(idx).fillna(0.0)
    if px.empty:
        return None
    sk = spk[(spk["strike"] == k) & (spk["cp"] == cp) & (spk["m"] >= t0) & (spk["m"] <= t1)] if len(spk) else spk
    marks = [(r.m, (f"⚡ {int(r.size)}c {r.side} ${r.prem / 1e3:,.0f}k" + (f" z{r.z:.1f}" if r.z == r.z else "")),
              direction(cp, r.side)) for r in sk.itertuples()] if len(sk) else []
    sym = q["sym"].iloc[-1] if (q is not None and len(q)) else cc["sym"].iloc[-1]
    dlt = (greeks.get(sym) or (np.nan, np.nan))[1]
    d = pd.Timestamp(exp)
    name = f"{k:,.0f}{'C' if cp == 1 else 'P'}"
    hdr = (f"{d:%b %d} {k:,.0f} {'C' if cp == 1 else 'P'} ${px.iloc[-1]:.2f}"
           + (f" Δ{dlt:+.2f}" if dlt == dlt else "") + f" · vol {int(vol.sum()):,}"
           + (f" · ⚡ {len(marks)}" if marks else ""))
    return dict(px=px, vol=vol, marks=marks, header=hdr, cp=cp, name=name)


def pane_for(p, spk, pin, t0, t1, exp, greeks, side, c1=None, legs=None):
    """pin (k, ±1) → one contract; (k, 0) → the strike's call AND put (C+P mode).
    exp may be a list (0+1DTE ridges): the pane shows the expiry that traded most at the pinned strike
    in the window (its date is in the header)."""
    if pin is None:
        return None
    k, cp = pin
    if not isinstance(exp, str):
        ex = list(exp)
        if len(ex) > 1 and legs:
            vol = {}
            for e in ex:
                syms = {s_ for s_, v in legs.items() if v[0] == e and v[1] == k and (cp == 0 or v[2] == cp)}
                v1 = float(c1[c1["sym"].isin(syms) & (c1["m"] >= t0) & (c1["m"] <= t1)]["size"].sum()) if c1 is not None and len(c1) else 0.0
                v2 = float(p[p["sym"].isin(syms) & (p["ts"] >= t0) & (p["ts"] <= t1)]["size"].sum()) if len(p) else 0.0
                vol[e] = max(v1, v2)
            e = max(ex, key=lambda x: vol.get(x, 0.0))
        else:
            e = ex[0]
        if legs:
            syms = {s_ for s_, v in legs.items() if v[0] == e}
            p = p[p["sym"].isin(syms)] if len(p) else p
            c1 = c1[c1["sym"].isin(syms)] if c1 is not None and len(c1) else c1
        exp = e
    if cp in (1, -1):
        c = contract_data(p, spk, pin, t0, t1, exp, greeks, c1)
        return [c] if c else None
    cps = {"C": [1], "P": [-1]}.get(side, [1, -1])
    out = [c for c in (contract_data(p, spk, (k, x), t0, t1, exp, greeks, c1) for x in cps) if c]
    return out or None


def strike_strip(mt, spk, ks, t0, t1, side, pin, h=620):
    """Clickable 2-D strip (3-D clicks don't reach Streamlit): window volume per strike, C/P bars,
    a ⚡ dot coloured by the strongest spike's direction. Click a bar to pin that strike/contract."""
    from core.ridges_ag import DIR, direction, PIN
    w = mt[(mt["m"] >= t0) & (mt["m"] <= t1) & mt["strike"].isin(ks)] if len(mt) else mt
    f = go.Figure()
    for cp, nm, col in ((1, "C", "#7cc4ff"), (-1, "P", "#ffb86b")):
        if side != "C+P" and nm != side:
            continue
        v = w[w["cp"] == cp].groupby("strike")["size"].sum().reindex(ks).fillna(0)
        f.add_bar(y=[f"{k:,.0f}" for k in ks], x=v.values * (1 if cp == 1 else -1) if side == "C+P" else v.values,
                  orientation="h", marker_color=[PIN if (pin and pin[0] == k and pin[1] in (0, cp)) else col for k in ks],
                  customdata=[[k, cp] for k in ks], name=nm,
                  hovertemplate="%{y} " + nm + " · %{customdata[0]:,.0f} · %{x:,.0f}c<extra>click to pin</extra>")
    s = spk[(spk["m"] >= t0) & (spk["m"] <= t1) & spk["strike"].isin(ks)] if len(spk) else spk
    if len(s):                                  # L17a: rank numbers (1 = strongest spike in the window), coloured by direction
        s = s.assign(sc=s["prem"] * np.clip(s["z"].fillna(4.0), 1, 10)).sort_values("sc").groupby(["strike"]).tail(1)
        s = s.sort_values("sc", ascending=False).reset_index(drop=True)
        s["rank"] = np.arange(1, len(s) + 1)
        f.add_scatter(y=[f"{k:,.0f}" for k in s["strike"]], x=[0] * len(s), mode="markers+text",
                      marker=dict(size=17, color=[DIR[direction(cp, sd)][0] for cp, sd in zip(s["cp"], s["side"])],
                                  line=dict(width=1, color="#0b1020")),
                      text=[str(r) for r in s["rank"]], textfont=dict(color="white", size=10), textposition="middle center",
                      customdata=[[k, cp] for k, cp in zip(s["strike"], s["cp"])], name="rank",
                      hovertext=[f"#{r} {k:,.0f}{'C' if cp == 1 else 'P'} {m:%H:%M} · {int(sz)}c {sd} · ${pr / 1e3:,.0f}k"
                                 for r, k, cp, m, sz, sd, pr in zip(s["rank"], s["strike"], s["cp"], s["m"], s["size"], s["side"], s["prem"])],
                      hovertemplate="%{hovertext}<extra>click to pin this contract</extra>")
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h, barmode="overlay",
                    margin=dict(l=4, r=4, t=34, b=4), showlegend=False, clickmode="event+select",
                    title=dict(text="click a bar = strike · a number = that spike", font=dict(size=10, color="#8b949e"), x=0.02),
                    yaxis=dict(autorange="reversed" if False else True, tickfont=dict(size=9)),
                    xaxis=dict(showticklabels=False, zeroline=True, zerolinecolor="#444"))
    return f


def merge_candles(mt: pd.DataFrame, c1: pd.DataFrame) -> pd.DataFrame:
    """L16d: minutes covered by the 1-min option candles (uncapped backfill) come from the candles;
    later minutes (and contracts outside the backfill) come from the recorded prints."""
    if c1 is None or c1.empty:
        return mt
    cols = ["m", "sym", "strike", "cp", "size", "prem", "net"]
    if len(mt):
        have = pd.MultiIndex.from_arrays([c1["m"], c1["sym"]])
        keep = mt[~pd.MultiIndex.from_arrays([mt["m"], mt["sym"]]).isin(have)]
    else:
        keep = mt
    return pd.concat([c1[cols], keep[cols] if len(keep) else keep], ignore_index=True)


def _exset(exp):
    return {exp} if isinstance(exp, str) else set(exp)


def ridge_exps(rec, exp, mode):
    """v0.18: 0+1DTE = the selected expiry and the next listed one (AG's ridges include 1DTE)."""
    if mode != "0+1DTE":
        return [exp]
    with rec.lock:
        have = sorted({v[0] for v in rec.legs.values()})
    nxt = [e for e in have if e > exp]
    return [exp] + nxt[:1]


def candles_for(rec, exp, day):
    try:
        c1 = rec.opt1m_df()
    except Exception:                                          # noqa: BLE001
        return None
    if c1 is None or c1.empty:
        return None
    ex = _exset(exp)
    legs = {k: v for k, v in dict(rec.legs).items() if v[0] in ex}
    c1 = c1[c1["sym"].isin(legs) & S.mask(c1["m"], day)]
    return c1 if len(c1) else None


def fill5(rec, exp, day, p, c1):
    """L22b: before a contract's first recorded print (the 1,000-print replay cap after a restart), fill its
    minutes from the uncapped 5-minute candles (volume ÷ 5 per minute) when no 1-minute candle covers them.
    The 20 Oct live zip: the replay of near-spot strikes reached back only ~13:30–14:45 while the 5-min
    candles covered 09:30–16:15 — without this the near-spot ridges were empty for most of the session."""
    try:
        c5 = rec.candles5_df()
    except Exception:                                          # noqa: BLE001
        return None
    if c5 is None or c5.empty or p is None or not len(p):
        return None
    ex = _exset(exp)
    legs = {k: v for k, v in dict(rec.legs).items() if v[0] in ex}
    c5 = c5[c5["sym"].isin(legs) & (c5["vol"] > 0)]
    if c5.empty:
        return None
    first = p.groupby("sym")["ts_ms"].min()
    c5 = c5[c5["ts_ms"] + 5 * 60_000 <= c5["sym"].map(first).fillna(np.inf)]       # whole bar before the first print
    if c5.empty:
        return None
    px = (p.groupby("sym")["px"].median() if "px" in p else pd.Series(dtype=float))
    rows = []
    for k_ in range(5):
        rows.append(pd.DataFrame({"ts_ms": c5["ts_ms"].values + k_ * 60_000, "sym": c5["sym"].values,
                                  "size": c5["vol"].values / 5.0, "net": (c5["askv"] - c5["bidv"]).values / 5.0}))
    d = pd.concat(rows, ignore_index=True)
    from core.timeutil import ET as _ET
    d["m"] = pd.to_datetime(d["ts_ms"], unit="ms", utc=True).dt.tz_convert(_ET).dt.tz_localize(None)
    d = d[S.mask(d["m"], day)]
    if c1 is not None and len(c1):
        d = d[~pd.MultiIndex.from_arrays([d["m"], d["sym"]]).isin(pd.MultiIndex.from_arrays([c1["m"], c1["sym"]]))]
    if d.empty:
        return None
    d["strike"] = d["sym"].map(lambda x: legs[x][1]); d["cp"] = d["sym"].map(lambda x: legs[x][2])
    d["prem"] = d["size"] * d["sym"].map(px).fillna(0.0) * 100.0
    return d[["m", "sym", "strike", "cp", "size", "prem", "net"]]


def spikes_for(rec, p, day, exp, cfg):
    c1 = candles_for(rec, exp, day)
    f5 = fill5(rec, exp, day, p, c1)
    if f5 is not None:
        c1 = f5 if c1 is None else pd.concat([c1[["m", "sym", "strike", "cp", "size", "prem", "net"]], f5], ignore_index=True)
    key = ("spk", tuple(sorted(_exset(exp))), str(day), len(p), 0 if c1 is None else len(c1), S.gth(), getattr(rec, "ts_ms", None),
           repr(sorted(cfg.items())))
    cache = rec.ui_state.setdefault("_spikes", {})
    if key in cache:
        return cache[key]
    single = bool(cfg.get("single") and len(p) and "spread_leg" in p)
    q = p[~p["spread_leg"].astype(bool)] if single else p
    mt_all = merge_candles(SP.minute_table(p), c1)               # ridges/pane: ALL volume, backfilled
    mt = SP.minute_table(q) if single else mt_all                # single-leg can't use candles (no flag)
    res = SP.detect(mt, day, cfg) + (mt_all,)
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
    title = "TETRIS · 3-D · cumulative dealer γ from flow (cyan = dealers long γ / red-orange = short) · white = spot · right of now = decay projection"
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
        b = bars[(bars["c"] >= ks.min()) & (bars["c"] <= ks.max()) & (bars["t"] >= min(x)) & (bars["t"] <= max(x))]
        f.add_scatter3d(x=b["t"], y=b["c"].astype(float), z=np.full(len(b), 2.3), mode="lines",
                        line=dict(color="white", width=5), hoverinfo="skip", showlegend=False)
    return _style(f, title, h, three=True, zlabel="dealer γ (norm)")


def spikes_table(spk, key=None):
    """Spike list; click a row to pin that contract (returns the displayed frame for row → contract)."""
    if spk is None or spk.empty:
        st.caption("⚡ no spikes yet with the current filter")
        return None
    from core.ridges_ag import direction
    t = spk.iloc[::-1].copy()
    t["time"] = t["m"].dt.strftime("%H:%M")
    t["contract"] = [_label(k, cp) for k, cp in zip(t["strike"], t["cp"])]
    t["premium $"] = t["prem"].round(0)
    t["z"] = t["z"].round(1)
    t["package"] = t["legs"] if "legs" in t else ""
    t["dir"] = ["▲ bull" if direction(cp, sd) == "bull" else ("▼ bear" if direction(cp, sd) == "bear" else "· mid")
                for cp, sd in zip(t["cp"], t["side"])]
    t = t.reset_index(drop=True)
    st.dataframe(t[["time", "contract", "size", "premium $", "side", "dir", "z", "package"]], hide_index=True, width="stretch",
                 height=420, key=key, on_select="rerun" if key else "ignore", selection_mode="single-row")
    return t


def _style(f, title, h, three=True, zlabel="contracts / min"):
    f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=h,
                    margin=dict(l=4, r=4, t=34, b=4), title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01),
                    showlegend=False)
    if three:
        ax = dict(gridcolor="#1f2a44", backgroundcolor=BG, showbackground=True, color="#8b949e")
        f.update_layout(scene=dict(xaxis=dict(title="", tickformat="%H:%M", **ax),
                                   yaxis=dict(title="strike", tickformat=",.0f", nticks=8, **ax),
                                   zaxis=dict(title=zlabel, **ax), aspectmode="manual",
                                   aspectratio=dict(x=1.9, y=1.25, z=0.55),
                                   camera=dict(eye=dict(x=-0.35, y=-1.75, z=1.05))))
    else:
        f.update_xaxes(gridcolor="#1f2a44"); f.update_yaxes(gridcolor="#1f2a44")
    return f
