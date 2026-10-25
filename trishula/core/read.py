"""VS3D Market Read: port of vs3dgbt 0.9.79's read_verdict (the cheat-sheet engine),
the _render_read figure (verdict + KEY LEVELS + two glance graphics) and the legacy
_render_signals diagnostics board, driven by the recorder's stored snapshots.

vs3dgbt kept trailing state in session_state (read_gmag, strad_open, open_read);
here every input is recomputed from the snapshots up to the frame time, so a
replayed frame reads exactly as it did live (no repaint).
"""
from __future__ import annotations

import datetime as dt
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .terrain import (DARK, _T_at, _dealer_sign, bs_charm, bs_delta,  # noqa: E402
                      gamma_exposure_minis, pinak_levels, terrain_straddle)


def vs3d_fishbone(c, signed=True):
    sign = _dealer_sign(c, signed)
    w = np.where(c["volume"].fillna(0) > 0, c["volume"].fillna(0), c["oi"].fillna(0))
    net = (np.asarray(sign) * c["gamma"].fillna(0).values * w)
    s = __import__("pandas").Series(net, index=c["strike"].values).groupby(level=0).sum().sort_index()
    v = s.values
    return int(sum(1 for i in range(1, len(v)) if np.sign(v[i]) != np.sign(v[i - 1]) and v[i] != 0))


def vs3d_timing(now):
    t = now.time()
    if t < dt.time(11, 0):
        return "OPEN 9:30-11 · avoid charm (external flow)"
    if t < dt.time(13, 0):
        return "MIDDAY 11-1 · charm building, not dominant"
    if t < dt.time(15, 0):
        return "SWEET SPOT 1:30-3 · best charm signal"
    return "CLOSE 3-4 · gamma asymptotic, pin resolution"


def vs3d_vix_regime(v):
    if v is None:
        return "VIX n/a"
    if v < 16:
        return f"VIX {v:.1f} LOW · charm rules, vanna negligible"
    if v < 20:
        return f"VIX {v:.1f} MID · charm ok, watch vanna"
    return f"VIX {v:.1f} HIGH · vanna can dominate, size down"


def _book_delta_drift(chp0, spot_prev, t_prev, spot_now, t_now, exp):
    c = chp0.dropna(subset=["strike"]); out = 0.0
    Tn = _T_at(exp, t_now); Tp = _T_at(exp, t_prev)
    for typ, sgn in (("call", +1), ("put", -1)):
        d = c[c.type == typ]
        if d.empty:
            continue
        K = d["strike"].values.astype(float)
        iv = np.where(d["iv"].fillna(0).values > 0, d["iv"].fillna(0).values, 0.15)
        w = np.where(d["volume"].fillna(0).values > 0, d["volume"].fillna(0).values, d["oi"].fillna(0).values)
        out += sgn * (w * (bs_delta(spot_now, K, Tn, iv, typ == "call") - bs_delta(spot_prev, K, Tp, iv, typ == "call"))).sum() * 100
    return out


def gmag_at(ch0, spot, e0, now):
    r = pinak_levels(ch0, spot, e0, now)
    return float(np.interp(spot, r["K"], np.abs(r["net_gex"]))) if len(r["K"]) else 0.0


