"""VS3D Interval (bubbles) and DT (repositioning tape): ports of vs3dgbt 0.9.79's
Interval v2 (_iv2_imap / _iv2_bursts / _iv2_draw / _render_intv2) and DT
(dt_detect / _dt_tick), rebuilt on the recorder's own classified tape.

GBT's interval_map served per-5-min per-strike call/put exposure of traded volume.
Here the same numbers come from the prints: GEX = Σ size·γ·100·S (calls +, puts −,
or dealer dsign when signed), DEX = Σ size·Δ·100. Bursts = single-leg premium per
minute, log-z on a rolling RTH baseline (vs3dgbt IV2 constants). SPX only, since
TRISHULA records SPX options (vs3dgbt also drew SPY/NDX/QQQ from GBT).
DT replays minute by minute from the open, so its event log is causal and
deterministic: a replayed frame shows exactly the squares it showed live.
"""
from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .terrain import DARK  # noqa: E402
from .timeutil import ET  # noqa: E402

IV2_EDGE = ("09:40", "15:50"); IV2_ZWIN = 60; IV2_ZMIN = 20; IV2_ZTHR = 3.0
IV2_COOL = 5; IV2_CAP = 50; IV2_TOP = 5
IV2_POS = "dodgerblue"; IV2_NEG = "crimson"
IV2_RING_C = "#2eff8a"; IV2_RING_P = "#ff7300"; IV2_FILL = "#ff9f1a"


def _et(ms):
    return pd.to_datetime(ms, unit="ms", utc=True).dt.tz_convert(ET).dt.tz_localize(None)


def prep_prints(p: pd.DataFrame, greeks: dict, spot_now: float) -> pd.DataFrame:
    """Prints with greeks filled (replayed prints have none: snapshot greeks stand in)."""
    if p is None or p.empty:
        return pd.DataFrame()
    d = p[p["ev_type"].astype(str) != "2"].copy() if "ev_type" in p else p.copy()
    dm = {k: v[1] for k, v in greeks.items()}; gm = {k: v[2] for k, v in greeks.items()}
    d["delta"] = d["delta"].fillna(d["sym"].map(dm))
    d["gamma"] = d["gamma"].fillna(d["sym"].map(gm))
    d["spot"] = d["spot"].fillna(spot_now) if "spot" in d else spot_now
    d["ts"] = _et(d["ts_ms"])
    return d


def imap(d: pd.DataFrame, greek: str, dsign: dict | None = None, unseeded_w=0.2) -> pd.DataFrame:
    """Cumulative per-strike exposure of traded volume in 5-min buckets (vs3dgbt _iv2_imap)."""
    if d.empty:
        return pd.DataFrame(columns=["ts", "strike", "val", "gross"])
    is_call = d["cp"].values == 1
    if greek == "GEX":
        mag = d["size"].values * d["gamma"].fillna(0).abs().values * 100.0 * d["spot"].values
        naive = np.where(is_call, 1.0, -1.0)
    else:
        mag = d["size"].values * d["delta"].fillna(0).abs().values * 100.0
        naive = np.where(is_call, 1.0, -1.0)
    if dsign:
        ds = d["sym"].map(dsign).values.astype(float)
        if greek == "GEX":
            sg = np.where(np.isfinite(ds), ds, naive * unseeded_w)
        else:                                   # dealer long put = short delta
            sg = np.where(np.isfinite(ds), np.where(is_call, ds, -ds), naive * unseeded_w)
    else:
        sg = naive
    v = pd.DataFrame({"ts": d["ts"].dt.floor("5min"), "strike": d["strike"].values,
                      "cs": np.where(is_call, sg * mag, 0.0), "ps": np.where(~is_call, sg * mag, 0.0)})
    g = v.groupby(["ts", "strike"], as_index=False)[["cs", "ps"]].sum().sort_values("ts")
    g["val"] = g.groupby("strike")["cs"].cumsum() + g.groupby("strike")["ps"].cumsum()
    g["gross"] = g.groupby("strike")["cs"].cumsum().abs() + g.groupby("strike")["ps"].cumsum().abs()
    return g[["ts", "strike", "val", "gross"]]


