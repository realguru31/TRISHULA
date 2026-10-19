"""VS3D Terrain (Gradient Chart): port of vs3dgbt 0.9.79's terrain functions,
used as-is with the data inputs swapped to the tastytrade recorder.

Ported: bs_gamma/bs_charm/bs_delta/bs_vanna/bs_color, _T_at, terrain_grid,
terrain_scale, terrain_intensity, terrain_pockets, terrain_contours,
terrain_straddle, pinak_levels, gamma_exposure_minis, the cmaps, _decay_shift,
draw_candles, style_time_axis, and the _render_terrain figure (main panel +
side profile + peak-γ rail + stacked charm panel).

One change from vs3dgbt: `signed=True` lets per-leg dealer signs (dsign,
confidence-weighted; unseeded legs = naive × 0.2) drive the field. vs3dgbt's
terrain always used calls+/puts−; here the "Signed field" toggle defaults on
to match the Book.
"""
from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.ndimage import gaussian_filter1d  # noqa: E402
from scipy.signal import argrelextrema  # noqa: E402
from scipy.stats import norm  # noqa: E402

GBT_UNSEEDED_W = 0.2
DARK = "#0d1117"; TXT = "#c9d1d9"; GRID = "#222a35"; WHITE = "#e6edf3"
UP = "#ffffff"; DOWN = "#ff8c00"
GHEAVY = "Gamma |Γ| (heaviness)"; GDECAY = "Gamma Decay (color)"
GREEKS = ["Delta Change", "Gamma", "Charm", GHEAVY, GDECAY]
WEIGHTS = ["OI + Volume", "OI (opening book)", "Volume (today's flow)", "Vol else OI (legacy)"]
FIELD_MODES = ["Aggregate (guide-spec §2)", "Per-strike ladder (exploration)"]


# ── greeks ──────────────────────────────────────────────────────────────
def bs_gamma(S, K, T, sig):
    S = np.asarray(S, float); K = np.asarray(K, float); T = np.maximum(T, 1e-9); sig = np.maximum(sig, 1e-4)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    return norm.pdf(d1) / (S * sig * np.sqrt(T))


def bs_charm(S, K, T, sig):
    S = np.asarray(S, float); K = np.asarray(K, float); T = np.maximum(T, 1e-9); sig = np.maximum(sig, 1e-4)
    sq = sig * np.sqrt(T); d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / sq; d2 = d1 - sq
    return norm.pdf(d1) * d2 / (2.0 * T)


def bs_delta(S, K, T, sig, is_call=True):
    S = np.asarray(S, float); K = np.asarray(K, float); T = np.maximum(T, 1e-9); sig = np.maximum(sig, 1e-4)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    return norm.cdf(d1) if is_call else norm.cdf(d1) - 1.0


def bs_vanna(S, K, T, sig):
    S = np.asarray(S, float); K = np.asarray(K, float); T = np.maximum(T, 1e-9); sig = np.maximum(sig, 1e-4)
    sq = sig * np.sqrt(T); d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / sq; d2 = d1 - sq
    return -norm.pdf(d1) * d2 / sig


def bs_color(S, K, T, sig, r=0.0):
    S = np.asarray(S, float); K = np.asarray(K, float); T = np.maximum(T, 1e-9); sig = np.maximum(sig, 1e-4)
    sq = sig * np.sqrt(T); d1 = (np.log(S / K) + (r + 0.5 * sig ** 2) * T) / sq; d2 = d1 - sq
    raw = -norm.pdf(d1) / (2 * S * T * sq) * (1 + d1 * (2 * r * T - d2 * sq) / sq)
    return raw / 365.0


def _T_at(es, ts):
    exp = dt.datetime.combine(dt.datetime.strptime(es, "%Y-%m-%d").date(), dt.time(16, 0))
    return max((exp - ts).total_seconds(), 60.) / (365 * 24 * 3600)


def _dealer_sign(c, signed=True):
    nv = np.where(c["type"].values == "call", 1.0, -1.0)
    if signed and "dsign" in c.columns:
        d = pd.to_numeric(c["dsign"], errors="coerce").values.astype(float)
        return np.where(np.isfinite(d), d, nv * GBT_UNSEEDED_W)
    return nv


