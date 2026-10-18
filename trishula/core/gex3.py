"""VS3D GEX³: port of vs3dgbt 0.9.79's GEX³ functions (the NIFTY GEX model on three
lenses), used as-is with the data inputs swapped to the tastytrade recorder.

Ported: gex3_lens_rows, gex3_draw_profile, gex3_zone_shade, gex3_model, and the
_render_gex3 figure plus readout. Panel 3 ΔOI = today's settled OI minus the prior
session's, both recorded by the recorder (tastytrade has no OI-change endpoint).
If no prior-day OI was recorded, panel 3 falls back to live volume and says so.
"""
from __future__ import annotations

import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .terrain import DARK, draw_candles, session_window  # noqa: E402

GEX3_MULT = 100.0; GEX3_GRID = 5.0; GEX3_SC = 0.1
GBT_UNSEEDED_W = 0.2


def gex3_lens_rows(ch, sp, exp, lens, doi=None, sign=None):
    try:
        cc = ch[ch["exp"] == exp] if "exp" in getattr(ch, "columns", []) else ch
        if cc is None or not len(cc):
            return None
        nv = np.where(cc["type"].values == "call", 1.0, -1.0)
        _sgn = sign or ("naive" if lens == "naive" else "signed")
        if _sgn == "naive":
            eff = pd.Series(nv, index=cc.index)
        else:
            eff = (cc["dsign"].where(cc["dsign"].notna(), pd.Series(nv * GBT_UNSEEDED_W, index=cc.index))
                   if "dsign" in cc.columns else pd.Series(nv * GBT_UNSEEDED_W, index=cc.index))
        g = cc["gamma"].fillna(0) * GEX3_MULT * float(sp)
        if lens == "doi":
            if doi is None or not len(doi):
                return None
            key = list(zip((cc["strike"] / GEX3_GRID).round() * GEX3_GRID, cc["type"]))
            dmap = {(r.strike, r.type): r.doi for r in doi.itertuples()}
            w = pd.Series([dmap.get(k, 0.0) for k in key], index=cc.index)
        elif lens == "vol":
            w = cc["volume"].fillna(0)
        else:
            w = cc["oi"].fillna(0) + cc["volume"].fillna(0)
        contrib = eff * g * w
        kk = (cc["strike"] / GEX3_GRID).round() * GEX3_GRID
        pos = contrib.clip(lower=0).groupby(kk).sum()
        neg = (-contrib.clip(upper=0)).groupby(kk).sum()
        ks = np.arange(float(min(pos.index.min(), neg.index.min())),
                       float(max(pos.index.max(), neg.index.max())) + GEX3_GRID, GEX3_GRID)
        P = np.array([float(pos.get(k, 0.0)) for k in ks]); N = np.array([float(neg.get(k, 0.0)) for k in ks])
        kern = np.array([0.25, 0.5, 0.25])
        Ps = np.convolve(P, kern, mode="same"); Ns = np.convolve(N, kern, mode="same")
        return pd.DataFrame({"strike": ks, "pos": Ps, "neg": Ns, "net": Ps - Ns, "total": Ps + Ns})
    except Exception:
        return None


