"""TETRIS (L18) — AG-style block view of where each strike's options matter most through the session.

Reverse-engineered against AG's 16 Oct 2026 tetris on the real 16 Oct tape (research 20 Oct; prototypes in
research/tetris_*.py). Best match: for every strike k and time bucket t

    value(k, t) = Σ_{C,P} weight(k, cp, t) · greek(S_t, K, T_t, iv)          greek = γ (model A) or vega (model E)
    weight      = prior-close open interest  [+ volume traded since the session open / since 09:30 — "overlay"]

then EACH STRIKE IS SCALED TO ITS OWN PEAK over the window (0 … 1). That per-strike scaling is what gives AG's
time structure (low strikes hot early, the purple "done" field spreading strike by strike, heat collapsing onto
the price into the close); every globally scaled model produced flat horizontal stripes instead.

Colour bands (purple → pink → light blue → dark blue → red → orange → tan):
  · "AG"       — band edges set so each colour covers the share of blocks measured on AG's 16 Oct chart
                 (purple 37 % · pink 5 % · light blue 20 % · dark blue 33 % · red 3 % · orange 1.5 % · tan 0.5 %):
                 warm colours are reserved for the extremes, as in his screenshots
  · "readable" — equal-width bands on 0 … 1 with a legend (0 = quiet for this strike, 1 = its peak)
Height = the same 0 … 1 value drawn from −1 to +1 (AG's axis), price path drawn ON the blocks.

Early warning (L10f/g, AG "ready for the sell"): an isolated warm block (red/orange/tan) ABOVE spot whose 5×5
neighbourhood is purple/pink, holding ≥ 3 buckets → listed and ringed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.stats import norm

AG_COLORS = ["#7a1fa2", "#d36ad6", "#7fd1e8", "#1f4fa8", "#d12b1f", "#f08a24", "#e8cf8a"]
AG_SHARE = np.array([0.37, 0.05, 0.20, 0.33, 0.03, 0.015, 0.005])          # AG 16 Oct chart (models A / E)
G_SHARE = np.array([0.25, 0.017, 0.047, 0.265, 0.239, 0.144, 0.037])     # AG 21 Oct chart, re-gridded (model G, research/l25)
READABLE = ["#1a1033", "#3b1f6e", "#2b5fa8", "#1fa3a3", "#5cc76a", "#e3c94a", "#ff8c42"]
BAND_NAMES = ["quiet", "low", "building", "active", "hot", "very hot", "peak"]
BUCKET = "10min"


def greek_field(legs: pd.DataFrame, S: pd.Series, expiry: pd.Timestamp, model: str,
                overlay: pd.DataFrame | None = None) -> pd.DataFrame:
    """legs: sym, strike, cp, oi, iv. S: spot per bucket (index = bucket times). overlay: buckets × sym of
    cumulative traded contracts to add to OI (None = OI only). Returns strikes × buckets (raw, unscaled)."""
    idx = S.index
    T = np.maximum((expiry - idx).total_seconds() / (365 * 24 * 3600), 1 / (365 * 24 * 12))
    Sv = S.values.astype(float)
    out = {}
    for r in legs.itertuples():
        iv = float(r.iv) if (r.iv == r.iv and r.iv and r.iv > 0) else 0.2
        w = np.full(len(idx), float(r.oi) if r.oi == r.oi else 0.0)
        if overlay is not None and r.sym in overlay:
            w = w + overlay[r.sym].reindex(idx).ffill().fillna(0.0).values
        if not w.any():
            continue
        d1 = (np.log(Sv / r.strike) + 0.5 * iv * iv * T) / (iv * np.sqrt(T))
        if model == "E":
            gk = Sv * norm.pdf(d1) * np.sqrt(T) / 100.0                      # vega per 1 vol pt
        else:
            gk = norm.pdf(d1) / (Sv * iv * np.sqrt(T)) * Sv * Sv * 0.01 * 100   # γ $ per 1 %
        out[r.strike] = out.get(r.strike, 0.0) + w * gk
    if not out:
        return pd.DataFrame()
    M = pd.DataFrame(out, index=idx).T.sort_index()
    return M


def price_grid_field(legs: pd.DataFrame, S: pd.Series, grid, overlay: pd.DataFrame | None = None,
                     ivpath: pd.DataFrame | None = None) -> pd.DataFrame:
    """v0.18 model G (research/l25, best match to AG's 21 Oct chart: 0.68 / 0.51 vs model A −0.04 / 0.20).
    For every PRICE LEVEL P of the grid and bucket t:
        value(P, t) = Σ_legs  w(leg, t) · γ(P, K, T_leg(t), iv_leg(t))
    i.e. "how much gamma all open positions would carry if SPX stood at P" — a price grid, not a per-strike sum.
    legs: sym, strike, cp, exp (date str), oi, iv · w = OI (+ cumulative traded contracts from `overlay`)
    · iv per bucket from `ivpath` (buckets × sym, the recorded chain snapshots) else the leg's iv."""
    idx = S.index
    P = np.asarray(sorted(grid), float)
    if legs.empty or not len(P):
        return pd.DataFrame()
    K = legs["strike"].values.astype(float)
    exp_end = np.array([pd.Timestamp(f"{e} 16:00").value for e in legs["exp"]], dtype=np.int64)
    iv0 = pd.to_numeric(legs["iv"], errors="coerce").values
    iv0 = np.where((iv0 > 0) & np.isfinite(iv0), iv0, 0.18)
    oi = pd.to_numeric(legs["oi"], errors="coerce").fillna(0.0).values
    W = np.broadcast_to(oi, (len(idx), len(K))).copy()
    if overlay is not None and len(overlay):
        ov = overlay.reindex(index=idx, columns=legs["sym"]).ffill().fillna(0.0).values
        W = W + ov
    IVm = np.broadcast_to(iv0, (len(idx), len(K))).copy()
    if ivpath is not None and len(ivpath):
        ivp = ivpath.reindex(index=idx, columns=legs["sym"]).ffill().values
        IVm = np.where(np.isfinite(ivp) & (ivp > 0), ivp, IVm)
    out = np.zeros((len(P), len(idx)))
    for j, t in enumerate(idx):
        T = np.maximum((exp_end - pd.Timestamp(t).value) / 1e9 / (365 * 86400), 300 / (365 * 86400))
        iv = IVm[j]
        sq = np.sqrt(T)
        d1 = (np.log(P[:, None] / K[None, :]) + 0.5 * iv[None, :] ** 2 * T[None, :]) / (iv[None, :] * sq[None, :])
        g = norm.pdf(d1) / (iv[None, :] * sq[None, :]) * P[:, None] * 0.01        # $γ per 1 % (∝ S·pdf/(σ√T))
        alive = (T > 300 / (365 * 86400) + 1e-12) | (exp_end > pd.Timestamp(t).value)
        out[:, j] = g[:, alive] @ W[j, alive]
    return pd.DataFrame(out, index=P, columns=idx)


def per_time_peak(M: pd.DataFrame, smooth: float = 0.0) -> pd.DataFrame:
    """Model G scaling: each TIME COLUMN scaled to its own peak (where, at that moment, gamma is concentrated)."""
    if M.empty:
        return M
    if smooth:
        M = pd.DataFrame(gaussian_filter1d(M.values, smooth, axis=0), index=M.index, columns=M.columns)
    mx = M.max(axis=0).replace(0, np.nan)
    return M.div(mx, axis=1).fillna(0.0).clip(0, 1)


def per_strike_peak(M: pd.DataFrame, smooth: float = 0.0) -> pd.DataFrame:
    if M.empty:
        return M
    if smooth:
        M = pd.DataFrame(gaussian_filter1d(M.values, smooth, axis=0), index=M.index, columns=M.columns)
    mx = M.max(axis=1).replace(0, np.nan)
    return M.div(mx, axis=0).fillna(0.0).clip(0, 1)


def bands(V: pd.DataFrame, palette: str, shares=None) -> np.ndarray:
    if V.empty:
        return np.zeros((0, 0), int)
    if palette == "AG":
        sh = AG_SHARE if shares is None else np.asarray(shares, float)
        edges = np.quantile(V.values.ravel(), np.cumsum(sh)[:-1])
        edges = np.maximum.accumulate(edges + np.arange(6) * 1e-12)
    else:
        edges = np.linspace(0, 1, 8)[1:-1]
    return np.clip(np.digitize(V.values, edges), 0, 6)


def specks(V: pd.DataFrame, B: np.ndarray, spot: pd.Series, hold: int = 3, warm: int = 4, quiet: int = 1):
    """Isolated warm blocks above spot inside a quiet (purple/pink) neighbourhood, holding ≥ `hold` buckets.
    Returns DataFrame(t, strike, band, first_t, run) — one row per block in a qualifying run."""
    if V.empty:
        return pd.DataFrame(columns=["t", "strike", "band", "first_t", "run"])
    ks = V.index.values
    cols = V.columns
    sp = spot.reindex(cols).ffill().values
    nk, nt = B.shape
    hit = np.zeros_like(B, bool)
    for i in range(nk):
        for j in range(nt):
            if B[i, j] < warm or not (ks[i] > sp[j] + 10):
                continue
            nb = B[max(0, i - 2):i + 3, max(0, j - 2):j + 3]
            if np.median(nb) <= quiet:
                hit[i, j] = True
    rows = []
    for i in range(nk):
        j = 0
        while j < nt:
            if hit[i, j] or (i > 0 and hit[i - 1, j]) or (i < nk - 1 and hit[i + 1, j]):
                j0 = j
                while j < nt and (hit[i, j] or (i > 0 and hit[i - 1, j]) or (i < nk - 1 and hit[i + 1, j])):
                    j += 1
                if j - j0 >= hold:
                    for jj in range(j0, j):
                        if hit[i, jj]:
                            rows.append((cols[jj], float(ks[i]), int(B[i, jj]), cols[j0], j - j0))
            else:
                j += 1
    return pd.DataFrame(rows, columns=["t", "strike", "band", "first_t", "run"])


def figure(V: pd.DataFrame, B: np.ndarray, spot: pd.Series, palette: str, title: str, sp_marks=None, h=760,
           eye=(0.45, -1.8, 1.35)):
    """3-D voxel blocks (strikes × buckets), price path drawn on the blocks, red last-price tag."""
    import plotly.graph_objects as go
    pal = AG_COLORS if palette == "AG" else READABLE
    f = go.Figure()
    if V.empty:
        f.add_annotation(text="no open interest / greeks for this expiry yet", x=0.5, y=0.5, xref="paper",
                         yref="paper", showarrow=False, font=dict(color="#6e7681"))
        f.update_layout(template="plotly_dark", height=360, paper_bgcolor="#1e2a4a")
        return f
    ks = V.index.values.astype(float)
    cols = V.columns
    H = V.values * 2 - 1
    step = float(np.median(np.diff(ks))) if len(ks) > 1 else 5.0
    X, Y, Z, I, J, K, FC = [], [], [], [], [], [], []
    tri = [(4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    gap, base = 0.14, -1.0
    for i, k in enumerate(ks):
        y0, y1 = k - step / 2 + step * 0.12, k + step / 2 - step * 0.12
        for j in range(len(cols)):
            top = max(float(H[i, j]), base + 0.03)
            x0, x1 = j + gap, j + 1 - gap
            n = len(X)
            X += [x0, x1, x1, x0, x0, x1, x1, x0]
            Y += [y0, y0, y1, y1, y0, y0, y1, y1]
            Z += [base, base, base, base, top, top, top, top]
            c = pal[B[i, j]]
            for a, b, cc in tri:
                I.append(n + a); J.append(n + b); K.append(n + cc); FC.append(c)
    f.add_mesh3d(x=X, y=Y, z=Z, i=I, j=J, k=K, facecolor=FC, flatshading=True, hoverinfo="skip",
                 lighting=dict(ambient=0.85, diffuse=0.45, specular=0.05, roughness=0.9),
                 lightposition=dict(x=-1e4, y=-2e4, z=3e4))
    sp = spot[(spot.index >= cols[0]) & (spot.index <= cols[-1] + pd.Timedelta(BUCKET))].dropna()
    if len(sp):
        tx = np.asarray((sp.index - cols[0]) / pd.Timedelta(BUCKET))
        y = sp.values.astype(float)
        inside = (y >= ks[0]) & (y <= ks[-1])
        ki = np.clip(np.searchsorted(ks, y), 0, len(ks) - 1)
        ji = np.clip(tx.astype(int), 0, len(cols) - 1)
        zl = np.where(inside, H[ki, ji] + 0.06, np.nan)
        f.add_scatter3d(x=tx, y=np.where(inside, y, np.nan), z=zl, mode="lines", connectgaps=False,
                        line=dict(color="white", width=7), hoverinfo="skip")
        f.add_scatter3d(x=[tx[-1] + 2], y=[float(np.clip(y[-1], ks[0], ks[-1]))], z=[1.18], mode="text",
                        text=[f"<b>{y[-1]:,.2f}</b>"], textfont=dict(color="#ff4d4d", size=15), hoverinfo="skip")
    if sp_marks is not None and len(sp_marks):
        tx = np.asarray((pd.to_datetime(sp_marks["t"]) - cols[0]) / pd.Timedelta(BUCKET)) + 0.5
        f.add_scatter3d(x=tx, y=sp_marks["strike"], z=np.full(len(sp_marks), 1.15), mode="markers",
                        marker=dict(size=7, symbol="circle-open", color="#ff3b3b", line=dict(width=3, color="#ff3b3b")),
                        text=[f"⚠ {k:,.0f} {pd.Timestamp(t):%H:%M} (since {pd.Timestamp(t0):%H:%M})"
                              for k, t, t0 in zip(sp_marks["strike"], sp_marks["t"], sp_marks["first_t"])],
                        hovertemplate="%{text}<extra>warm block above spot in a quiet field</extra>")
    nt = len(cols)
    tick = list(range(0, nt, max(1, nt // 6)))
    BG = "#1e2a4a"
    ax = dict(backgroundcolor=BG, gridcolor="#2c3a63", color="#c9d1d9", showbackground=True, title="")
    f.update_layout(paper_bgcolor=BG, height=h, margin=dict(l=0, r=0, t=34, b=0), showlegend=False,
                    title=dict(text=title, font=dict(color="#c9d1d9", size=12), x=0.01),
                    scene=dict(xaxis=dict(tickvals=tick, ticktext=[cols[t].strftime("%H:%M") for t in tick], **ax),
                               yaxis=dict(tickformat=",.0f", **ax),
                               zaxis=dict(range=[-1, 1.25], tickvals=[-1, 0, 1], **ax),
                               aspectmode="manual", aspectratio=dict(x=2.0, y=1.6, z=0.32),
                               camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2]))))
    return f


def topdown(V: pd.DataFrame, B: np.ndarray, spot: pd.Series, palette: str, h=330):
    """Small flat top-down view (AG's inset)."""
    import plotly.graph_objects as go
    pal = AG_COLORS if palette == "AG" else READABLE
    f = go.Figure()
    if V.empty:
        return f
    cs = [[i / 6, c] for i, c in enumerate(pal)]
    f.add_heatmap(z=B, x=V.columns, y=V.index, colorscale=cs, zmin=0, zmax=6, showscale=False,
                  hovertemplate="%{y:,.0f} · %{x|%H:%M}<extra></extra>")
    sp = spot[(spot.index >= V.columns[0])]
    f.add_scatter(x=sp.index, y=sp.values, mode="lines", line=dict(color="white", width=1.6), hoverinfo="skip")
    f.update_layout(template="plotly_dark", paper_bgcolor="#1e2a4a", plot_bgcolor="#1e2a4a", height=h,
                    margin=dict(l=4, r=4, t=26, b=4), showlegend=False,
                    title=dict(text="top-down", font=dict(size=11, color="#8b949e"), x=0.02),
                    yaxis=dict(range=[V.index.min(), V.index.max()], tickformat=",.0f"))
    return f


def legend_html(palette: str) -> str:
    pal = AG_COLORS if palette == "AG" else READABLE
    names = (["≈ 0", "", "", "", "", "", "strike's peak"] if palette == "AG" else BAND_NAMES)
    cells = "".join(f"<span style='display:inline-block;width:22px;height:12px;background:{c};margin-right:2px'></span>"
                    for c in pal)
    return (f"<div style='font-size:.8rem;color:#c9d1d9'>{cells}&nbsp; low → high for each strike "
            f"({names[0]} → {names[-1]}); "
            + ("AG palette: band edges match AG's colour shares, so warm = rare extremes" if palette == "AG"
               else "equal bands") + "</div>")