# ── the field ───────────────────────────────────────────────────────────
def terrain_grid(chain, spot, exps, now, day, greek="Delta Change", vol_adj=0.0, field_mode=FIELD_MODES[0],
                 p_min=None, p_max=None, n_price=170, n_time=84, simulated_gamma=False,
                 simulated_charm=False, weighting="OI + Volume", signed=False):
    """Field Z(price,time) for the chosen greek over ALL expiries in `exps`, on the
    09:30–16:00 axis of `day`. Leg sign: naive calls+/puts−, or dealer dsign when signed."""
    if p_min is None:
        p_min = spot * 0.975
    if p_max is None:
        p_max = spot * 1.025
    pg = np.linspace(p_min, p_max, n_price)
    open_ = dt.datetime.combine(day, dt.time(9, 30)); close = dt.datetime.combine(day, dt.time(16, 0))
    taus = [open_ + dt.timedelta(seconds=s) for s in np.linspace(0, (close - open_).total_seconds(), n_time)]
    Z = np.zeros((n_price, n_time))
    book_now = 0.0
    for es in exps:
        ce = chain[chain["exp"] == es] if "exp" in chain.columns else chain
        ce = ce.dropna(subset=["strike", "gamma"])
        if ce.empty:
            continue
        cc = ce[ce.type == "call"]; pp = ce[ce.type == "put"]

        def arr(df):
            K = df["strike"].values.astype(float)
            iv = np.where(df["iv"].fillna(0).values > 0, df["iv"].fillna(0).values, 0.15) + vol_adj
            vol = df["volume"].fillna(0).values.astype(float); oi = df["oi"].fillna(0).values.astype(float)
            if weighting == "Volume (today's flow)":
                w = vol
            elif weighting == "OI (opening book)":
                w = oi
            elif weighting == "Vol else OI (legacy)":
                w = np.where(vol > 0, vol, oi)
            else:
                w = oi + vol
            # leg sign folded into the weight: naive = +calls / −puts (vs3dgbt), signed = dsign
            s = _dealer_sign(df, signed) * np.where(df["type"].values == "call", 1.0, -1.0)
            return K, iv, w * s
        Kc, ivc, wc = arr(cc); Kp, ivp, wp = arr(pp)
        Tn = _T_at(es, now)
        if greek == "Delta Change":
            book_now += (wc * bs_delta(spot, Kc, Tn, ivc, True)).sum() * 100 \
                - (wp * bs_delta(spot, Kp, Tn, ivp, False)).sum() * 100
        Sg = pg[:, None]
        for j, tau in enumerate(taus):
            T = _T_at(es, tau)
            if greek == "Gamma":
                if str(field_mode).startswith("Per-strike"):
                    gc = bs_gamma(spot, Kc, T, ivc); gp = bs_gamma(spot, Kp, T, ivp)
                    _contrib = np.zeros_like(Z[:, j])
                    for _K, _v in ((Kc, gc * wc * 100.0 * Kc), (Kp, -(gp * wp * 100.0 * Kp))):
                        if len(_K):
                            _idx = np.abs(pg[None, :] - _K[:, None]).argmin(1)
                            np.add.at(_contrib, _idx, _v)
                    Z[:, j] += _contrib
                elif simulated_gamma:
                    dU = bs_delta(Sg + 5, Kc[None, :], T, ivc[None, :], True); dD = bs_delta(Sg - 5, Kc[None, :], T, ivc[None, :], True)
                    gc = (dU - dD) / 10.0
                    dU = bs_delta(Sg + 5, Kp[None, :], T, ivp[None, :], False); dD = bs_delta(Sg - 5, Kp[None, :], T, ivp[None, :], False)
                    gp = (dU - dD) / 10.0
                    Z[:, j] += (gc * wc[None, :]).sum(1) * 100 * pg - (gp * wp[None, :]).sum(1) * 100 * pg
                else:
                    gc = bs_gamma(Sg, Kc[None, :], T, ivc[None, :]); gp = bs_gamma(Sg, Kp[None, :], T, ivp[None, :])
                    Z[:, j] += (gc * wc[None, :]).sum(1) * 100 * pg - (gp * wp[None, :]).sum(1) * 100 * pg
            elif greek == "Charm":
                if simulated_charm:
                    _dT = 5.0 / (365.0 * 24 * 60)
                    T2 = max(T - _dT, 1e-8)
                    ch_c = (bs_delta(Sg, Kc[None, :], T2, ivc[None, :], True) - bs_delta(Sg, Kc[None, :], T, ivc[None, :], True))
                    ch_p = (bs_delta(Sg, Kp[None, :], T2, ivp[None, :], False) - bs_delta(Sg, Kp[None, :], T, ivp[None, :], False))
                else:
                    ch_c = bs_charm(Sg, Kc[None, :], T, ivc[None, :]); ch_p = bs_charm(Sg, Kp[None, :], T, ivp[None, :])
                Z[:, j] += (ch_c * wc[None, :]).sum(1) * 100 - (ch_p * wp[None, :]).sum(1) * 100
            else:
                dc = bs_delta(Sg, Kc[None, :], T, ivc[None, :], True); dp = bs_delta(Sg, Kp[None, :], T, ivp[None, :], False)
                Z[:, j] += (dc * wc[None, :]).sum(1) * 100 - (dp * wp[None, :]).sum(1) * 100
    if greek == "Delta Change":
        Z = book_now - Z
    if str(field_mode).startswith("Per-strike"):
        Z = gaussian_filter1d(Z, 0.6, axis=0)
    return pg, Z, taus


def terrain_scale(Z, mode, cap, pct):
    if mode == "Manual (fixed cap)":
        sc = cap if cap and cap > 0 else (np.percentile(np.abs(Z), 92) or 1.0)
    elif mode == "Percentile":
        sc = np.percentile(np.abs(Z), pct) or 1.0
    else:
        sc = (2.0 * np.abs(Z).std()) or 1.0
    return np.clip(Z / sc, -1, 1), sc


def terrain_intensity(V, kind="Power", power=1.0, gain=3.0, floor=0.0):
    s = np.sign(V); m = np.abs(V)
    if kind == "Sqrt":
        m = np.sqrt(m)
    elif kind == "Arcsinh":
        m = np.arcsinh(gain * m) / np.arcsinh(gain)
    else:
        m = np.power(m, max(power, 0.05))
    if floor > 0.0:
        m = np.where(m > 0.0, floor + (1.0 - floor) * m, 0.0)
    return s * m