def read_verdict(ch0, spot, e0, now, prev=None, gmag_hist=(), strad_open=None, open_lbl="open", vix=None,
                 signed=True):
    """vs3dgbt read_verdict. prev = (chain, spot, naive datetime) of the previous snapshot."""
    r = pinak_levels(ch0, spot, e0, now)
    gsign = +1 if (r["flip"] is None or spot >= r["flip"]) else -1
    K = r["K"]; gnow = float(np.interp(spot, K, np.abs(r["net_gex"]))) if len(K) else 0.0
    hh = list(gmag_hist) + [gnow]
    pct = float(np.mean(np.array(hh) <= gnow)) * 100 if len(hh) > 2 else 50.0
    env = ("HEAVY γ (top decile — saturated, pinned)" if pct >= 90 else
           "LIGHT γ (bottom quartile — moves come easier)" if pct <= 25 else
           f"NORMAL γ ({pct:.0f}th pctile of session)")
    if gsign < 0:
        env = "NEGATIVE γ side of flip — dealers chase, trend/expansion"
    if prev is not None:
        chp0, sp_prev, t_prev = prev
        hrs = max((now - t_prev).total_seconds() / 3600.0, 1 / 60)
        dbook = _book_delta_drift(chp0, sp_prev, t_prev, spot, now, e0) / hrs
        lean = ("SELL flow (drift down)" if dbook > 0 else "BUY flow (drift up)"); src = "empirical Δδ/Δt"
        flow5 = abs(dbook) / 12.0 * (2 / 100.0)
    else:
        c = ch0.dropna(subset=["strike"]); T = _T_at(e0, now); dbook = 0.0
        for typ, sgn in (("call", +1), ("put", -1)):
            d = c[c.type == typ]
            if d.empty:
                continue
            Kk = d["strike"].values.astype(float)
            iv = np.where(d["iv"].fillna(0).values > 0, d["iv"].fillna(0).values, 0.15)
            w = np.where(d["volume"].fillna(0).values > 0, d["volume"].fillna(0).values, d["oi"].fillna(0).values)
            dbook += sgn * (w * bs_charm(spot, Kk, T, iv)).sum() * 100
        lean = ("SELL flow (drift down)" if dbook > 0 else "BUY flow (drift up)"); src = "model"
        flow5 = abs(dbook) / (365 * 24 * 12) * 2 / 100
    up = lean.startswith("BUY")
    strad_now = terrain_straddle(ch0, spot)
    decay = ("n/a — need open reference" if (not strad_now or not strad_open) else
             "COLLAPSING — very local, pin tightens" if strad_now < 0.45 * strad_open else
             "DECAYING — charm signal live" if strad_now < 0.995 * strad_open else
             "FLAT/REPRICING — stand down (snake-oil check)")
    t = now.time()
    clock = ("OPEN 9:30–11 — external flow, avoid charm" if t < dt.time(11, 0) else
             "MIDDAY 11–1:30 — settling, building" if t < dt.time(13, 30) else
             "SWEET SPOT 1:30–3 — best charm window" if t <= dt.time(15, 0) else
             "CLOSE 3–4 — very local, pin resolution")
    vixline = vs3d_vix_regime(vix) + (" · live (DXLink 5m)" if vix is not None else " · feed unavailable")
    fish = vs3d_fishbone(ch0, signed)
    fishline = ("clean structure" if fish <= 4 else "messy — size down" if fish <= 8 else "FISHBONE — sit out")
    c = ch0.dropna(subset=["strike", "delta"])
    w = np.where(c["oi"].fillna(0) > 0, c["oi"].fillna(0), c["volume"].fillna(0)).astype(float)
    dlt = c["delta"].fillna(0).values; Ks = c["strike"].values
    rem = np.abs(np.where(dlt >= 0, 1 - dlt, -1 - dlt)) * w * 100 / 50.0
    bound = spot + (strad_now or spot * 0.004) * (1 if up else -1)
    mask = (Ks > spot) & (Ks <= bound) if up else (Ks < spot) & (Ks >= bound)
    absorb = float(rem[mask].sum()); swallowed = absorb > 0 and flow5 * 24 > 0 and absorb > flow5 * 24 * 3
    if gsign > 0 and up:
        pat, do = ("CHOP, LEANS UP — grind toward resistance, pin near anchor", "call flies / spreads · sell the target strike")
    elif gsign > 0:
        pat, do = ("CHOP, LEANS DOWN — drift lower but contained, fade extremes", "put flies / spreads · sell the target strike")
    elif up:
        pat, do = ("BULL EXPANSION — squeeze higher, needs a trigger", "long calls / single-leg · never fade the void")
    else:
        pat, do = ("BEAR FLUSH — sell-off/expansion, needs a trigger", "long puts / put flies · never fade the void")
    target = r["pin"]; wall_up = r["call_wall"]; wall_dn = r["put_wall"]
    through = (wall_up if up else wall_dn)
    tension = None
    if target and ((up and target < spot) or ((not up) and target > spot)):
        tension = (f"PIN {target:,.0f} sits {'ABOVE' if target > spot else 'BELOW'} against the charm lean — "
                   "pin-vs-charm tension, respect the weaker read")
        to = spot + (strad_now or spot * 0.004) * (1 if up else -1)
    else:
        to = target if target else spot + (strad_now or spot * 0.004) * (1 if up else -1)
    conf = 50
    conf += 15 if decay.startswith("DECAYING") else (5 if decay.startswith("COLLAPSING") else (-15 if decay.startswith("FLAT") else 0))
    conf += 10 if clock.startswith("SWEET") else (5 if clock.startswith("MIDDAY") else (-10 if clock.startswith("OPEN") else 0))
    conf += (10 if (vix and vix < 16) else -15 if (vix and vix >= 20) else 0)
    conf += -20 if fish > 8 else (-8 if fish > 4 else 0)
    conf += -12 if swallowed else 0
    conf += -10 if gsign < 0 else 0
    if fish > 8:
        conf = min(conf, 25)
    conf = int(max(5, min(95, conf)))
    nxt = (f"expect drift {'UP' if up else 'DOWN'} toward {to:,.0f}" if to else f"expect drift {'UP' if up else 'DOWN'}")
    if gsign > 0:
        rails = [x for x in (wall_up, wall_dn) if x and (not to or abs(x - to) > 1)]
        if rails:
            nxt += ", repelled near " + " / ".join(f"{x:,.0f}" for x in rails)
        if target and to and abs(target - to) <= 1:
            nxt += f", settle ≈ PIN {target:,.0f} into close"
    if gsign < 0:
        nxt += " IF a trigger arrives — without one it floats (γ is a multiplier, not a generator)"
    if swallowed:
        nxt += f" · WARNING: ~{absorb:,.0f} minis of γ absorption in path — pin may land short (profile consumes itself)"
    if tension:
        nxt += "  ·  " + tension
    _ex, _mn = gamma_exposure_minis(ch0, signed)
    if _ex is None:
        gexp = "n/a"
    else:
        _tag = ("NEGLIGIBLE <25 — 'as good as negative' (Dan floor)" if abs(_ex) < 25 else
                "LIGHT <100 — moves come easier (Dan floor)" if abs(_ex) < 100 else "normal by Dan floors")
        gexp = f"≈{_ex:+,.0f} SPX/$1 → {_mn:+,.0f} minis/$1 · {_tag}"
    return dict(gexp=gexp, pat=pat, do=do, env=env, lean=lean + f"  [{src} · ≈{flow5:,.0f} minis/5min proxy]",
                decay=decay, clock=clock, vix=vixline, vix_v=vix, fish=f"{fishline} (score {fish})", fish_n=fish,
                nxt=nxt, conf=conf, through=through, to=to, spot=spot, wall_up=wall_up, wall_dn=wall_dn, pin=target,
                strad=f"${strad_now:.2f}" if strad_now else "n/a", strad_now=strad_now, strad_open=strad_open,
                open_lbl=open_lbl, pinak=r, up=up, gsign=gsign, absorb_up=None)


