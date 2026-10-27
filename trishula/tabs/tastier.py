"""TASTIER — 1:1 with the original Tastier GEX page (L19, v0.16).

Header: SPX price · live/replay badge · regime chip (Positive/Negative GEX + score) · β dealer switch.
Row 1 (open interest, naive convention): Total net GEX · Net bias · Call GEX · Put GEX · Zero gamma · Call wall · Put wall.
Row 2 (β dealer = flow-signed from the tape, naive alongside): Flow GEX · Flow γ-flip · Dealer Δ · Hedge → close ·
       Vanna −1 vol · Customer calls / puts · Spreads · blocks.
Panels: SPX price (interval, MACD/RSI/VRVP, Velocity/Absorb/Pressure, per-bar delta) · Dealer GEX by strike
(flow-adjusted colour, naive grey) · Dealer hedging (3 tiles + session lines) · Customer flow by strike ·
Dealer delta & vanna by strike · SPX vanna surface · SPX flow-adjusted gamma surface (price × time, candles on top).
Maths in core/dealer.py.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import dealer as DL
from core import loader as LD
from core.timeutil import ET

BG = "#0b0f14"
CARD = "#11161d"
GRID = "#1c2128"
GREEN, RED, BLUE, PURPLE, YEL, GREY = "#2ecc71", "#e74c3c", "#58a6ff", "#b388ff", "#f0c040", "#5a6372"
H_TOP, H_MID = 520, 300


def _style(fig, title, h, legend=False):
    fig.update_layout(template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD, height=h,
                      margin=dict(l=8, r=8, t=34, b=8), showlegend=legend,
                      title=dict(text=title, font=dict(size=12, color="#c9d1d9"), x=0.01))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def _empty(title, msg, h):
    f = go.Figure()
    f.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
                     font=dict(color="#6e7681", size=12))
    f.update_xaxes(visible=False)
    f.update_yaxes(visible=False)
    return _style(f, title, h)


def _t(ms):
    return pd.to_datetime(ms, unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)


def _b(x, unit=None, suf=None, sign=False):
    if x is None or not x == x:
        return "—"
    if unit is None:
        unit, suf = (1e9, "B") if abs(x) >= 1e9 else (1e6, "M")
    return f"{'+' if sign and x > 0 else ''}{'-' if x < 0 else ''}${abs(x) / unit:,.2f}{suf}"


def _bs(x):
    """$ amount with buy/sell (dealer hedge: + buy, − sell)."""
    if x is None or not x == x:
        return "—", ""
    v = abs(x)
    s = f"${v / 1e9:,.2f}B" if v >= 1e9 else f"${v / 1e6:,.1f}M"
    return s, ("buy" if x > 0 else "sell")


def _tile(label, value, sub="", color="#e6edf3", sub_color="#8b949e"):
    return (f"<div style='background:{CARD};border:1px solid #232b36;border-radius:6px;padding:6px 10px;"
            f"min-height:52px'><div style='font-size:.68rem;color:#8b949e;letter-spacing:.04em'>{label}</div>"
            f"<div style='font-family:monospace;font-size:1.05rem;font-weight:700;color:{color}'>{value}"
            f"<span style='font-size:.72rem;font-weight:400;color:{sub_color};margin-left:6px'>{sub}</span></div></div>")


def _row(tiles):
    cols = st.columns(len(tiles))
    for c, t in zip(cols, tiles):
        c.markdown(t, unsafe_allow_html=True)


def _history(rec, exp):
    """Chain snapshots for exp, plus the live chain as the newest column."""
    h = rec.chain_df()
    live = rec.live_chain(exp)
    if len(h):
        h = h[h["exp"] == exp]
    h = pd.concat([h, live], ignore_index=True) if len(live) else h
    if len(h):
        h = h.drop_duplicates(subset=["ts_ms", "sym"], keep="last")
    return h.dropna(subset=["spot"]) if len(h) else h


def render(rec, ctl):
    _draw(rec, ctl)


def _draw(rec, ctl):
    from core import session as S
    from core import vs3d_data as D
    LD.stage("chain + dealer exposures", 0.12)
    exp = ctl["exp"]
    spot, ssrc = rec.spot_now()
    asof = getattr(rec, "ts_ms", None)
    now = (pd.Timestamp(asof, unit="ms", tz="UTC").tz_convert(ET).tz_localize(None) if asof
           else pd.Timestamp(dt.datetime.now(ET).replace(tzinfo=None)))
    ch = rec.live_chain(exp) if exp else pd.DataFrame()
    have = bool(exp) and len(ch) and ch["gamma"].notna().any() and spot == spot
    if have:
        try:
            ds = rec.dsign_table(exp)
            ch = ch.drop(columns=["dsign"], errors="ignore").merge(ds[["sym", "dsign"]], on="sym", how="left")
        except Exception:                                   # noqa: BLE001
            ch["dsign"] = np.nan
    ss = st.session_state
    beta = bool(ss.get("t_beta", True))
    cN = DL.exposures(ch, spot, exp, now, False) if have else pd.DataFrame()
    cB = DL.exposures(ch, spot, exp, now, True) if have else pd.DataFrame()
    sN, sB = DL.summary(cN), DL.summary(cB)
    zN = DL.zero_gamma(ch, spot, exp, now, False) if have else None
    zB = DL.zero_gamma(ch, spot, exp, now, True) if have else None
    cur, scur = (cB, sB) if beta else (cN, sN)

    # ── header ────────────────────────────────────────────────────────
    h = st.columns([1.3, 1.6, 1.6, 3.0, 1.0])
    mode = (f"replay · {now:%Y-%m-%d %H:%M}" if asof else f"live · {now:%H:%M}")
    h[0].markdown(f"<div style='font-family:monospace;font-size:1.9rem;font-weight:800'>"
                  f"{spot:,.0f}</div>" if spot == spot else "—", unsafe_allow_html=True)
    h[1].markdown(f"<div style='margin-top:.6rem;border:1px solid {YEL};color:{YEL};border-radius:12px;padding:2px 10px;"
                  f"display:inline-block;font-family:monospace;font-size:.85rem'>{mode} · {ssrc}</div>", unsafe_allow_html=True)
    if sN:
        pos = sN["net"] >= 0
        col = GREEN if pos else RED
        h[2].markdown(f"<div style='margin-top:.6rem;border:1px solid {col};color:{col};border-radius:12px;padding:2px 10px;"
                      f"display:inline-block;font-family:monospace;font-size:.85rem'>{'▲ Positive' if pos else '▼ Negative'} GEX "
                      f"<b>{sN['score']:.0f}</b></div>", unsafe_allow_html=True)
    h[4].toggle("β dealer", value=True, key="t_beta",
                help="ON: dealer positions signed from the classified tape (seed + live). OFF: naive convention "
                     "(dealers long calls, short puts). Row 2 always shows flow-signed next to naive.")

    # ── metric rows ───────────────────────────────────────────────────
    _row([_tile("TOTAL NET GEX", _b(sN.get("net")), color=GREEN if sN.get("net", 0) >= 0 else RED),
          _tile("NET BIAS", _b(sN.get("bias")), color=GREEN if sN.get("bias", 0) >= 0 else RED),
          _tile("CALL GEX", _b(sN.get("call")), color=GREEN),
          _tile("PUT GEX", _b(sN.get("put")), color=RED),
          _tile("ZERO GAMMA", f"{zN:,.2f}" if zN else "—", color=PURPLE),
          _tile("CALL WALL", f"{sN['call_wall']:,.0f}" if sN.get("call_wall") else "—", color=GREEN),
          _tile("PUT WALL", f"{sN['put_wall']:,.0f}" if sN.get("put_wall") else "—", color=RED)])
    prints = rec.prints_df(exp) if exp else pd.DataFrame()
    day = D.session_date(rec)
    if len(prints):
        prints = prints.assign(ts=_t(prints["ts_ms"]))
        prints = prints[S.mask(prints["ts"], day)]
    if len(prints) and have and "delta" in ch:
        dmap = ch.drop_duplicates("sym").set_index("sym")["delta"]
        prints = prints.assign(delta=prints["delta"].fillna(prints["sym"].map(dmap)))
    cc = cp_ = spreads = bc = bp = 0
    if len(prints):
        nb = np.sign(prints["aggr"]) * prints["size"]
        cc, cp_ = int(nb[prints["cp"] == 1].sum()), int(nb[prints["cp"] == -1].sum())
        spreads = int(prints["spread_leg"].astype(bool).sum())
        blk = prints[prints["size"] >= 100]
        bc, bp = int((blk["cp"] == 1).sum()), int((blk["cp"] == -1).sum())
    tc, tcs = _bs(scur.get("to_close"))
    vv, vvs = _bs(scur.get("iv_dn"))
    _row([_tile("β · FLOW GEX", _b(sB.get("net")), f"naive {_b(sN.get('net'))}",
                color=GREEN if sB.get("net", 0) >= 0 else RED),
          _tile("FLOW γ-FLIP", f"{zB:,.1f}" if zB else "—", f"naive {zN:,.2f}" if zN else "", color=PURPLE),
          _tile("DEALER Δ", _b(scur.get("dex")), "flow" if beta else "naive", color=BLUE),
          _tile("HEDGE → CLOSE", tc, tcs, color=GREEN if tcs == "buy" else RED),
          _tile("VANNA −1 VOL", vv, vvs, color=GREEN if vvs == "buy" else RED),
          _tile("CUST. CALLS / PUTS", f"{cc / 1e3:+.1f}k/{cp_ / 1e3:+.1f}k", "net bought"),
          _tile("SPREADS · BLOCKS", f"{spreads / 1e3:.1f}k · {bc}/{bp}",
                "<span style='color:#ff5566'>● recording</span>" if not asof else "replay")])

    LD.stage("price panel", 0.35)
    bars = D.bars_for(rec, day, asof)
    r1 = st.columns([1.55, 1.0, 1.0])
    with r1[0]:
        st.plotly_chart(_price_panel(rec, prints, bars, day, spot), width="stretch", key="p_price")
    LD.stage("dealer panels", 0.55)
    gv = _window(cur, spot, ctl)
    with r1[1]:
        st.plotly_chart(_gex_panel(cN, cB, spot, zB if beta else zN, ctl), width="stretch", key="p_dgex")
        st.plotly_chart(_cust_panel(prints, spot, ctl), width="stretch", key="p_cust")
    with r1[2]:
        hist = _history(rec, exp) if exp else pd.DataFrame()
        if len(hist) and have and "dsign" in ch:
            hist = hist.drop(columns=["dsign"], errors="ignore").merge(
                ch.drop_duplicates("sym")[["sym", "dsign"]], on="sym", how="left")
        hh = DL.history(hist[hist["ts_ms"] >= S.bounds_ms(day)[0]] if len(hist) else hist, exp, beta) if len(hist) else pd.DataFrame()
        st.markdown(_hedge_tiles(scur), unsafe_allow_html=True)
        st.plotly_chart(_hedge_panel(hh), width="stretch", key="p_hedge")
        st.plotly_chart(_dv_panel(gv, spot), width="stretch", key="p_dv")
    LD.stage("vanna + gamma surfaces", 0.75)
    half = (ctl["pct"] / 100 * spot) if ctl["mode"] == "% move" else ctl["n"] * 5.0
    surf = None
    # v0.19.3 L45: surfaces from the 1-minute candles (survive a reboot); chain snapshots only as a fallback
    try:
        from tabs import agrev3d as R3_
        c1t = R3_.candles_for(rec, exp, day) if exp else None
    except Exception:                                            # noqa: BLE001
        c1t = None
    if c1t is not None and len(c1t) and spot == spot and ch is not None and len(ch):
        lg = ch.drop_duplicates("sym")[[c_ for c_ in ("sym", "strike", "cp", "oi", "iv", "dsign") if c_ in ch]]
        t_end = pd.Timestamp(bars["t"].max()) if bars is not None and len(bars) else pd.Timestamp(S.close_dt(day))
        keyt = ("tsurf2", exp, beta, len(c1t), t_end.floor("5min"), round(spot - half), round(spot + half), S.gth())
        cache = rec.ui_state.setdefault("_tsurf", {})
        if keyt not in cache:
            cache.clear()
            cache[keyt] = DL.surfaces_tape(lg, c1t, pd.Timestamp(S.open_dt(day)), t_end, exp, beta, spot - half, spot + half)
        surf = cache[keyt]
    if surf is None and len(hist) and spot == spot:
        key = ("tsurf", exp, beta, int(hist["ts_ms"].max()) // 300_000, round(spot - half), round(spot + half), S.gth())
        cache = rec.ui_state.setdefault("_tsurf", {})
        if key not in cache:
            hs = hist[hist["ts_ms"] >= S.bounds_ms(day)[0]]
            cache.clear()
            cache[key] = DL.surfaces(hs, exp, beta, spot - half, spot + half)
        surf = cache[key]
    r2 = st.columns(2)
    with r2[0]:
        st.plotly_chart(_surface_panel(surf, "vanna", bars, beta), width="stretch", key="p_vsurf")
    with r2[1]:
        gk = st.segmented_control("γ surface", ["total", "Δ today"], default="total", key="t_gsurf",
                                  label_visibility="collapsed",
                                  help="total = dealer γ from morning OI + today's flow · Δ today = only the γ ADDED (+) or "
                                       "REMOVED (−) for dealers by today's trading — where new positioning is going in")
        kind = "dgamma" if (gk == "Δ today" and surf is not None and "dgamma" in surf) else "gamma"
        st.plotly_chart(_surface_panel(surf, kind, bars, beta), width="stretch", key="p_gsurf")
    st.caption(f"{exp} · {len(ch)} legs · β dealer {'ON (flow-signed)' if beta else 'OFF (naive)'} · "
               f"OI = last settled · coverage: {_cov(ch)} · maths: core/dealer.py")


def _cov(ch):
    if ch is None or not len(ch) or "dsign" not in ch:
        return "—"
    return f"{int(ch['dsign'].notna().sum())}/{len(ch)} legs tape-signed"


def _window(c, spot, ctl):
    if c is None or c.empty:
        return pd.DataFrame(columns=["strike", "gex", "dex", "vanna"])
    half = (ctl["pct"] / 100 * spot) if ctl["mode"] == "% move" else ctl["n"] * 5.0
    g = DL.by_strike(c)
    return g[(g["strike"] - spot).abs() <= half]


# ── panels ───────────────────────────────────────────────────────────
def _price_panel(rec, prints, bars, day, spot):
    from core import overlays as OV
    from core import session as S
    ss = st.session_state
    c0 = st.columns([1.45, 1.3, 1.75])
    iv_ = c0[0].segmented_control("interval", ["1m", "5m", "15m", "1h"], default="1m", key="t_int",
                                  label_visibility="collapsed")
    ind = c0[1].segmented_control("indicators", ["MACD", "RSI", "VRVP"], selection_mode="multi", default=["VRVP"],
                                  key="t_ind", label_visibility="collapsed")
    ov = c0[2].segmented_control("overlays", ["Velocity", "Absorb", "Pressure"], selection_mode="multi",
                                 default=["Velocity", "Absorb", "Pressure"], key="t_ov2", label_visibility="collapsed",
                                 help="Velocity = EMA₃ of signed delta-notional ($M/min), spikes marked along the top · "
                                      "Absorb = extreme flow, flat price · Pressure = 15-min Σ flow ÷ σ")
    ind, ov = tuple(ind or ()), tuple(ov or ())
    title = f"SPX price · {iv_ or '1m'} · MA9 / MA21 · per-bar delta"
    if bars is None or bars.empty:
        return _empty("SPX price", "waiting for SPX candles / spot for this session", H_TOP)
    b = bars.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"}).copy()
    rule = {"1m": None, "5m": "5min", "15m": "15min", "1h": "1h"}.get(iv_ or "1m")
    if rule:
        b = (b.set_index("t").resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                    "ts_ms": "first"}).dropna(subset=["close"]).reset_index())
    sub = [x for x in ("MACD", "RSI") if x in ind]
    rows = 2 + len(sub)
    rh = [0.62, 0.20] + [0.18 / max(len(sub), 1)] * len(sub) if sub else [0.74, 0.26]
    vr = "VRVP" in ind
    f = make_subplots(rows=rows, cols=2 if vr else 1, shared_xaxes=True, row_heights=rh,
                      column_widths=[0.15, 0.85] if vr else None, vertical_spacing=0.02, horizontal_spacing=0.005,
                      specs=[[{}, {}] if vr else [{}]] + [[None, {}] if vr else [{}] for _ in range(rows - 1)])
    pc = 2 if vr else 1
    f.add_candlestick(x=b["t"], open=b["open"], high=b["high"], low=b["low"], close=b["close"],
                      increasing_line_color=GREEN, decreasing_line_color=RED, row=1, col=pc, name="SPX")
    f.add_scatter(x=b["t"], y=b["close"].rolling(9).mean(), line=dict(color=YEL, width=1), row=1, col=pc, name="MA9")
    f.add_scatter(x=b["t"], y=b["close"].rolling(21).mean(), line=dict(color=PURPLE, width=1), row=1, col=pc, name="MA21")
    cdf = bars.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})[["ts_ms", "open", "high", "low", "close"]]
    m = OV.minute_flow(prints, cdf, day, spot) if len(prints) else pd.DataFrame()
    if len(m):
        mm = m["dn"] if not rule else m["dn"].resample(rule).sum()
        f.add_bar(x=mm.index, y=mm.values / 1e6, marker_color=np.where(mm.values >= 0, GREEN, RED),
                  row=2, col=pc, name="Δ $M per bar", hovertemplate="%{x|%H:%M} Δ $%{y:.1f}M<extra></extra>")
        f.update_yaxes(title_text="Δ $M", title_font_size=10, row=2, col=pc)
        vel = OV.velocity(m)
        if "Velocity" in ov:
            sp_ = vel[vel["spike"]]
            if len(sp_):
                top = float(b["high"].max())
                f.add_scatter(x=sp_.index, y=[top + 1.0] * len(sp_), mode="markers", row=1, col=pc, name="velocity spike",
                              marker=dict(symbol="line-ns-open", size=16, line=dict(width=3, color=PURPLE)))
        if "Absorb" in ov:
            ab = OV.absorption(m, vel["z"])
            for side, sym, col in (("buyers absorbed", "triangle-down", RED), ("sellers absorbed", "triangle-up", GREEN)):
                a = ab[ab["side"] == side]
                if len(a):
                    f.add_scatter(x=a["t"], y=a["y"], mode="markers", row=1, col=pc, name=side,
                                  marker=dict(symbol=sym, size=10, color=col, line=dict(color="white", width=1)))
        if "Pressure" in ov:
            pr = OV.pressure(m)
            f.add_scatter(x=pr.index, y=[float(b["low"].min()) - 1.0] * len(pr), mode="markers", row=1, col=pc,
                          marker=dict(symbol="square", size=5, color=pr.fillna(0).values, cmin=-3, cmax=3,
                                      colorscale=[[0, "#c62828"], [0.5, "#30363d"], [1, "#2e7d32"]]), name="pressure")
    r = 3
    if "MACD" in sub:
        e12, e26 = b["close"].ewm(span=12).mean(), b["close"].ewm(span=26).mean()
        macd = e12 - e26; sig = macd.ewm(span=9).mean()
        f.add_bar(x=b["t"], y=macd - sig, marker_color=np.where(macd - sig >= 0, GREEN, RED), row=r, col=pc, name="MACD hist")
        f.add_scatter(x=b["t"], y=macd, line=dict(color=BLUE, width=1), row=r, col=pc, name="MACD")
        f.add_scatter(x=b["t"], y=sig, line=dict(color=YEL, width=1), row=r, col=pc, name="signal")
        r += 1
    if "RSI" in sub:
        d = b["close"].diff()
        up, dn = d.clip(lower=0).ewm(alpha=1 / 14).mean(), (-d.clip(upper=0)).ewm(alpha=1 / 14).mean()
        rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        f.add_scatter(x=b["t"], y=rsi, line=dict(color=PURPLE, width=1.2), row=r, col=pc, name="RSI")
        for y_ in (30, 70):
            f.add_hline(y=y_, line_dash="dot", line_color=GREY, line_width=1, row=r, col=pc)
    if vr and hasattr(rec, "spy_df"):
        prof = _vrvp_split(rec.spy_df(), rec.candles_df(), day)
        if prof is not None:
            mids, buy, sell, poc = prof
            f.add_bar(y=mids, x=-buy, orientation="h", marker_color="rgba(88,166,255,0.6)", row=1, col=1, name="buy vol")
            f.add_bar(y=mids, x=-sell, orientation="h", marker_color="rgba(240,160,64,0.6)", row=1, col=1, name="sell vol",
                      base=-buy)
            f.add_hline(y=poc, line_color=YEL, line_width=1, row=1, col=pc, annotation_text=f"POC {poc:,.0f}",
                        annotation_font_size=9, annotation_font_color=YEL)
        f.update_yaxes(showticklabels=False, row=1, col=1)
        f.update_xaxes(showticklabels=False, row=1, col=1)
    if S.gth():
        f.add_vline(x=S.rth_open_dt(day), line_dash="dash", line_color="#8a93a6", line_width=1, row=1, col=pc)
    last = float(b["close"].iloc[-1])
    f.add_annotation(x=b["t"].iloc[-1], y=last, text=f"<b>{last:,.2f}</b>", showarrow=False, xanchor="left", xshift=6,
                     bgcolor="#1f6f43", font=dict(color="white", size=11), row=1, col=pc)
    f.update_layout(xaxis_rangeslider_visible=False, barmode="overlay")
    for i in range(1, rows + 1):
        f.update_xaxes(rangeslider_visible=False, row=i, col=pc)
    lo_, hi_ = float(b["low"].min()), float(b["high"].max())
    pad = max(3.0, (hi_ - lo_) * 0.06)
    f.update_yaxes(side="right", range=[lo_ - pad, hi_ + pad], row=1, col=pc)
    if vr:
        f.update_yaxes(range=[lo_ - pad, hi_ + pad], row=1, col=1)
    return _style(f, title, H_TOP)


def _vrvp_split(spy, candles, day, bin_pts=2.0):
    """SPY volume profile in SPX points, split up-bar (buy) / down-bar (sell) volume."""
    from core.overlays import _t as _tt
    if spy is None or spy.empty or candles is None or candles.empty:
        return None
    s = spy.copy(); s["t"] = _tt(s["ts_ms"])
    s = s[(s["t"].dt.date == day)].set_index("t")
    c = candles.copy(); c["t"] = _tt(c["ts_ms"]); c = c.set_index("t")["close"]
    if s.empty or c.empty:
        return None
    ratio = (c.reindex(s.index, method="ffill") / s["close"]).ffill().bfill()
    s = s[(s["low"] > 0) & (s["high"] > 0)]
    ratio = ratio.reindex(s.index)
    lo, hi = (s["low"] * ratio).values, (s["high"] * ratio).values
    vol = s["volume"].fillna(0).values
    upb = (s["close"] >= s["open"]).values
    if not np.isfinite(lo).any() or vol.sum() <= 0:
        return None
    edges = np.arange(np.floor(np.nanmin(lo) / bin_pts) * bin_pts, np.ceil(np.nanmax(hi) / bin_pts) * bin_pts + bin_pts, bin_pts)
    buy, sell = np.zeros(len(edges) - 1), np.zeros(len(edges) - 1)
    for a, b_, v, u in zip(lo, hi, vol, upb):
        if not (np.isfinite(a) and np.isfinite(b_)) or v <= 0:
            continue
        i0 = max(0, int((a - edges[0]) // bin_pts)); i1 = min(len(buy) - 1, int((b_ - edges[0]) // bin_pts))
        (buy if u else sell)[i0:i1 + 1] += v / (i1 - i0 + 1)
    mids = (edges[:-1] + edges[1:]) / 2
    return mids, buy, sell, float(mids[int(np.argmax(buy + sell))])


def _levels(f, spot, flip):
    f.add_hline(y=spot, line_dash="dot", line_color="white", line_width=1, annotation_text=f"spot {spot:,.2f}",
                annotation_font_size=10, annotation_font_color="white")
    if flip:
        f.add_hline(y=flip, line_dash="dash", line_color=PURPLE, line_width=1.5, annotation_text=f"0γ {flip:,.1f}",
                    annotation_font_size=10, annotation_font_color=PURPLE, annotation_position="bottom right")


def _gex_panel(cN, cB, spot, flip, ctl):
    t = "Dealer GEX by strike · bars = flow-adjusted · grey = naive"
    if cN is None or cN.empty:
        return _empty(t, "waiting for greeks / OI", H_MID)
    gN, gB = _window(cN, spot, ctl), _window(cB, spot, ctl)
    f = go.Figure()
    f.add_bar(y=gN["strike"], x=gN["gex"] / 1e9, orientation="h", marker_color="rgba(110,118,129,0.45)", name="naive",
              width=3.6, hovertemplate="%{y:,.0f} naive $%{x:.2f}B<extra></extra>")
    f.add_bar(y=gB["strike"], x=gB["gex"] / 1e9, orientation="h", width=2.2,
              marker_color=np.where(gB["gex"] >= 0, GREEN, RED), name="flow",
              hovertemplate="%{y:,.0f} flow $%{x:.2f}B<extra></extra>")
    f.update_layout(barmode="overlay", xaxis_title="$B / 1 %")
    _levels(f, spot, flip)
    return _style(f, t, H_MID)


def _cust_panel(prints, spot, ctl):
    t = "Customer flow by strike · calls / puts net bought today (contracts)"
    if prints is None or not len(prints):
        return _empty(t, "no prints for this session yet", H_MID)
    half = (ctl["pct"] / 100 * spot) if ctl["mode"] == "% move" else ctl["n"] * 5.0
    p = prints[(prints["strike"] - spot).abs() <= half]
    nb = p.assign(nb=np.sign(p["aggr"]) * p["size"]).groupby(["strike", "cp"])["nb"].sum().unstack(fill_value=0.0)
    f = go.Figure()
    if 1 in nb:
        f.add_bar(y=nb.index, x=nb[1], orientation="h", marker_color="#26d0a8", name="calls", width=2.0, offset=0.4,
                  hovertemplate="%{y:,.0f}C %{x:+,.0f}<extra></extra>")
    if -1 in nb:
        f.add_bar(y=nb.index, x=nb[-1], orientation="h", marker_color="#ff5e78", name="puts", width=2.0, offset=-2.4,
                  hovertemplate="%{y:,.0f}P %{x:+,.0f}<extra></extra>")
    f.update_layout(barmode="overlay")
    f.add_hline(y=spot, line_dash="dot", line_color="white", line_width=1, annotation_text=f"spot {spot:,.2f}",
                annotation_font_size=10)
    return _style(f, t, H_MID)


def _hedge_tiles(s):
    tc, tcs = _bs(s.get("to_close"))
    iv, ivs = _bs(s.get("iv_dn"))
    dx, dxs = _bs(-s.get("dex", float("nan")) if s else float("nan"))
    cell = ("<div style='flex:1;background:#0d1117;border:1px solid #232b36;border-radius:6px;padding:4px 8px'>"
            "<div style='font-size:.62rem;color:#8b949e'>{}</div><div style='font-family:monospace;font-weight:700;"
            "font-size:1.05rem;color:{}'>{}<span style='font-size:.7rem;margin-left:4px'>{}</span></div></div>")
    c = lambda x: GREEN if x == "buy" else RED                  # noqa: E731
    return ("<div style='font-size:.8rem;color:#c9d1d9;margin-bottom:2px'><b>Dealer hedging</b> "
            "<span style='color:#8b949e'>what dealers must trade if spot / IV move</span></div>"
            "<div style='display:flex;gap:6px'>"
            + cell.format("INTO THE CLOSE", c(tcs), tc, tcs) + cell.format("IF IV −1 PT", c(ivs), iv, ivs)
            + cell.format("DEALER Δ NOW (hedge)", c(dxs), dx, dxs) + "</div>")


def _hedge_panel(hh):
    t = "dealer Δ $ (dashed) · hedge into the close $ (solid)"
    if hh is None or hh.empty:
        return _empty(t, "builds from the chain snapshots (every 60 s)", 230)
    f = go.Figure()
    f.add_scatter(x=hh["t"], y=hh["dex"] / 1e9, line=dict(color=BLUE, width=1.4, dash="dash"), name="dealer Δ $B")
    f.add_scatter(x=hh["t"], y=hh["to_close"] / 1e9, line=dict(color="#26d0a8", width=1.6), name="→ close $B")
    f.update_yaxes(tickprefix="$", ticksuffix="B")
    return _style(f, t, 230)


def _dv_panel(g, spot):
    t = "Dealer delta & vanna · Δ $ (blue) · vanna $ per +1 vol (yellow)"
    if g is None or g.empty:
        return _empty(t, "waiting for greeks / OI", H_MID - 30)
    f = go.Figure()
    f.add_bar(y=g["strike"], x=g["dex"] / 1e9, orientation="h", marker_color="rgba(88,166,255,0.85)", width=2.2,
              hovertemplate="%{y:,.0f} Δ $%{x:.2f}B<extra></extra>")
    f.add_scatter(y=g["strike"], x=g["vanna"] / 1e9, mode="lines+markers", line=dict(color=YEL, width=1.4),
                  marker=dict(size=4), hovertemplate="%{y:,.0f} vanna $%{x:.3f}B<extra></extra>")
    f.add_hline(y=spot, line_dash="dot", line_color="white", line_width=1, annotation_text=f"spot {spot:,.2f}",
                annotation_font_size=10)
    f.update_xaxes(tickprefix="$", ticksuffix="B")
    return _style(f, t, H_MID - 30)


def _surface_panel(surf, kind, bars, beta):
    b_ = " (β)" if beta else " (naive)"
    t = ("SPX vanna surface · dealer Δ per +1 vol by price" + b_ if kind == "vanna"
         else "SPX Δ today · dealer γ ADDED (+) / REMOVED (−) by today's flow" + b_ if kind == "dgamma"
         else "SPX flow-adjusted gamma surface · dealer γ by price" + b_)
    if surf is not None:
        t += " · from 1-min candles (survives reboots)" if surf.get("source") == "tape" else " · from chain snapshots"
    if surf is None:
        return _empty(t, "builds from the chain snapshots (every 60 s)", 460)
    Z = surf[kind]
    # v0.19.3: each time column scaled to its own peak — gamma grows ~10× into the close, so one scale for the whole
    # session hides the morning; per-column shows where exposure is concentrated AT EACH MOMENT (no future data)
    cm = np.nanmax(np.abs(Z), axis=0, keepdims=True)
    Z = Z / np.where(cm > 0, cm, 1.0)
    q = 1.0
    cs = ([[0, "#1e6fb8"], [0.5, "#0b0f14"], [1, "#f0a020"]] if kind == "vanna"
          else [[0, "#b64bff"], [0.5, "#0b0f14"], [1, "#2ecc71"]] if kind == "dgamma"
          else [[0, "#d1263a"], [0.45, "#3a0d18"], [0.5, "#0b0f14"], [0.55, "#0d2a5a"], [1, "#2f8bff"]])
    f = go.Figure(go.Heatmap(z=Z, x=surf["t"], y=surf["P"], zmin=-q, zmax=q, colorscale=cs, showscale=False,
                             zsmooth="best", hovertemplate="%{y:,.0f} · %{x|%H:%M}<br>%{z:.3s}<extra></extra>"))
    # 0γ flip line through time (from the gamma surface)
    G = surf["gamma"]
    flips = []
    for j in range(G.shape[1]):
        col = G[:, j]; s = np.sign(col); ix = np.where(np.diff(s) != 0)[0]
        flips.append(float(surf["P"][ix[np.argmin(np.abs(ix - len(col) / 2))]]) if len(ix) else np.nan)
    f.add_scatter(x=surf["t"], y=flips, mode="lines", line=dict(color=PURPLE, width=1.4, dash="dash"), name="0γ flip")
    if bars is not None and len(bars):
        bb = bars[(bars["t"] >= surf["t"][0])]
        f.add_candlestick(x=bb["t"], open=bb["o"], high=bb["h"], low=bb["l"], close=bb["c"], name="SPX",
                          increasing_line_color=GREEN, decreasing_line_color=RED)
    f.update_layout(xaxis_rangeslider_visible=False)
    f.update_yaxes(range=[float(surf["P"][0]), float(surf["P"][-1])], side="right")
    return _style(f, t, 460)