def gex3_draw_profile(axp, rows, ylo, yhi, mdl=None, ref_rows=None, width_frac=0.45):
    m = (rows["strike"] >= ylo) & (rows["strike"] <= yhi)
    K = rows["strike"][m].values
    P = rows["pos"][m].values; N = rows["neg"][m].values
    T = (rows["total"][m].values if "total" in rows else P + N)
    if not len(K):
        axp.axis("off")
        return 0.0
    mx = float(max(P.max(), N.max(), T.max() if len(T) else 0.0, 1e-9))
    axp.set_ylim(ylo, yhi)
    axp.set_xlim(mx / max(min(width_frac, 0.60), 0.20), 0.0)
    axp.fill_betweenx(K, 0, P, color="#3fb950", alpha=.22, zorder=2)
    axp.fill_betweenx(K, 0, N, color="#ef5350", alpha=.22, zorder=2)
    axp.plot(P, K, color="#3fb950", lw=1.5, zorder=3)
    axp.plot(N, K, color="#ef5350", lw=1.5, zorder=3)
    if len(T):
        axp.plot(T, K, color="#d4a017", lw=1.9, alpha=.95, zorder=3)
    axp.plot(np.abs(rows["net"][m]), K, color="#e8ecf2", lw=0.9, alpha=.55, zorder=3)
    if ref_rows is not None:
        mr = (ref_rows["strike"] >= ylo) & (ref_rows["strike"] <= yhi)
        if mr.any():
            sc = mx / max(float(max(ref_rows["pos"][mr].max(), ref_rows["neg"][mr].max())), 1e-9)
            axp.plot(ref_rows["pos"][mr] * sc, ref_rows["strike"][mr], color="#3fb950", lw=1.0, ls=":", alpha=.8, zorder=3)
            axp.plot(ref_rows["neg"][mr] * sc, ref_rows["strike"][mr], color="#ef5350", lw=1.0, ls=":", alpha=.8, zorder=3)
    if P.max() > 0:
        iP = int(np.argmax(P)); axp.plot([P[iP]], [K[iP]], marker="^", ms=7, color="#1a7f37", zorder=5)
    if N.max() > 0:
        iN = int(np.argmax(N)); axp.plot([N[iN]], [K[iN]], marker="v", ms=7, color="#c62828", zorder=5)
    if mdl and mdl.get("hhi"):
        for _k, _sh in mdl["hhi"].get("top", [])[:5]:
            if ylo <= _k <= yhi:
                axp.plot([mx * 0.06], [_k], marker="D", ms=4, color="#8b5cf6", zorder=5)
                axp.text(mx * 0.10, _k, f"{_sh * 100:.0f}%", color="#8b5cf6", fontsize=6.5, va="center", ha="left", zorder=5)
    axp.axis("off")
    return mx


def gex3_zone_shade(ax, rows, ylo, yhi, x0, x1):
    m = (rows["strike"] >= ylo) & (rows["strike"] <= yhi)
    K = rows["strike"][m].values; NV = rows["net"][m].values
    if not len(K):
        return
    i = 0
    while i < len(K):
        j = i
        sgn = NV[i] >= 0
        while j + 1 < len(K) and (NV[j + 1] >= 0) == sgn:
            j += 1
        y0 = K[i] - 2.5; y1 = K[j] + 2.5
        ax.axhspan(max(y0, ylo), min(y1, yhi), xmin=0, xmax=1, color=("#22aa22" if sgn else "#ff4444"), alpha=0.045, zorder=0)
        i = j + 1