def read_figure(v, ts_label, card_lines):
    """vs3dgbt _render_read figure: verdict text + KEY LEVELS lines + pattern sketch + day map."""
    BULL = "#22c55e"; BEAR = "#ef4444"; WARN = "#f0a020"; DIM = "#8b949e"; CYAN = "#38bdf8"; WHT = "#e6edf3"
    up = v["up"]
    dirc = BULL if up else BEAR

    def gate_color(txt):
        t = " " + txt.upper()
        if any(k in t for k in ["SELL FLOW", "FISHBONE", "FLAT/REPRICING", "VIX HIGH", " HIGH ·", "OPEN 9:30", "NEGATIVE"]):
            return BEAR
        if any(k in t for k in ["BUY FLOW", "DECAYING", "SWEET", " LOW ·", "CLEAN"]):
            return BULL
        return WARN
    cmap = {"k": WHT, "w": WHT, "g": BULL, "r": BEAR, "c": CYAN, "d": DIM, "y": WARN}
    lines = [(f"SPX {v['spot']:,.2f}   {ts_label} ET   straddle {v['strad']}", WHT, 13, False), ("", WHT, 6, False)]
    lines += [(t, cmap.get(c, c), s, b) for t, c, s, b in card_lines]
    lines.append((("▲ " if up else "▼ ") + v["pat"], dirc, 17, True))
    for i, w in enumerate(textwrap.wrap("NEXT  " + v["nxt"], 96)):
        lines.append((w if i == 0 else "      " + w, dirc if "WARNING" not in w and "tension" not in w else WARN, 12.5, False))
    lines.append(("STRUCTURE  " + v["do"], CYAN, 12.5, False))
    thr = f"{v['through']:,.0f}" if v['through'] else "n/a"; to = f"{v['to']:,.0f}" if v['to'] else "n/a"
    lines.append((f"PLAY  buy through {thr} · sell to {to}", CYAN, 12.5, True))
    lines.append(("", WHT, 6, False))
    cc = BULL if v["conf"] >= 65 else (WARN if v["conf"] >= 40 else BEAR)
    nb = int(round(v["conf"] / 5))
    lines.append((f"CONFIDENCE {v['conf']}/100  " + "█" * nb + "─" * (20 - nb), cc, 14, True))
    lines.append(("", WHT, 6, False))
    for lab, val in [("γ env", v["env"]), ("γ @spot", v.get("gexp", "n/a")), ("charm", v["lean"]), ("straddle", v["decay"]),
                     ("clock", v["clock"]), ("vix", v["vix"]), ("structure", v["fish"])]:
        lines.append((f"  {lab:<10}{val}", gate_color(val), 12, False))
    lines.append(("", WHT, 6, False))
    lines.append(("flips this read: straddle repricing up · VIX spike (vanna over charm) · a test", DIM, 10.5, False))
    lines.append(("breaking AND holding (delta 30→100, new range) · any external trigger", DIM, 10.5, False))
    textH = sum(l[2] for l in lines) * 1.55 / 72 + 0.35; gfxH = 1.9; H = textH + gfxH
    fr = plt.figure(figsize=(13.5, H), dpi=80, facecolor=DARK)
    axr = fr.add_axes([0.0, gfxH / H, 1.0, textH / H]); axr.axis("off"); axr.set_facecolor(DARK)
    y = 1.0
    for txt, col, fs, bold in lines:
        axr.text(0.012, y, str(txt).replace("$", r"\$"), transform=axr.transAxes, color=col, va="top", ha="left",
                 family="monospace", fontsize=fs, fontweight=("bold" if bold else "normal"))
        y -= fs * 1.55 / (textH * 72)
    axl = fr.add_axes([0.015, 0.045, 0.30, (gfxH - 0.35) / H]); axl.set_facecolor("#10151d")
    axl.set_xticks([]); axl.set_yticks([])
    for sp in axl.spines.values():
        sp.set_color("#242c38")
    gpos = "LEANS" in v["pat"]
    xs = np.linspace(0, 1, 13)
    if gpos:
        drift = 0.16 if up else -0.16
        ys = 0.5 + 0.16 * np.array([0, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, 0])[:13] * 0.9 + drift * xs
        axl.axhspan(0.30, 0.70, color=("#12331f" if up else "#331416"), alpha=.5, zorder=0)
        axl.plot(xs, ys, color="#e6edf3", lw=2.0, solid_capstyle="round")
    else:
        ys = (0.18 + 0.64 * xs ** 1.7) if up else (0.82 - 0.64 * xs ** 1.7)
        axl.plot(xs, ys, color=dirc, lw=2.4, solid_capstyle="round")
        axl.plot([0.42], [np.interp(0.42, xs, ys)], marker="o", color=WARN, ms=6)
        axl.text(0.44, np.interp(0.42, xs, ys) + (0.09 if up else -0.13), "trigger", color=WARN, fontsize=8)
        axl.plot([1.0], [ys[-1]], marker=("^" if up else "v"), color=dirc, ms=8)
    axl.set_xlim(0, 1.04); axl.set_ylim(0, 1)
    axl.set_title(("RANGE — fade edges" if gpos else "TREND — needs trigger"), color=("#3fb950" if gpos else dirc),
                  fontsize=9, loc="left", pad=3)
    axm = fr.add_axes([0.365, 0.045, 0.615, (gfxH - 0.35) / H]); axm.set_facecolor("#10151d")
    axm.set_xticks([]); axm.set_yticks([])
    for sp in axm.spines.values():
        sp.set_color("#242c38")
    sp_ = v["spot"]; to = v["to"]; cw = v.get("wall_up"); pw = v.get("wall_dn"); pin = v.get("pin")
    lv = [x for x in (cw, pw, pin, sp_, to) if x]
    ylo, yhi = min(lv), max(lv); pad = max((yhi - ylo) * 0.30, sp_ * 0.0015); axm.set_ylim(ylo - pad, yhi + pad)
    axm.set_xlim(0, 1)
    pin_on_cw = pin and cw and abs(pin - cw) <= 1; pin_on_pw = pin and pw and abs(pin - pw) <= 1
    if cw and not pin_on_cw:
        axm.axhline(cw, color=WARN, lw=1.6); axm.text(0.995, cw, f"UPPER TEST {cw:,.0f} ", color=WARN, fontsize=8.5, ha="right", va="bottom")
    if pw and not pin_on_pw:
        axm.axhline(pw, color=WARN, lw=1.6); axm.text(0.995, pw, f"LOWER TEST {pw:,.0f} ", color=WARN, fontsize=8.5, ha="right", va="top")
    if pin:
        lbl = (f"ANCHOR = UPPER TEST {pin:,.0f} " if pin_on_cw else f"ANCHOR = LOWER TEST {pin:,.0f} " if pin_on_pw else f"ANCHOR {pin:,.0f} ")
        axm.axhline(pin, color="#3b82f6", lw=1.8)
        axm.text(0.995, pin, lbl, color="#3b82f6", fontsize=8.5, ha="right", va=("bottom" if pin >= sp_ else "top"))
    axm.plot([0.10], [sp_], marker="o", color="#e6edf3", ms=7, zorder=5)
    axm.text(0.10, sp_, f"  spot {sp_:,.0f}", color="#e6edf3", fontsize=8.5, va="center")
    if to:
        axm.annotate("", xy=(0.80, to), xytext=(0.13, sp_),
                     arrowprops=dict(arrowstyle="-|>", color=dirc, lw=2.0, connectionstyle="arc3,rad=" + ("-0.08" if to >= sp_ else "0.08")))
        if not [x for x in (cw, pw, pin) if x and abs(x - to) < pad * 0.45]:
            axm.text(0.81, to, f" target {to:,.0f}", color=dirc, fontsize=8.5, va="center", ha="left")
    axm.set_title("the day on one map — tests bound it, anchor holds it", color="#8b949e", fontsize=9, loc="left", pad=3)
    return fr