def terrain_pockets(ax, Vn, x0, x1, pg, topn=3):
    try:
        from scipy import ndimage
        neg = np.where(np.isfinite(Vn), -Vn, 0.0)
        ref = float(neg.max())
        if ref <= 0:
            return
        cav = neg > 0.30 * ref
        if not cav.any():
            return
        lab, n = ndimage.label(cav)
        depths = ndimage.maximum(neg, lab, index=np.arange(1, n + 1))
        keep = (np.argsort(depths)[::-1][:max(1, int(topn))] + 1)
        mask = np.isin(lab, keep)
        X = np.linspace(x0, x1, Vn.shape[1])
        ax.contourf(X, pg, np.where(mask, 1.0, np.nan), levels=[0.5, 1.5], colors=["#03050a"], alpha=0.62, zorder=6)
        core = np.where(mask & (neg > 0.65 * ref), 1.0, np.nan)
        ax.contourf(X, pg, core, levels=[0.5, 1.5], colors=["#d9303f"], alpha=0.70, zorder=6)
        ax.contour(X, pg, mask.astype(float), levels=[0.5], colors=["#e8ecf2"], linewidths=1.0,
                   linestyles="--", alpha=0.9, zorder=7)
    except Exception:
        pass


def terrain_contours(ax, Z, x0, x1, pg, cap, zero=True, ridges=True):
    X = np.linspace(x0, x1, Z.shape[1])
    if zero:
        try:
            ax.contour(X, pg, Z, levels=[0.0], colors="#e8e8e8", linewidths=1.0, linestyles=(0, (4, 3)), alpha=.9, zorder=6)
        except Exception:
            pass
    if not ridges:
        return
    thr = 0.25 * (cap or (np.abs(Z).max() or 1.0)); edge = 4

    def chains(sign):
        pts = {}
        for j in range(Z.shape[1]):
            colv = Z[:, j] * sign
            idx = argrelextrema(colv, np.greater, order=6)[0]
            pts[j] = [i for i in idx if colv[i] > thr and edge <= i < Z.shape[0] - edge]
        used = set(); out = []
        for j0 in range(Z.shape[1]):
            for i0 in pts.get(j0, []):
                if (j0, i0) in used:
                    continue
                ch = [(j0, i0)]; used.add((j0, i0)); j, i = j0, i0
                while j + 1 < Z.shape[1]:
                    cand = [k for k in pts.get(j + 1, []) if abs(k - i) <= 4 and (j + 1, k) not in used]
                    if not cand:
                        break
                    k = min(cand, key=lambda q: abs(q - i)); ch.append((j + 1, k)); used.add((j + 1, k)); j, i = j + 1, k
                if len(ch) >= 8:
                    out.append(ch)
        out.sort(key=len, reverse=True)
        return out[:4]
    _stroke = [pe.withStroke(linewidth=3.0, foreground="#140a02")]
    for sgn in (+1, -1):
        for ch in chains(sgn):
            ln, = ax.plot([X[j] for j, _ in ch], [pg[i] for _, i in ch], color="#ff9500", lw=1.6, alpha=1.0, zorder=8)
            ln.set_path_effects(_stroke)


def terrain_straddle(chain0, spot):
    c = chain0.dropna(subset=["strike"])
    if c.empty:
        return None
    ks = c["strike"].unique(); k = ks[np.argmin(np.abs(ks - spot))]

    def mid(df):
        if df.empty:
            return np.nan
        b = df["bid"].iloc[0] or 0; a = df["ask"].iloc[0] if "ask" in df else b
        b = 0 if b != b else b; a = b if (a is None or a != a) else a
        return (b + a) / 2 if (b or a) else np.nan
    cm = mid(c[(c.strike == k) & (c.type == "call")]); pm = mid(c[(c.strike == k) & (c.type == "put")])
    v = (0 if np.isnan(cm) else cm) + (0 if np.isnan(pm) else pm)
    return float(v) if v > 0 else None