def gex3_model(rows, spot):
    try:
        ks = rows["strike"].values; net = rows["net"].values
        pos = rows["pos"].values; neg = rows["neg"].values; tot = rows["total"].values
        flip = None; best = 1e18
        for i in range(len(ks) - 1):
            a, b = net[i], net[i + 1]
            if a == 0:
                x = ks[i]
            elif a * b < 0:
                x = ks[i] + (ks[i + 1] - ks[i]) * (-a) / (b - a)
            else:
                continue
            if abs(x - spot) < best:
                best = abs(x - spot); flip = float(x)
        ref = flip if flip is not None else float(spot)
        up = ks > ref; dn = ks < ref
        cw = float(ks[up][np.argmax(pos[up])]) if up.any() and pos[up].max() > 0 else None
        pw = float(ks[dn][np.argmax(neg[dn])]) if dn.any() and neg[dn].max() > 0 else None

        def _grav(side_mask, wall, ratio, side):
            if wall is None:
                return dict(fixed=None, cent=None, med=None)
            fixed = ref + side * ratio * abs(wall - ref)
            m = side_mask & ((pos if side > 0 else neg) > 0)
            w_ = (pos if side > 0 else neg)[m]; k_ = ks[m]
            cent = float((k_ * w_).sum() / w_.sum()) if w_.sum() > 0 else fixed
            order = np.argsort(np.abs(k_ - ref)) if len(k_) else []
            med = fixed
            if len(k_):
                cw_ = np.cumsum(w_[order]); half = 0.5 * w_.sum()
                med = float(k_[order][min(int(np.searchsorted(cw_, half)), len(k_) - 1)]) if w_.sum() > 0 else fixed
            return dict(fixed=float(fixed), cent=cent, med=med)
        gv_c = _grav(up, cw, 0.30, +1); gv_p = _grav(dn, pw, 0.35, -1)
        score = 0.0; pin = None; notes = []
        if flip is not None and spot > flip:
            score += 40; notes.append("pos-γ +40")
        k_g = float(ks[np.argmax(tot)]) if tot.max() > 0 else None
        k_o = float(ks[np.argmax(pos + neg)]) if (pos + neg).max() > 0 else None
        if k_g is not None and k_o is not None:
            gap = abs(k_g - k_o)
            if gap <= 10:
                pin = k_g; score += 25; notes.append("converge +25")
            else:
                wsum = tot[np.argmax(tot)] + (pos + neg)[np.argmax(pos + neg)]
                pin = (k_g * tot[np.argmax(tot)] + k_o * (pos + neg)[np.argmax(pos + neg)]) / max(wsum, 1e-9)
                score += max(0.0, 25 - gap / 2.0); notes.append(f"gap {gap:.0f}")
        spread_c = (max(x for x in gv_c.values() if x is not None) - min(x for x in gv_c.values() if x is not None)) \
            if all(v is not None for v in gv_c.values()) else 99
        spread_p = (max(x for x in gv_p.values() if x is not None) - min(x for x in gv_p.values() if x is not None)) \
            if all(v is not None for v in gv_p.values()) else 99
        if spread_c < 20 and spread_p < 20:
            score += 20; notes.append("consensus +20")
        else:
            score += max(0.0, 20 - (spread_c + spread_p) / 4.0)
        if pin is not None:
            dpct = abs(pin - spot) / spot * 100
            score += 15 if dpct <= 1.0 else max(0.0, 15 - dpct * 5)
            pin = round(pin / GEX3_GRID) * GEX3_GRID
        raw = min(100.0, score)

        def _hhi(v):
            a = np.abs(v); ssum = a.sum()
            return float(((a / ssum) ** 2).sum()) if ssum > 0 else 0.0
        h_t, h_c, h_p = _hhi(tot), _hhi(pos), _hhi(neg)
        regime = ("COMPRESSED" if h_t >= 0.15 else "BALANCED" if h_t >= 0.06 else "DISPERSED")
        mult = {"COMPRESSED": 1.00, "BALANCED": 0.85, "DISPERSED": 0.65}[regime]
        adj = raw * mult

        def _lbl(x):
            return ("STRONG PIN" if x >= 70 else "MODERATE PIN" if x >= 45 else "WEAK PIN" if x >= 25 else "NO PIN")
        top = np.argsort(-np.abs(tot))[:5]
        hhi_top = [(float(ks[i]), float(np.abs(tot[i]) / max(np.abs(tot).sum(), 1e-9))) for i in top]
        upS = ks > spot; dnS = ks < spot
        cmask = upS & (net > 0); fmask = dnS & (net > 0)
        ceil_ = float(ks[cmask][np.argmax((pos * (pos + neg))[cmask])]) if cmask.any() else None
        floor_ = float(ks[fmask][np.argmax((neg * (pos + neg))[fmask])]) if fmask.any() else None

        def _hedge(wall, side):
            if wall is None:
                return None, None
            m = (ks > wall) if side > 0 else (ks < wall)
            if not m.any():
                return None, None
            base = (pos if side > 0 else neg)[m] * (pos + neg)[m]
            vann = base / max(base.max(), 1e-9)
            hp = base * np.exp(-5.0 * np.abs(ks[m] - wall) / max(wall, 1e-9)) * (1.0 + vann)
            hw = float(ks[m][np.argmax(hp)]); gap = abs(hw - wall)
            lab = ("TIGHT" if gap <= 10 else "NORMAL" if gap <= 25 else "WIDE")
            return hw, lab
        uhw, uhl = _hedge(cw, +1); dhw, dhl = _hedge(pw, -1)

        def _dial(v):
            m_ = 2.0 * abs(float(v)); posv = float(v) > 0
            lab = ("HEAVY" if m_ >= 250 else "LIGHT" if m_ >= 100 else "THIN" if m_ >= 25 else "VIRTUALLY-NEG") if posv else "TRUE-NEG"
            return m_, lab, posv
        net_minis = float(net.sum()) / (float(spot) * GEX3_MULT) * GEX3_MULT
        loc = np.abs(ks - ref) <= 30.0
        loc_minis = float(net[loc].sum()) / (float(spot) * GEX3_MULT) * GEX3_MULT if loc.any() else 0.0
        d_all = _dial(net_minis); d_loc = _dial(loc_minis)
        return dict(flip=flip, cw=cw, pw=pw, grav_call=gv_c, grav_put=gv_p,
                    pin=pin, pin_raw=raw, pin_adj=adj, pin_lbl=_lbl(raw), pin_adj_lbl=_lbl(adj),
                    hhi=dict(total=h_t, call=h_c, put=h_p, regime=regime, top=hhi_top),
                    floor=floor_, ceiling=ceil_, uhw=uhw, uhl=uhl, dhw=dhw, dhl=dhl,
                    dial=d_all, dial_local=d_loc, notes=notes)
    except Exception as _e:  # noqa: BLE001
        return dict(err=f"{type(_e).__name__}: {_e}")