def bursts(d: pd.DataFrame) -> pd.DataFrame:
    """Single-leg premium per minute → robust log-z (vs3dgbt _iv2_bursts)."""
    if d.empty:
        return pd.DataFrame(columns=["prem", "call_share", "z"])
    c = d[~d["spread_leg"].astype(bool)]
    if c.empty:
        return pd.DataFrame(columns=["prem", "call_share", "z"])
    m = c["ts"].dt.floor("1min")
    prem = c["size"] * c["px"] * 100.0
    cp = prem.where(c["cp"] == 1, 0.0)
    g = pd.DataFrame({"prem": prem.values, "cprem": cp.values}, index=m).groupby(level=0).sum().sort_index()
    if g.empty:
        return pd.DataFrame(columns=["prem", "call_share", "z"])
    idx = pd.date_range(g.index.min(), g.index.max(), freq="1min")
    g = g.reindex(idx, fill_value=0.0)
    g = g[(g.index.strftime("%H:%M") >= "09:30") & (g.index.strftime("%H:%M") <= "16:00")]
    g["call_share"] = g["cprem"] / g["prem"].replace(0, np.nan)
    s = np.log1p(g["prem"])
    med = s.rolling(IV2_ZWIN, min_periods=IV2_ZMIN).median()
    mad = (s - med).abs().rolling(IV2_ZWIN, min_periods=IV2_ZMIN).median()
    g["z"] = (s - med) / (1.4826 * np.maximum(mad, 0.05))
    out = g.dropna(subset=["z"])
    return out[(out.index.strftime("%H:%M") >= IV2_EDGE[0]) & (out.index.strftime("%H:%M") <= IV2_EDGE[1])]


def burst_reduce(raw):
    keep = []
    for t, r in raw.sort_index().iterrows():
        if keep and (t - keep[-1][0]) <= pd.Timedelta(minutes=IV2_COOL):
            continue
        keep.append((t, r))
        if len(keep) >= IV2_CAP:
            break
    return pd.DataFrame({t: r for t, r in keep}).T if keep else raw.iloc[0:0]