def signals_board(v, ch0, spot, ts_label, e0, n_snaps, gmag_hist, now):
    """vs3dgbt legacy _render_signals board (§5.1 workflow: straddle → structure → charm gate → absorption)."""
    strad_now, strad_open = v["strad_now"], v["strad_open"]
    decaying = None
    if strad_now and strad_open:
        decaying = strad_now < strad_open * 0.995
    c = ch0.dropna(subset=["strike", "delta"])
    w = np.where(c["oi"].fillna(0) > 0, c["oi"].fillna(0), c["volume"].fillna(0)).astype(float)
    dlt = c["delta"].fillna(0).values; K = c["strike"].values
    rem = np.abs(np.where(dlt >= 0, 1 - dlt, -1 - dlt)) * w * 100 / 50.0
    up = float(rem[(K > spot) & (K <= spot + (strad_now or spot * 0.005))].sum())
    dn = float(rem[(K < spot) & (K >= spot - (strad_now or spot * 0.005))].sum())
    fish = v["fish_n"]; fishtxt = "CLEAN — trade" if fish <= 4 else ("MESSY — size down" if fish <= 8 else "FISHBONE — sit out")
    reg = ""
    if len(gmag_hist):
        cur = gmag_at(ch0, spot, e0, now); avg = float(np.mean(gmag_hist))
        reg = ("HEAVY (γ > 1.5× trailing)" if cur > 1.5 * avg else "LOOSE (γ < 0.5× trailing)" if cur < 0.5 * avg else "NORMAL")
    t = now.time(); win = vs3d_timing(now)
    charm_ok = (decaying is True) and dt.time(13, 30) <= t <= dt.time(15, 0)
    gate = ("OPEN — straddle decaying, in window" if charm_ok else
            "CLOSED — " + ("straddle NOT decaying (snake-oil check)" if decaying is False else
                           "need the open reference" if decaying is None else "outside 1:30–3pm window"))
    r = v["pinak"]

    def f(x):
        return f"{x:,.0f}" if isinstance(x, (int, float)) and x is not None else "n/a"

    def nm(s):
        return str(s).replace("$", "\\$")
    GRN = "#22c55e"; RED = "#ef4444"; GLD = "#f0a020"; DIM = "#8b949e"; WHT = "#e6edf3"; CYN = "#38bdf8"
    vup = v["up"]
    if v["conf"] <= 25 and "FISHBONE" in v["fish"]:
        ban = ("⛔ STAND DOWN", "no trade — structure is whipsaw (fishbone): hedging flips strike to strike", RED)
    elif v["conf"] >= 60:
        ban = (("▲ LEAN LONG" if vup else "▼ LEAN SHORT"),
               f"{v['do']}  ·  target {v['to']:,.0f}" if v.get("to") else v["do"], (GRN if vup else RED))
    elif v["conf"] >= 40:
        ban = ("⚠ SMALL SIZE ONLY", f"{v['do']}  ·  reduced conviction", GLD)
    else:
        blocker = ("straddle not decaying — charm signal is off" if v["decay"].startswith("FLAT")
                   else "open-hour external flow — signal not live yet" if v["clock"].startswith("OPEN")
                   else "VIX high — vanna can steamroll charm" if "HIGH" in v["vix"]
                   else "no reference yet — need the open straddle" if v["decay"].startswith("n/a")
                   else "weak/conflicting gates")
        ban = ("⏸ WAIT", f"inaction is the trade right now — {blocker}", GLD)
    why = []
    if v["conf"] <= 25 and "FISHBONE" in v["fish"]:
        why.append("fishbone structure (BINDING — caps everything else)")
    why.append("charm live" if v["decay"].startswith(("DECAYING", "COLLAPSING")) else "charm off")
    why.append("prime window" if "SWEET" in v["clock"] else ("pin hour" if v["clock"].startswith("CLOSE") else ("open hour" if v["clock"].startswith("OPEN") else "midday")))
    why.append(v["vix"].split(" · ")[0])
    banner_why = "because: " + " · ".join(why) + "    flips if: straddle reprices · VIX spikes · a test breaks & holds"
    path = ("DOWN" if up > dn * 1.4 else "UP" if dn > up * 1.4 else "balanced")
    d_txt, d_col, d_int = (("YES — charm flow is real today", GRN, "decay drips onto dealer books — the drift is live") if decaying
                           else ("NO — repricing/flat", RED, "options not bleeding — ignore charm today") if decaying is False
                           else ("n/a", DIM, "need the open reference"))
    rows = [("sec", "STRADDLE — is the charm signal usable today? (snake-oil check)", CYN),
            ("kv2", "now", (f"${strad_now:.2f}" if strad_now else "n/a"), WHT, f"open ({v['open_lbl']})",
             (f"${strad_open:.2f}" if strad_open else "n/a"), WHT, ""),
            ("kv", "decaying?", d_txt, d_col, d_int),
            ("kv", "range spot±straddle", f"{f(spot - (strad_now or 0))} — {f(spot + (strad_now or 0))}", WHT,
             "the market's own guess for today's travel"),
            ("sec", "STRUCTURE · REGIME · CLOCK — can the signal be trusted right now?", CYN),
            ("kv", "fishbone", f"{fish}  ·  {fishtxt}", (GRN if fish <= 4 else GLD if fish <= 8 else RED),
             ("one-sided book = orderly hedging" if fish <= 4 else "mixed book = degraded signal" if fish <= 8 else "alternating strikes = whipsaw, no edge")),
            ("kv", "gamma regime", reg or "building trailing…", WHT,
             ("tight, pinned tape — fade the edges" if reg.startswith("HEAVY") else "moves travel further than usual" if reg.startswith("LOOSE") else "typical range behavior")),
            ("kv", "window", win, (GRN if "SWEET" in win else GLD),
             ("prime charm hours" if "SWEET" in win else "pin gravity strongest" if win.startswith("CLOSE") else "external flow dominates — wait" if win.startswith("OPEN") else "signal building")),
            ("kv", "CHARM GATE", gate, (GRN if gate.startswith("OPEN") else RED),
             ("all clear — the drift can be leaned on" if gate.startswith("OPEN") else "do NOT trade the charm story while this is closed")),
            ("sec", "DIRECTION — which way is the path of least resistance?", CYN),
            ("kv", "absorption up/down", f"{up:,.0f} / {dn:,.0f} e-mini", WHT, "hedge supply waiting in each direction — thicker side is harder to cross"),
            ("kv", "path", ("▼ DOWN" if path == "DOWN" else "▲ UP" if path == "UP" else "◆ balanced"),
             (RED if path == "DOWN" else GRN if path == "UP" else GLD),
             ("more hedge supply above than below" if path == "DOWN" else "more hedge supply below than above" if path == "UP" else "no edge from absorption"))]
    _pin, _ps = r["pin"], r["pin_score"]
    pin_int = ("no reliable magnet today — don't lean on the pin" if (_ps or 0) < 40 else
               ("▲ magnet ABOVE spot — drift-up pull into the close" if _pin and _pin > spot else
                "▼ magnet BELOW spot — drift-down pull into the close" if _pin and _pin < spot else "at spot — expect stickiness"))
    flip_side = (r["flip"] is None or spot >= r["flip"])
    rows += [("kv", "PIN", f"{f(_pin)}  ·  {r['pin_label']} {_ps}/100", GLD, pin_int),
             ("kv", "FLIP", f"{f(r['flip'])}  ·  spot is {'ABOVE' if flip_side else 'BELOW'}", (CYN if flip_side else RED),
              ("+γ side: chop / mean-revert regime" if flip_side else "−γ side: trend risk — needs a trigger, never fade the void")),
             ("kv2", "CALL WALL", f"{f(r['call_wall'])}" + (f"  (resistance {r['call_wall'] - spot:+,.0f})" if r["call_wall"] else ""), RED,
              "PUT WALL", f"{f(r['put_wall'])}" + (f"  (support {r['put_wall'] - spot:+,.0f})" if r["put_wall"] else ""), GRN, ""),
             ("kv2", "K*", f"{f(r['kstar'])}  (implied fair spot)", WHT, "CEIL / FLOOR", f"{f(r['ceiling'])} / {f(r['floor'])}", WHT, "")]
    rows += [("foot", "cannot measure: dealer long/short (anchor vs test) · MM-on-MM netting · OTC flow — treat as a weighted coin", DIM)]
    fs, axs = plt.subplots(figsize=(16, 7.4), dpi=80, facecolor=DARK); axs.axis("off"); axs.set_facecolor(DARK)
    y = 0.988
    axs.text(0.012, y, f"SPX {spot:,.2f}    {ts_label} ET    expiry {e0}    snapshots {n_snaps}", transform=axs.transAxes,
             color=WHT, va="top", ha="left", family="monospace", fontsize=14, fontweight="bold"); y -= 0.058
    axs.add_patch(mpatches.FancyBboxPatch((0.010, y - 0.088), 0.978, 0.086, boxstyle="round,pad=0.004", transform=axs.transAxes,
                                          facecolor=ban[2], alpha=0.13, edgecolor=ban[2], linewidth=1.4))
    axs.text(0.026, y - 0.012, ban[0], transform=axs.transAxes, color=ban[2], va="top", ha="left", family="monospace", fontsize=16.5, fontweight="bold")
    axs.text(0.300, y - 0.014, nm(ban[1]), transform=axs.transAxes, color=WHT, va="top", ha="left", family="monospace", fontsize=11.5, fontweight="bold")
    axs.text(0.945, y - 0.012, f"{v['conf']}/100", transform=axs.transAxes, color=ban[2], va="top", ha="right", family="monospace", fontsize=15, fontweight="bold")
    axs.text(0.026, y - 0.056, banner_why, transform=axs.transAxes, color=DIM, va="top", ha="left", family="monospace", fontsize=9.5)
    y -= 0.118
    for rw in rows:
        kind = rw[0]
        if kind == "sec":
            y -= 0.010
            axs.text(0.012, y, rw[1], transform=axs.transAxes, color=rw[2], va="top", ha="left", family="monospace", fontsize=10.5, alpha=.95); y -= 0.048
        elif kind == "kv":
            axs.text(0.030, y, rw[1], transform=axs.transAxes, color=DIM, va="top", ha="left", family="monospace", fontsize=11)
            axs.text(0.230, y, nm(rw[2]), transform=axs.transAxes, color=rw[3], va="top", ha="left", family="monospace", fontsize=12, fontweight="bold")
            if len(rw) > 4 and rw[4]:
                axs.text(0.565, y, "→ " + rw[4], transform=axs.transAxes, color=DIM, va="top", ha="left", family="monospace", fontsize=9.5, style="italic")
            y -= 0.046
        elif kind == "kv2":
            axs.text(0.030, y, rw[1], transform=axs.transAxes, color=DIM, va="top", ha="left", family="monospace", fontsize=11)
            axs.text(0.230, y, nm(rw[2]), transform=axs.transAxes, color=rw[3], va="top", ha="left", family="monospace", fontsize=12, fontweight="bold")
            axs.text(0.565, y, rw[4], transform=axs.transAxes, color=DIM, va="top", ha="left", family="monospace", fontsize=11)
            axs.text(0.740, y, nm(rw[5]), transform=axs.transAxes, color=rw[6], va="top", ha="left", family="monospace", fontsize=12, fontweight="bold"); y -= 0.046
        else:
            y -= 0.010
            axs.text(0.012, y, rw[1], transform=axs.transAxes, color=rw[2], va="top", ha="left", family="monospace", fontsize=9.5)
    return fs