def gex3_figure(ch, sp, exp, day, bars, doi, p3_weight, p3_sign, room, width, height, lock_levels=None):
    """vs3dgbt _render_gex3 → (fig, readout [(title, model)], notes)."""
    notes = []
    _l3 = "doi" if (p3_weight.startswith("Δ") and doi is not None and len(doi)) else "vol"
    if p3_weight.startswith("Δ") and _l3 == "vol":
        notes.append("Δ-OI unavailable — the recorder has no prior-session OI yet (it needs one recorded overnight); "
                     "panel 3 fell back to live volume (honest label, not silence).")
    s3 = "signed" if p3_sign.startswith("signed") else "naive"
    panels = [("CONVENTION (naive — assumed dealer sign)", "naive", None),
              ("FLOW-SIGNED (our dsign engine)", "signed", None),
              (f"{'Δ-OI OVERNIGHT (settled, frozen)' if _l3 == 'doi' else 'FRESH PAPER (live volume)'} · {s3} sign", s3, _l3)]
    ylo, yhi = sp * (1 - room), sp * (1 + room)
    fig, axs = plt.subplots(3, 1, figsize=(13, 3 * height), dpi=90, sharex=True, sharey=True)
    fig.patch.set_facecolor(DARK)
    x0, x1 = session_window(day)
    if bars is None or not len(bars):
        notes.append("no price bars for this session yet — profiles only (candles appear during RTH)")
    prep = []
    for ttl, sgn, wov in panels:
        rows = (gex3_lens_rows(ch, sp, exp, wov, doi=doi, sign=sgn) if wov else gex3_lens_rows(ch, sp, exp, sgn))
        prep.append((ttl, sgn, wov, rows, gex3_model(rows, sp) if rows is not None else {"err": "no rows"}))
    ylos, yhis = [], []
    for _, _, _, rows, _ in prep:
        if rows is None:
            continue
        t_ = rows["total"].values; n_ = np.abs(rows["net"].values)
        mk = (t_ > 0.02 * max(float(t_.max()), 1e-9)) | (n_ > 0.02 * max(float(n_.max()), 1e-9))
        if mk.any():
            ylos.append(float(rows["strike"][mk].min())); yhis.append(float(rows["strike"][mk].max()))
    if bars is not None and len(bars):
        ylos.append(float(bars["l"].min())); yhis.append(float(bars["h"].max()))
    if ylos:
        ylo = max(min(ylos) - 15.0, ylo); yhi = min(max(yhis) + 15.0, yhi)
    if yhi <= ylo:
        ylo, yhi = sp * (1 - room), sp * (1 + room)
    rd = []
    for ax, (ttl, sgn, wov, rows, mdl) in zip(axs, prep):
        ax.set_facecolor("#101826"); ax.set_ylim(ylo, yhi)
        rd.append((ttl, mdl))
        ax.set_xlim(x0, x1)
        if rows is not None:
            gex3_zone_shade(ax, rows, ylo, yhi, x0, x1)
        if bars is not None and len(bars):
            draw_candles(ax, bars, x0, x1, ylo, yhi)
        if rows is not None:
            _ref = (gex3_lens_rows(ch, sp, exp, "signed") if wov else None)
            gex3_draw_profile(ax.twiny(), rows, ylo, yhi, mdl=mdl, ref_rows=_ref, width_frac=width)
        if not mdl.get("err"):
            if mdl["flip"] is not None:
                ax.axhline(mdl["flip"], color="#c792ea", lw=1.2, ls="--", zorder=4)
                ax.text(1.001, mdl["flip"], f" flip {mdl['flip']:,.0f}", transform=ax.get_yaxis_transform(),
                        color="#c792ea", fontsize=8, va="center")
            _sh = {"TIGHT": "·T", "NORMAL": "·N", "WIDE": "·W"}
            _gaps = {"uhw": _sh.get(mdl.get("uhl") or "", ""), "dhw": _sh.get(mdl.get("dhl") or "", "")}
            _lbls = []
            for lv, cl, nm, ls_, ex in ((mdl["cw"], "#3fb950", "CW", "-", ""), (mdl["pw"], "#ef5350", "PW", "-", ""),
                                        (mdl["pin"], "#f0ad4e", "PIN", "-", ""),
                                        (mdl.get("ceiling"), "#ff8844", "CEIL", "--", ""), (mdl.get("floor"), "#33cc99", "FLOOR", "--", ""),
                                        (mdl.get("uhw"), "#8b5cf6", "UHW", "-.", _gaps["uhw"]), (mdl.get("dhw"), "#1a7f37", "DHW", "-.", _gaps["dhw"])):
                if lv is not None:
                    ax.axhline(lv, color=cl, lw=1.0 if ls_ != "-" else 1.1, ls=ls_, alpha=.9, zorder=4)
                    _lbls.append([float(lv), cl, f"{nm} {lv:,.0f}{ex}"])
            _lbls.sort(key=lambda t: t[0])
            _min = (yhi - ylo) * 0.024
            for _i in range(1, len(_lbls)):
                if _lbls[_i][0] - _lbls[_i - 1][0] < _min:
                    _lbls[_i][0] = _lbls[_i - 1][0] + _min
            for _i in range(len(_lbls) - 2, -1, -1):
                if _lbls[_i + 1][0] - _lbls[_i][0] < _min:
                    _lbls[_i][0] = _lbls[_i + 1][0] - _min
            for _y, _c, _t in _lbls:
                ax.text(1.001, _y, f" {_t}", transform=ax.get_yaxis_transform(), color=_c, fontsize=7.5, va="center", clip_on=False)
            _hh = mdl["hhi"]
            for _dy, _txt, _col in (
                    (0.000, f"pin {mdl['pin'] if mdl['pin'] is not None else '—'} raw {mdl['pin_raw']:.0f}→adj {mdl['pin_adj']:.0f} ({mdl['pin_adj_lbl']})", "#f0ad4e"),
                    (0.035, f"floor {mdl['floor'] if mdl['floor'] is not None else '—'} · ceil {mdl['ceiling'] if mdl['ceiling'] is not None else '—'}", "#33cc99"),
                    (0.070, f"HHI {_hh['total']:.3f} {_hh['regime']} · local γ {mdl['dial_local'][1]}", "#8b949e")):
                ax.text(0.006, 0.97 - _dy, _txt, transform=ax.transAxes, color=_col, fontsize=6.8, family="monospace",
                        va="top", ha="left", zorder=6, bbox=dict(fc="#0d1117", ec="#3a4150", lw=0.4, alpha=.8, pad=1.8))
            _d = mdl["dial"]
            ax.text(0.995, 0.03, f"γ {_d[1]} {'+' if _d[2] else '−'}{_d[0]:,.0f}", transform=ax.transAxes,
                    color=("#3fb950" if _d[2] else "#ef5350"), fontsize=9, fontweight="bold", ha="right")
        if lock_levels:
            if lock_levels.get("bal"):
                ax.axhline(lock_levels["bal"]["peak"], color="#e8ecf2", lw=0.8, ls=(0, (4, 2, 1, 2)), alpha=.5, zorder=3)
            for _t in (lock_levels.get("ups") or [])[:1]:
                ax.axhline(_t["peak"], color="#3fb950", lw=0.8, ls=(0, (4, 2, 1, 2)), alpha=.5, zorder=3)
            for _t in (lock_levels.get("dns") or [])[:1]:
                ax.axhline(_t["peak"], color="#ef5350", lw=0.8, ls=(0, (4, 2, 1, 2)), alpha=.5, zorder=3)
        ax.set_title(ttl, color="#8b949e", fontsize=9.5, loc="left", pad=2)
        ax.tick_params(colors="#8a93a6", labelsize=7.5, labelbottom=True)
        ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=(0, 30)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        for _sp2 in ax.spines.values():
            _sp2.set_color("#30363d")
        ax.xaxis_date()
    fig.tight_layout(pad=0.6); fig.subplots_adjust(right=0.905, hspace=0.14)
    return fig, rd, notes