def pinak_levels(chain, spot, exp, now):
    c = chain.dropna(subset=["strike"]).copy()
    c = c.groupby(["strike", "type"], as_index=False).first()
    cc = c[c.type == "call"].set_index("strike"); pp = c[c.type == "put"].set_index("strike")
    K = np.array(sorted(set(cc.index) | set(pp.index)), float)

    def col(df, k):
        return df[k].reindex(K).fillna(0).values
    cg = col(cc, "gamma"); pgm = col(pp, "gamma"); coi = col(cc, "oi"); poi = col(pp, "oi")
    civ = col(cc, "iv"); piv = col(pp, "iv"); cpx = col(cc, "bid"); ppx = col(pp, "bid")
    mult = 100.0
    call_gex = cg * coi * spot * mult; put_gex = pgm * poi * spot * mult
    net_gex = call_gex - put_gex; tot_gex = call_gex + put_gex
    flip = None
    gex_floor = 0.02 * np.abs(net_gex).max()
    cross = []
    for i in range(len(K) - 1):
        a, b = net_gex[i], net_gex[i + 1]
        if np.sign(a) != np.sign(b) and b != a and max(abs(a), abs(b)) >= gex_floor:
            cross.append(float(K[i] + (K[i + 1] - K[i]) * (-a) / (b - a)))
    if cross:
        flip = float(min(cross, key=lambda x: abs(x - spot)))
    above = K > spot; below = K < spot
    _wa = flip if flip is not None else spot
    ab_f = K > _wa; bl_f = K < _wa
    call_wall = float(K[ab_f][np.argmax(call_gex[ab_f])]) if ab_f.any() and call_gex[ab_f].max() > 0 else None
    put_wall = float(K[bl_f][np.argmax(put_gex[bl_f])]) if bl_f.any() and put_gex[bl_f].max() > 0 else None
    T = _T_at(exp, now)
    vanna = np.abs(bs_vanna(spot, K, T, np.where(civ > 0, civ, np.where(piv > 0, piv, 0.15))))
    vn = vanna / (vanna.max() or 1.0)
    up_hw = None
    if call_wall is not None:
        m = K > call_wall
        if m.any():
            hp = (call_gex[m] * coi[m]) * np.exp(-5 * (K[m] - call_wall) / call_wall) * (1 + vn[m])
            if hp.max() > 0:
                up_hw = float(K[m][np.argmax(hp)])
    dn_hw = None
    if put_wall is not None:
        m = K < put_wall
        if m.any():
            hp = (put_gex[m] * poi[m]) * np.exp(-5 * (put_wall - K[m]) / put_wall) * (1 + vn[m])
            if hp.max() > 0:
                dn_hw = float(K[m][np.argmax(hp)])
    posmask = net_gex > 0

    def side_level(mask):
        idx = np.where(mask)[0]
        if len(idx) == 0:
            return None
        score = np.abs(net_gex[idx]) * (coi[idx] + poi[idx])
        return float(K[idx][np.argmax(score)])
    ceiling = side_level(posmask & above); floor = side_level(posmask & below)

    def centroid(mask):
        w = np.abs(net_gex[mask])
        return float((K[mask] * w).sum() / w.sum()) if w.sum() > 0 else None
    call_grav = centroid(ab_f); put_grav = centroid(bl_f)
    nb = np.abs(K - spot) <= spot * 0.025
    if nb.any():
        tg = np.where(nb, tot_gex, -1); to_ = np.where(nb, coi + poi, -1)
        max_gex_k = float(K[np.argmax(tg)]) if tg.max() > 0 else spot
        max_oi_k = float(K[np.argmax(to_)]) if to_.max() > 0 else spot
    else:
        max_gex_k = max_oi_k = spot
    in_pos = (flip is not None and spot > flip) or (flip is None and len(K) and net_gex[np.argmin(np.abs(K - spot))] > 0)
    conv = abs(max_gex_k - max_oi_k)
    grav_agree = (call_grav is not None and put_grav is not None and abs(call_grav - put_grav) < spot * 0.01)
    pin = float(np.average([max_gex_k, max_oi_k]))
    score = 0
    score += 35 if in_pos else 0
    score += 30 if conv < spot * 0.0015 else (15 if conv < spot * 0.004 else 0)
    score += 20 if grav_agree else 0
    score += 15 if abs(pin - spot) < spot * 0.003 else (7 if abs(pin - spot) < spot * 0.008 else 0)
    label = ("STRONG PIN" if score >= 75 else "MODERATE PIN" if score >= 50 else "WEAK PIN" if score >= 25 else "NO PIN")
    _mature = bool(nb.any()) and int((tot_gex[nb] > 0).sum()) >= 6
    if not (in_pos and conv < spot * 0.004 and _mature):
        pin = None
        label = "NO PIN (" + ("open/sparse data" if not _mature
                              else "trending — negative γ" if not in_pos else "GEX/OI diverge") + ")"
    cask = col(cc, "ask"); pask = col(pp, "ask")
    kstar = None; best = 1e18; band = spot * 0.01
    for i, k in enumerate(K):
        if abs(k - spot) > band:
            continue
        if cpx[i] <= 0 or ppx[i] <= 0:
            continue
        if cask[i] < cpx[i] or pask[i] < ppx[i]:
            continue
        cmid = 0.5 * (cpx[i] + cask[i]); pmid = 0.5 * (ppx[i] + pask[i])
        F = cmid + k - pmid
        d = abs(F - spot)
        if d < best:
            best = d; kstar = float(k)
    colr = (bs_color(spot, K, T, np.where(civ > 0, civ, 0.15)) * coi
            + bs_color(spot, K, T, np.where(piv > 0, piv, 0.15)) * poi) * spot * mult
    return dict(K=K, call_gex=call_gex, put_gex=put_gex, net_gex=net_gex, tot_gex=tot_gex, color=colr,
                flip=flip, call_wall=call_wall, put_wall=put_wall, up_hw=up_hw, dn_hw=dn_hw,
                ceiling=ceiling, floor=floor, call_grav=call_grav, put_grav=put_grav,
                pin=pin, pin_score=score, pin_label=label, kstar=kstar, in_pos=in_pos)


def gamma_exposure_minis(ch0, signed=True):
    try:
        c = ch0.dropna(subset=["strike", "gamma"])
        if c.empty:
            return None, None
        nv = np.where(c["type"].values == "call", 1.0, -1.0)
        sgn = (c["dsign"].where(c["dsign"].notna(), pd.Series(nv, index=c.index)).values
               if (signed and "dsign" in c.columns) else nv)
        w = c["oi"].fillna(0).values.astype(float)
        expos = float((sgn * c["gamma"].fillna(0).values * w).sum())
        return expos, expos * 2.0
    except Exception:
        return None, None