def draw_panel(ax, lbl, dd, bars, bz, day, rth=True, topn=IV2_TOP, zthr=IV2_ZTHR, badge=""):
    ax.set_facecolor(DARK); ax.tick_params(colors="#8a93a6", labelsize=9)
    for s_ in ax.spines.values():
        s_.set_color("#2a2f3a")
    if dd is None or getattr(dd, "empty", True):
        ax.set_title(f"{lbl} — SPX · NO DATA (no prints yet)", color="#ff5566", fontsize=13, fontweight="bold", loc="left")
        ax.set_xlim(dt.datetime.combine(day, dt.time(9, 25)), dt.datetime.combine(day, dt.time(16, 5)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        return
    top = dd.groupby("strike")["gross"].max().sort_values(ascending=False).head(int(topn)).index
    vmax = float(dd[dd["strike"].isin(top)]["gross"].max()) or 1.0
    pop, big = dd[~dd["strike"].isin(top)], dd[dd["strike"].isin(top)]
    ax.scatter(pop["ts"], pop["strike"], s=2.0, c=np.where(pop["val"] >= 0, IV2_POS, IV2_NEG), alpha=0.45, lw=0)
    ax.scatter(big["ts"], big["strike"], s=5 + 220 * (big["gross"] / vmax), c=np.where(big["val"] >= 0, IV2_POS, IV2_NEG),
               alpha=0.70, lw=0, zorder=4)
    nb = 0
    if bars is not None and len(bars):
        ax.plot(bars["t"], bars["c"].astype(float), color="white", lw=1.1, alpha=0.95, zorder=6)
        if bz is not None and len(bz):
            ev = burst_reduce(bz[bz["z"] >= float(zthr)])
            pxs = pd.Series(bars["c"].astype(float).values, index=pd.to_datetime(bars["t"]).dt.floor("1min"))
            pxs = pxs[~pxs.index.duplicated(keep="last")]
            bb = ev.join(pxs.rename("px"), how="inner"); nb = len(bb)
            if len(bb):
                zc = np.clip(bb["z"].astype(float), float(zthr), 12.0)
                edge = np.where(bb["call_share"].astype(float).fillna(0.5) >= 0.5, IV2_RING_C, IV2_RING_P)
                ax.scatter(bb.index, bb["px"], s=45 + 30 * (zc - IV2_ZTHR), color=IV2_FILL, edgecolors=edge, lw=1.6, alpha=0.95, zorder=8)
    op = dt.datetime.combine(day, dt.time(9, 30))
    ax.axvline(op, color="#888", ls="--", lw=0.9)
    if rth:
        ax.set_xlim(dt.datetime.combine(day, dt.time(9, 25)), dt.datetime.combine(day, dt.time(16, 5)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_title(f"{lbl} — SPX · 5m · top {int(topn)} · ● {nb} bursts z≥{float(zthr):g}{badge}",
                 color="#e8eef8", fontsize=13, fontweight="bold", loc="left")


def interval_figure(d, bars, day, dsign, signed, rth, topn, zthr):
    fig, axg = plt.subplots(1, 2, figsize=(16, 6.5))
    fig.patch.set_facecolor(DARK)
    bz = bursts(d)
    badge = " · SIGNED (dsign)" if signed else " · naive"
    for ax, g in zip(axg, ("DEX", "GEX")):
        draw_panel(ax, g, imap(d, g, dsign if signed else None), bars, bz, day, rth, topn, zthr, badge)
    plt.tight_layout()
    return fig


# ── DT repositioning tape ───────────────────────────────────────────────
def dt_detect(dot, cur, band_pct, floor_c, seen_bands):
    mv = cur - dot
    band = max(abs(dot) * band_pct / 100.0, float(floor_c))
    if band <= 0:
        return 0, None, seen_bands
    n = int(abs(mv) // band)
    if n <= seen_bands or n == 0:
        return 0, None, max(seen_bands, n)
    if abs(dot) < floor_c:
        g = ("blue", "filled") if mv > 0 else ("magenta", "filled")
    elif dot < 0:
        g = ("blue", "hollow") if mv > 0 else ("magenta", "filled")
    else:
        g = ("blue", "filled") if mv > 0 else ("magenta", "hollow")
    return n - seen_bands, g, n


def dt_events(ds: pd.DataFrame, live_prints: pd.DataFrame, bars: pd.DataFrame, band_pct, floor_c, prox_pct, watch):
    """Netflow lens (participant view): dot = seed (yesterday-final) n_call − n_put per strike;
    cur = dot + today's live net up to each minute. Minute-by-minute from the open, watch set =
    the `watch` strikes nearest spot inside ±prox% (spot = that minute's candle close)."""
    if ds is None or ds.empty:
        return []
    sn = ds.assign(nf=np.where(ds["type"] == "call", 1.0, -1.0) * ds["seed_net"]).groupby("strike")["nf"].sum()
    if live_prints is None or live_prints.empty or bars is None or bars.empty:
        return []
    lp = live_prints.copy()
    lp["m"] = lp["ts"].dt.floor("1min")
    lp["nf"] = np.where(lp["cp"] == 1, 1.0, -1.0) * np.sign(lp["aggr"]) * lp["size"]
    per = lp.groupby(["m", "strike"])["nf"].sum().unstack(fill_value=0.0).sort_index()
    cum = per.cumsum()
    px = pd.Series(bars["c"].astype(float).values, index=pd.to_datetime(bars["t"]).dt.floor("1min"))
    px = px[~px.index.duplicated(keep="last")]
    seen, events = {}, []
    for m in cum.index:
        sp = px.asof(m) if len(px) else np.nan
        if not sp == sp:
            continue
        w = sp * prox_pct / 100.0
        ks = sorted((k for k in sn.index if abs(k - sp) <= w), key=lambda k: abs(k - sp))[:int(watch)]
        row = cum.loc[m]
        for k in ks:
            dot = float(sn.get(k, 0.0)); cur = dot + float(row.get(k, 0.0))
            nnew, g, bands = dt_detect(dot, cur, band_pct, floor_c, seen.get(k, 0))
            seen[k] = bands
            if nnew and g:
                events.append({"t": m.to_pydatetime(), "k": float(k), "c": g[0], "f": g[1]})
    return events


def dt_figure(events, bars, day, band_pct, floor_c, prox_pct):
    fg, axd = plt.subplots(figsize=(13, 5.6), dpi=100)
    fg.patch.set_facecolor(DARK); axd.set_facecolor(DARK)
    if bars is not None and len(bars):
        axd.plot(pd.to_datetime(bars["t"]).values, bars["c"].astype(float).values, color="#e8ecf2", lw=1.1, zorder=4)
    else:
        axd.text(0.01, 0.98, "no price bars for this session yet", transform=axd.transAxes, color="#ef5350", fontsize=8, va="top")
    for e in events:
        fc = ("#1e90ff" if e["c"] == "blue" else "#ff00ff")
        axd.scatter([e["t"]], [e["k"]], s=64, marker="s", zorder=6,
                    facecolors=(fc if e["f"] == "filled" else "none"), edgecolors=fc, linewidths=1.6)
    axd.set_xlim(dt.datetime.combine(day, dt.time(9, 30)), dt.datetime.combine(day, dt.time(16, 0)))
    axd.tick_params(colors="#8b949e", labelsize=8)
    for spn in axd.spines.values():
        spn.set_color("#30363d")
    axd.set_title(f"DT repositioning tape · {len(events)} events · watch ±{prox_pct:.2f}% · band {band_pct:.1f}% · "
                  f"floor {int(floor_c)} · blue = bullish / magenta = bearish · filled = extending, hollow = receding",
                  color="#8b949e", fontsize=9, loc="left")
    axd.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    return fg