def readout_html(rd):
    _n1 = lambda v: f"{v:,.1f}" if v is not None else "—"  # noqa: E731
    _n0 = lambda v: f"{v:,.0f}" if v is not None else "—"  # noqa: E731
    _sp = lambda t, c: f"<span style='color:{c}'>{t}</span>"  # noqa: E731
    LC = {"flip": "#c792ea", "cw": "#3fb950", "pw": "#ef5350", "pin": "#f0ad4e",
          "floor": "#33cc99", "ceil": "#ff8844", "hw": "#8b5cf6", "dim": "#8b949e"}
    html, det = [], []
    for ttl, mdl in rd:
        if mdl.get("err"):
            html.append(f"<div style='color:#ef5350'>{ttl}: {mdl['err']}</div>")
            continue
        _d = mdl["dial"]
        html.append("<div style='margin:2px 0'><b style='color:#e8ecf2'>" + ttl + "</b><br>" + " · ".join((
            _sp(f"flip {_n1(mdl['flip'])}", LC["flip"]),
            _sp(f"CW {_n0(mdl['cw'])}", LC["cw"]),
            _sp(f"PW {_n0(mdl['pw'])}", LC["pw"]),
            _sp(f"PIN {_n0(mdl['pin'])} ({mdl['pin_adj_lbl']})", LC["pin"]),
            _sp(f"FLOOR {_n0(mdl['floor'])}", LC["floor"]),
            _sp(f"CEIL {_n0(mdl['ceiling'])}", LC["ceil"]),
            _sp(f"HW ↑{_n0(mdl['uhw'])}·{(mdl['uhl'] or '—')[:1]} ↓{_n0(mdl['dhw'])}·{(mdl['dhl'] or '—')[:1]}", LC["hw"]),
            _sp(f"γ {_d[1]} {'+' if _d[2] else '−'}{_d[0]:,.0f}", "#3fb950" if _d[2] else "#ef5350"),
        )) + "</div>")
        gc, gp = mdl["grav_call"], mdl["grav_put"]
        det.append(f"{ttl}\n  gravity call FR/CEN/MED {_n0(gc['fixed'])}/{_n0(gc['cent'])}/{_n0(gc['med'])} · "
                   f"put {_n0(gp['fixed'])}/{_n0(gp['cent'])}/{_n0(gp['med'])}\n"
                   f"  pin raw {mdl['pin_raw']:.0f} ({mdl['pin_lbl']}) → HHI-adj {mdl['pin_adj']:.0f} ({mdl['pin_adj_lbl']})\n"
                   f"  HHI tot {mdl['hhi']['total']:.3f} ({mdl['hhi']['regime']}, fixed thresholds — no session history) · "
                   "top: " + ", ".join(f"{k:,.0f} {sh * 100:.0f}%" for k, sh in mdl['hhi']['top']) + "\n"
                   f"  dial whole {mdl['dial'][1]} {mdl['dial'][0]:,.0f} · local(±30) {mdl['dial_local'][1]} {mdl['dial_local'][0]:,.0f}")
    out = ("<div style='font-family:monospace;font-size:12.5px;line-height:1.55'>" + "".join(html)
           + f"<div style='color:{LC['dim']};font-size:11px;margin-top:3px'>K* omitted: §10 needs market premiums; "
           "chain carries model mids (circular). Dealer sign: panel 1 assumed, panels 2-3 inferred — "
           "neither is clearing truth.</div></div>")
    return out, "\n".join(det)


def doi_frame(oi_today: dict, oi_prev: dict, legs: dict) -> pd.DataFrame | None:
    """DataFrame(strike, type, doi) from two recorded OI dicts {sym: oi}."""
    if not oi_today or not oi_prev:
        return None
    rows = []
    for sym, v in oi_today.items():
        if sym in oi_prev and sym in legs and v == v and oi_prev[sym] == oi_prev[sym]:
            ex, k, cp = legs[sym]
            rows.append((round(k / GEX3_GRID) * GEX3_GRID, "call" if cp == 1 else "put", float(v) - float(oi_prev[sym])))
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["strike", "type", "doi"])
    return d.groupby(["strike", "type"], as_index=False)["doi"].sum()


def prev_day_key(oi_log: dict, today: dt.date):
    ks = sorted(k for k in oi_log if k < str(today))
    return ks[-1] if ks else None