# ── colour maps, candles, axis ─────────────────────────────────────────
def gex_cmap():
    return mcolors.LinearSegmentedColormap.from_list("gex",
        [(0.0, (0.50, 0, 0)), (0.34, (0.86, 0.06, 0.06)), (0.47, (0.10, 0, 0)),
         (0.50, (0, 0, 0)), (0.53, (0, 0.10, 0)), (0.66, (0.10, 0.74, 0.18)), (1.0, (0.02, 0.42, 0.06))])


def charm_cmap():
    return mcolors.LinearSegmentedColormap.from_list("charm",
        [(0.0, (0.42, 0.24, 0)), (0.34, (0.86, 0.58, 0.02)), (0.47, (0.10, 0.06, 0)),
         (0.50, (0, 0, 0)), (0.53, (0, 0.05, 0.12)), (0.66, (0.12, 0.52, 0.95)), (1.0, (0.02, 0.22, 0.58))])


def heat_cmap():
    return mcolors.LinearSegmentedColormap.from_list("vs3dheat",
        [(0.0, (0.05, 0.07, 0.09)), (0.30, (0.05, 0.22, 0.26)), (0.60, (0.10, 0.50, 0.55)),
         (0.85, (0.22, 0.82, 0.85)), (1.0, (0.85, 0.99, 1.0))])


def decay_cmap():
    return mcolors.LinearSegmentedColormap.from_list("vs3ddecay",
        [(0.0, (0.42, 0.20, 0.75)), (0.42, (0.09, 0.05, 0.14)), (0.50, (0, 0, 0)),
         (0.58, (0.16, 0.10, 0.03)), (1.0, (1.0, 0.62, 0.20))])


def _decay_shift(Z, taus, mins=30):
    n = Z.shape[1]
    if n < 3:
        return np.zeros_like(Z)
    span_min = max((taus[-1] - taus[0]).total_seconds() / 60.0, 1.0)
    step = max(1, int(round(mins / (span_min / max(n - 1, 1)))))
    j2 = np.minimum(np.arange(n) + step, n - 1)
    return Z[:, j2] - Z


def session_window(day):
    return (mdates.date2num(dt.datetime.combine(day, dt.time(9, 30))),
            mdates.date2num(dt.datetime.combine(day, dt.time(16, 0))))


def draw_candles(ax, bars, x0, x1, p_min, p_max):
    if bars is None or not len(bars):
        return
    bn = np.array([mdates.date2num(pd.Timestamp(t).to_pydatetime()) for t in bars["t"]]); inwin = (bn >= x0) & (bn <= x1)
    if not inwin.sum():
        return
    bw = inwin.sum()
    bvis = np.sort(bn[inwin])
    spacing = np.median(np.diff(bvis)) if bw > 1 else (x1 - x0) / 390.0
    cwidth = spacing * 0.8
    halo = [pe.Stroke(linewidth=2.4, foreground="#000000"), pe.Normal()]
    for x, (_, r) in zip(bn[inwin], bars[inwin].iterrows()):
        up = r["c"] >= r["o"]; body = UP if up else DOWN
        ln, = ax.plot([x, x], [r["l"], r["h"]], color=body, lw=1.0, zorder=5); ln.set_path_effects(halo)
        edge = "#000000" if up else "#ff8c00"
        h = max(abs(r["c"] - r["o"]), (p_max - p_min) * 0.0012)
        rect = plt.Rectangle((x - cwidth / 2, min(r["o"], r["c"])), cwidth, h, facecolor=body, edgecolor=edge, lw=0.6, zorder=6)
        rect.set_path_effects([pe.withStroke(linewidth=1.4, foreground="#000000" if up else "#1f2937")])
        ax.add_patch(rect)


def style_time_axis(ax, x0, x1):
    ax.set_autoscalex_on(False)
    ax.margins(x=0)
    ax.set_xlim(x0, x1); ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator())
    ax.tick_params(axis="x", colors=TXT, labelsize=8)


# ── figures (vs3dgbt _render_terrain) ──────────────────────────────────
def terrain_figures(ch, spot, exps, now, day, bars, o, cap_state, peak_pts=()):
    """Build the main terrain figure (+ stacked charm figure).
    o = options dict (greek, weighting, norm, pct, intensity, power, alpha, sat, contours, pockets,
        nblob, strad, levels, voladj, simg, simc, charm2, fieldmode, signed, zoom, p_min, p_max).
    cap_state = per-viewer dict holding the manual caps / history (vs3dgbt session keys).
    peak_pts = [(naive datetime, strike)] — magenta peak-γ rail from stored snapshots.
    Returns (figs, notes)."""
    notes = []
    t_greek = o["greek"]; t_wt = o["weighting"]; t_norm = o["norm"]
    base = "Gamma" if t_greek in (GHEAVY, GDECAY) else t_greek
    kw = dict(greek=base, field_mode=o["fieldmode"], vol_adj=(0.01 if o["voladj"] == "+1%" else 0.0),
              p_min=o["p_min"], p_max=o["p_max"], simulated_gamma=o["simg"], simulated_charm=o["simc"],
              weighting=t_wt, signed=o["signed"])
    pg, Z, taus = terrain_grid(ch, spot, exps, now, day, **kw)
    if t_greek == GHEAVY:
        Z = np.abs(Z)
    elif t_greek == GDECAY:
        Z = _decay_shift(Z, taus)
    capkey = f"terr_cap_{t_greek}_{t_wt}"
    seed = cap_state.get(capkey)
    _sat = float(o["sat"])
    V, used_cap = terrain_scale(Z, t_norm, (seed * _sat if (seed and t_norm == "Manual (fixed cap)") else
                                            (seed if t_norm == "Manual (fixed cap)" else None)), o["pct"])
    if t_norm == "Manual (fixed cap)" and seed is None:
        cap_state[capkey] = 1.2 * float(np.percentile(np.abs(Z), 98)) or 1.0
        V, used_cap = terrain_scale(Z, t_norm, cap_state[capkey] * _sat, o["pct"])
    _p92 = float(np.percentile(np.abs(Z), 92))
    cap_state.setdefault(f"terr_hist_{t_greek}_{t_wt}", []).append(_p92)
    cap_state[f"terr_hist_{t_greek}_{t_wt}"] = cap_state[f"terr_hist_{t_greek}_{t_wt}"][-48:]
    if t_norm == "Manual (fixed cap)" and used_cap:
        _bad = (_p92 > 1.5 * used_cap) or (_p92 < 0.40 * used_cap)
        _ck = f"cap_bad_{t_greek}_{t_wt}"
        cap_state[_ck] = cap_state.get(_ck, 0) + 1 if _bad else 0
        if cap_state[_ck] >= 2:
            _h = cap_state.get(f"terr_hist_{t_greek}_{t_wt}", [])[-24:]
            if _h:
                cap_state[capkey] = 1.3 * float(np.mean(_h)); cap_state[_ck] = 0
                cap_state.setdefault("cap_log", []).append(f"{now:%H:%M} ×{_p92 / used_cap:.1f}")
    if cap_state.get("cap_log"):
        notes.append("cap auto-recalibrated: " + " · ".join(cap_state["cap_log"][-4:]))
    if now.date() != day or now.time() < dt.time(9, 30) or now.time() > dt.time(16, 0):
        notes.append(f"⏸ off-hours: field projected across {day:%a %d %b} 09:30–16:00 from the current chain; "
                     "candles appear live during RTH.")
    Vn_rings = V.copy()
    V = terrain_intensity(V, o["intensity"], power=o["power"], gain=3.0)
    cmap = (charm_cmap() if t_greek == "Charm" else heat_cmap() if t_greek == GHEAVY
            else decay_cmap() if t_greek == GDECAY else gex_cmap())
    plotV = (-V if t_greek == "Charm" else V)
    _vmin = (0.0 if t_greek == GHEAVY else -1.0)
    x0, x1 = session_window(day)
    fig = plt.figure(figsize=(16.5, 7.6), dpi=80, facecolor=DARK)
    gs = fig.add_gridspec(1, 2, width_ratios=[24, 2.2], wspace=0.015)
    ax = fig.add_subplot(gs[0, 0]); axp = fig.add_subplot(gs[0, 1], sharey=ax)
    ax.set_facecolor(DARK); axp.set_facecolor(DARK)
    ax.imshow(plotV, origin="lower", extent=[x0, x1, pg[0], pg[-1]], aspect="auto", cmap=cmap,
              vmin=_vmin, vmax=1, interpolation="bilinear", zorder=0, alpha=o["alpha"])
    if o["contours"]:
        terrain_contours(ax, Z, x0, x1, pg, cap_state.get(capkey))
    if o["pockets"]:
        terrain_pockets(ax, Vn_rings, x0, x1, pg, topn=o["nblob"])
    draw_candles(ax, bars, x0, x1, pg[0], pg[-1])
    ax.axhline(spot, color=WHITE, ls="--", lw=1.0, alpha=.9, zorder=7)
    nowx = mdates.date2num(now) if now.date() == day else x0
    ax.axvline(nowx, color="#3399dd", ls=":", lw=1.1, zorder=7)
    ch0 = ch[ch["exp"] == exps[0]]
    strad = terrain_straddle(ch0, spot)
    if o["strad"] and strad:
        for b in (spot - strad, spot + strad):
            if pg[0] < b < pg[-1]:
                ax.axhline(b, color="#e06ce0", ls=(0, (5, 3)), lw=1.0, alpha=.85, zorder=7)
                ax.text(x1, b, f" {b:.0f}", color="#e06ce0", fontsize=8, va="center", zorder=8)
    if o["levels"]:
        try:
            r = pinak_levels(ch0, spot, exps[0], now)
            _labels = []

            def lvl(v, color, txt, ls, lw):
                if v is None or not (pg[0] < v < pg[-1]):
                    return
                ax.axhline(v, color=color, ls=ls, lw=lw, alpha=.9, zorder=7); _labels.append([v, color, txt])
            lvl(r["pin"], "#FF6600", "PIN", "-", 1.8); lvl(r["flip"], "#0080ff", "FLIP", "-", 1.2)
            lvl(r["call_wall"], "#ff5a3c", "CW", "--", 1.0); lvl(r["put_wall"], "#3ca0ff", "PW", "--", 1.0)
            lvl(r["kstar"], "#cccccc", "K*", "-.", 0.9)
            mg = (pg[-1] - pg[0]) * 0.04; _labels.sort(key=lambda z: z[0]); last = -1e9
            for v, color, txt in _labels:
                y = max(v, last + mg); last = y
                ax.text(x0 + (x1 - x0) * 0.002, y, f"{txt} {v:.0f}", color=color, fontsize=8, va="center", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.2", facecolor=DARK, edgecolor=color, alpha=.85, lw=.6))
        except Exception:
            pass
    jnow = int(np.clip(round((nowx - x0) / (x1 - x0) * (Z.shape[1] - 1)), 0, Z.shape[1] - 1))
    prof = Z[:, jnow]; capv = float(np.percentile(np.abs(prof), 98)) or 1.0
    posc, negc = (("#d9a90b", "#3399dd") if t_greek == "Charm"
                  else ("#39d0d8", "#39d0d8") if t_greek == GHEAVY
                  else ("#ff9f43", "#7a3fd0") if t_greek == GDECAY
                  else ("#22b14c", "#d13438"))
    axp.fill_betweenx(pg, 0, np.clip(prof / capv, -1, 1), where=prof >= 0, color=posc, alpha=.85)
    axp.fill_betweenx(pg, 0, np.clip(prof / capv, -1, 1), where=prof < 0, color=negc, alpha=.85)
    axp.axvline(0, color="#555", lw=.6); axp.axhline(spot, color=WHITE, ls="--", lw=.8, alpha=.8)
    axp.set_xlim(-1, 1); axp.set_xticks([])
    for s_ in ("top", "right", "left", "bottom"):
        axp.spines[s_].set_color(GRID)
    _sgmode = "SIGNED·flow" if (o["signed"] and "dsign" in ch.columns and ch["dsign"].notna().any()) else "naive±"
    pol = ("green = dealers BUY to arrive hedged (supportive) · red = SELL" if t_greek == "Delta Change"
           else "green = +γ suppressive · red = −γ amplifying" if t_greek == "Gamma"
           else "bright = heavy book · direction UNKNOWN by design (roles come from behavior)" if t_greek == GHEAVY
           else "orange = γ BUILDING into the close (pin energy) · purple = fading" if t_greek == GDECAY
           else "gold = dealers must SELL as time passes · blue = must BUY")
    if t_greek == "Gamma":
        try:
            _pts = sorted((t_, vv) for t_, vv in peak_pts if vv is not None and t_.date() == day)
            if _pts:
                _xs = [mdates.date2num(t_) for t_, _ in _pts]; _ys = [vv for _, vv in _pts]
                ax.plot(_xs, _ys, color="#e83e8c", lw=1.5, alpha=.95, zorder=8, solid_capstyle="round")
                ax.plot(_xs[-1], _ys[-1], "o", ms=3.5, color="#e83e8c", zorder=8)
                if len(_ys) >= 2 and abs(_ys[-1] - _ys[-2]) >= 15:
                    ax.text(_xs[-1], _ys[-1] + 2, f"peak jump {_ys[-2]:.0f}→{_ys[-1]:.0f}", color="#e83e8c", fontsize=8, zorder=9)
                ax.text(x1, _ys[-1], " peak γ", color="#e83e8c", fontsize=8, va="center", zorder=9)
            _colx = np.linspace(x0, x1, Z.shape[1])
            _jm = _colx >= nowx
            if _jm.any():
                _py = [float(pg[int(np.argmax(np.clip(Z[:, j], 0, None)))]) for j in np.where(_jm)[0]]
                ax.plot(_colx[_jm], _py, color="#e83e8c", lw=1.1, ls=(0, (2, 2)), alpha=.75, zorder=8)
        except Exception:
            pass
    _hp = ""
    if t_greek == "Gamma":
        _exT, _mnT = gamma_exposure_minis(ch0, o["signed"])
        if _mnT is not None:
            _hp = f" · ≈{_mnT:+,.0f} minis/$1 @spot"
    ax.set_title(f"TERRAIN · {t_greek} · {t_wt} · {_sgmode} · exps {len(exps)} · cap {cap_state.get(capkey, 0):,.0f}"
                 f" · {o['intensity']}({o['power']:g})" + (" · pockets" if o["pockets"] else "") + _hp
                 + f" · α{o['alpha']:.2f}   [{pol}]", color=TXT, fontsize=10.5, loc="left")
    _yt = np.arange(np.ceil(pg[0] / 25) * 25, pg[-1] + 1, 25)
    for _y in _yt:
        ax.axhline(_y, color="#1a2330", lw=0.6, zorder=1)
    ax.set_yticks(_yt)
    ax.tick_params(axis="y", colors="#9fb0c3", labelsize=10.5, length=3)
    axp.yaxis.tick_right()
    axp.set_yticks(_yt)
    plt.setp(axp.get_yticklabels(), visible=True)
    axp.tick_params(axis="y", colors="#9fb0c3", labelsize=9, length=2)
    _tz = float(o.get("zoom", 1.0))
    _zl, _zh = pg[0], pg[-1]
    if _tz < 0.999:
        _hz = (pg[-1] - pg[0]) * _tz / 2.0; _zc = float(spot)
        _zl, _zh = max(pg[0], _zc - _hz), min(pg[-1], _zc + _hz)
    ax.set_ylim(_zl, _zh); axp.set_ylim(_zl, _zh); style_time_axis(ax, x0, x1)
    figs = [fig]
    if o["charm2"] and t_greek != "Charm":
        try:
            kw2 = dict(kw, greek="Charm")
            _, Zc, _ = terrain_grid(ch, spot, exps, now, day, **kw2)
            ck = f"terr_cap_Charm_{t_wt}" + ("_sim" if o["simc"] else "")
            cseed = cap_state.get(ck)
            Vc, c_cap = terrain_scale(Zc, t_norm, cseed if t_norm == "Manual (fixed cap)" else None, o["pct"])
            if t_norm == "Manual (fixed cap)" and cseed is None:
                cap_state[ck] = 1.2 * float(np.percentile(np.abs(Zc), 98)) or 1.0
                Vc, c_cap = terrain_scale(Zc, t_norm, cap_state[ck], o["pct"])
            cap_state.setdefault(f"terr_hist_Charm_{t_wt}", []).append(float(np.percentile(np.abs(Zc), 92)))
            Vc = terrain_intensity(Vc, o["intensity"], power=o["power"], gain=3.0)
            fc = plt.figure(figsize=(16.5, 4.4), dpi=80, facecolor=DARK)
            axc = fc.add_subplot(111); axc.set_facecolor(DARK)
            axc.imshow(-Vc, origin="lower", extent=[x0, x1, pg[0], pg[-1]], aspect="auto",
                       cmap=charm_cmap(), vmin=-1, vmax=1, interpolation="bilinear", zorder=0, alpha=o["alpha"])
            if o["contours"]:
                try:
                    axc.contour(np.linspace(x0, x1, Zc.shape[1]), pg, Zc, levels=[0.0], colors="#e8e8e8",
                                linewidths=1.0, linestyles=(0, (4, 3)), alpha=.9, zorder=6)
                except Exception:
                    pass
            draw_candles(axc, bars, x0, x1, pg[0], pg[-1])
            axc.axhline(spot, color=WHITE, ls="--", lw=1.0, alpha=.9, zorder=7)
            axc.axvline(nowx, color="#3399dd", ls=":", lw=1.1, zorder=7)
            for _y in _yt:
                axc.axhline(_y, color="#1a2330", lw=0.6, zorder=1)
            axc.set_yticks(_yt); axc.tick_params(axis="y", colors="#9fb0c3", labelsize=10.5, length=3)
            axc.set_ylim(_zl, _zh); style_time_axis(axc, x0, x1)
            _cflip = None
            try:
                _pc = Zc[:, jnow]; _zx = np.where(np.diff(np.sign(_pc)) != 0)[0]
                if len(_zx):
                    _cands = pg[_zx]; _cflip = float(_cands[np.argmin(np.abs(_cands - spot))])
                    axc.axhline(_cflip, color="#e8e8e8", ls=(0, (4, 3)), lw=1.1, alpha=.9, zorder=8)
                    axc.text(x0 + (x1 - x0) * 0.002, _cflip, f"charm flip {_cflip:.0f}", color="#e8e8e8", fontsize=8,
                             va="bottom", zorder=9, bbox=dict(boxstyle="round,pad=0.2", facecolor=DARK, edgecolor="#e8e8e8", alpha=.85, lw=.6))
            except Exception:
                pass
            _c5 = ""
            try:
                _cx = ch0.dropna(subset=["strike"]); _Tc = _T_at(exps[0], now); _db = 0.0
                for _ty, _sg2 in (("call", +1), ("put", -1)):
                    _d = _cx[_cx.type == _ty]
                    if _d.empty:
                        continue
                    _Kk = _d["strike"].values.astype(float)
                    _iv = np.where(_d["iv"].fillna(0).values > 0, _d["iv"].fillna(0).values, 0.15)
                    _w = np.where(_d["volume"].fillna(0).values > 0, _d["volume"].fillna(0).values, _d["oi"].fillna(0).values)
                    _db += _sg2 * (_w * bs_charm(spot, _Kk, _Tc, _iv)).sum() * 100
                _c5 = f" · ≈{abs(_db) / (365 * 24 * 12) * 2 / 100:,.0f} minis/5min"
            except Exception:
                pass
            axc.set_title(f"CHARM{' ·sim5m' if o['simc'] else ''} · {t_wt} · {_sgmode} · cap {cap_state.get(ck, 0):,.0f}"
                          + (f" · flip {_cflip:.0f}" if _cflip else "") + _c5 + "   "
                          "[gold = dealers must SELL as time passes · blue = must BUY]", color=TXT, fontsize=10.5, loc="left")
            figs.append(fc)
        except Exception as ex:  # noqa: BLE001
            notes.append(f"charm panel unavailable: {ex}")
    return figs, notes


def peak_strike_of(ch0, spot):
    """Strike holding the snapshot's peak positive signed gamma mass (magenta rail);
    unsigned Σγ·OI argmax when no signs."""
    try:
        c = ch0.dropna(subset=["strike", "gamma"])
        if "dsign" in c.columns and c["dsign"].notna().any():
            nv = np.where(c["type"].values == "call", 1.0, -1.0)
            eff = c["dsign"].where(c["dsign"].notna(), pd.Series(nv * GBT_UNSEEDED_W, index=c.index))
            v = (np.sign(eff) * c["gamma"].fillna(0) * c["oi"].fillna(0)).groupby(c["strike"]).sum()
            if (v > 0).any():
                return float(v.idxmax())
        g = (c["gamma"].fillna(0) * c["oi"].fillna(0)).groupby(c["strike"]).sum()
        if len(g):
            return float(g.idxmax())
    except Exception:
        pass
    return None
