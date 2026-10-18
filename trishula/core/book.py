"""VS3D Book: port of vs3dgbt 0.9.79's book functions, used as-is with the data
inputs swapped from GBT to the tastytrade recorder.

Ported: signed_book_rows, seed_dot_rows, cleanB_rows, netflow_rows,
signed_clusters, package_suspects, _in_band, _strength, dan_levels_from_rows,
key_levels_lines (fly section dropped, since the Book card is simple=True),
method_card_jpg, compute_strip, book_figure, and _book_spot_overlay.

Input frames:
  chain: exp, sym, strike, type ('call'/'put'), gamma, oi, bid, ask, iv, delta, dsign
  dsign table (core.signs.dsign_table): sym, strike, type, seed_net/tot, live_net/tot, seed_dsign
"""
from __future__ import annotations

import datetime as dt
import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

GBT_UNSEEDED_W = 0.2
BG = "#0e1117"


# ── signed rows (vs3dgbt signed_book_rows) ──────────────────────────────
def signed_book_rows(ch, sp, mode="flow", doi=None, units="gex"):
    if ch is None or "dsign" not in getattr(ch, "columns", []):
        return None
    if mode == "flow" and not ch["dsign"].notna().any():
        return None
    cc = ch.copy()
    nv = np.where(cc["type"].values == "call", 1.0, -1.0)
    eff = cc["dsign"].where(cc["dsign"].notna(), pd.Series(nv * GBT_UNSEEDED_W, index=cc.index))
    if units == "contracts":
        if mode == "clean":
            cm2 = doi or {}
            vv2 = np.array([float(cm2.get(float(k), 0.0) or 0.0) for k in cc["strike"]])
            cc["_v"] = vv2 * cc["oi"].fillna(0)
            g2 = cc.groupby("strike", as_index=False).agg(signed_pct=("_v", "sum"))
            g2 = g2[g2["signed_pct"] != 0.0]
            g2["conf"] = 1.0
            return g2[["strike", "signed_pct", "conf"]]
        cc["_v"] = np.sign(eff) * cc["oi"].fillna(0)
        cc["_w"] = cc["oi"].fillna(0)
        cc["_a"] = cc["dsign"].abs().fillna(0) * cc["_w"]
        g2 = cc.groupby("strike", as_index=False).agg(signed_pct=("_v", "sum"), _w=("_w", "sum"), _a=("_a", "sum"))
        g2["conf"] = (g2["_a"] / g2["_w"].replace(0, np.nan)).fillna(0.0)
        return g2[["strike", "signed_pct", "conf"]]
    cc["_v"] = np.sign(eff) * cc["gamma"].fillna(0) * cc["oi"].fillna(0) * 100.0 * sp * sp / 10000.0
    cc["_w"] = cc["oi"].fillna(0)
    cc["_a"] = cc["dsign"].abs().fillna(0) * cc["_w"]
    g = cc.groupby("strike", as_index=False).agg(signed_pct=("_v", "sum"), _w=("_w", "sum"), _a=("_a", "sum"))
    g["conf"] = (g["_a"] / g["_w"].replace(0, np.nan)).fillna(0.0)
    return g[["strike", "signed_pct", "conf"]]


def seed_dot_rows(ch, ds):
    """Flow dot = YESTERDAY'S INFERENCE × today's OI (vs3dgbt seed_dot_rows)."""
    if ch is None or ds is None or ds.empty or not ds["seed_dsign"].notna().any():
        return None
    cc = ch.drop(columns=[c for c in ("dsign",) if c in ch.columns]).copy()
    cc["dsign"] = cc["sym"].map(dict(zip(ds["sym"], ds["seed_dsign"])))
    return signed_book_rows(cc, 0.0, units="contracts")


def _per_strike(ds, which):
    """{strike: {'call': (net, tot), 'put': (net, tot)}} from a dsign table."""
    out = {}
    if ds is None or ds.empty:
        return out
    n = ds["seed_net"] + (ds["live_net"] if which == "all" else 0)
    t = ds["seed_tot"] + (ds["live_tot"] if which == "all" else 0)
    for k, ty, nn, tt in zip(ds["strike"], ds["type"], n, t):
        d = out.setdefault(float(k), {})
        a, b = d.get(ty, (0.0, 0.0))
        d[ty] = (a + float(nn), b + float(tt))
    return out


def cleanB_rows(ds_single, which="seed"):
    """CLEAN-B: net single-leg paper per strike, DEALER view = −(n_call − n_put)."""
    m = _per_strike(ds_single, which)
    rows = []
    for k, v in m.items():
        nc, tc = v.get("call", (0.0, 0.0))
        pc, tp = v.get("put", (0.0, 0.0))
        if (tc + tp) <= 0:
            continue
        rows.append((float(k), -(float(nc) - float(pc)), 1.0))
    return pd.DataFrame(rows, columns=["strike", "signed_pct", "conf"]) if rows else None


def netflow_rows(ds, merged=True):
    """NET FLOW: customer view, + net bought / − net sold, value = n_call − n_put."""
    m = _per_strike(ds, "all" if merged else "seed")
    rows = []
    for k in sorted(m):
        nc, nt = m[k].get("call", (0.0, 0.0))
        pc, pt = m[k].get("put", (0.0, 0.0))
        tot = nt + pt
        if tot <= 0:
            continue
        val = nc - pc
        rows.append((float(k), val, min(1.0, abs(val) / max(tot, 1e-9) * 2.0)))
    return pd.DataFrame(rows, columns=["strike", "signed_pct", "conf"]) if rows else None


def naive_book(ch):
    """Naive per-$1 frame: call_pd / put_pd (calls +, puts −), vs3dgbt 'book'."""
    c = ch.dropna(subset=["gamma"]).copy()
    c["pd"] = np.where(c["type"] == "call", 1.0, -1.0) * c["gamma"] * c["oi"].fillna(0) * 100
    b = c.pivot_table(index="strike", columns="type", values="pd", aggfunc="sum").fillna(0)
    b = b.rename(columns={"call": "call_pd", "put": "put_pd"})
    for col in ("call_pd", "put_pd"):
        if col not in b:
            b[col] = 0.0
    return b.reset_index()


# ── clusters + THE METHOD ──────────────────────────────────────────────
def signed_clusters(rows, lo, hi, min_share=0.05):
    if rows is None or getattr(rows, "empty", True):
        return []
    r = rows[(rows["strike"] >= lo) & (rows["strike"] <= hi)].sort_values("strike").reset_index(drop=True)
    r = r[r["signed_pct"].abs() > 0]
    if r.empty:
        return []
    out = []
    cur = None
    for _, q in r.iterrows():
        k = float(q["strike"]); v = float(q["signed_pct"]); c = float(q.get("conf", 0.5)); s = 1 if v >= 0 else -1
        if cur and s == cur["sign"] and k - cur["last"] <= 10.01:
            cur["ks"].append(k); cur["vs"].append(abs(v)); cur["cs"].append(c); cur["last"] = k
        else:
            if cur:
                out.append(cur)
            cur = dict(sign=s, ks=[k], vs=[abs(v)], cs=[c], last=k)
    if cur:
        out.append(cur)
    tot = sum(sum(c["vs"]) for c in out) or 1.0
    res = []
    for c in out:
        m = sum(c["vs"]); w = np.array(c["vs"]); ks = np.array(c["ks"])
        peak = float(ks[int(np.argmax(w))])
        pmass = float(w.max())
        bars = list(zip([float(x) for x in ks], [float(x) for x in w]))
        conf = float((np.array(c["cs"]) * w).sum() / m)
        share = m / tot
        if share >= min_share:
            res.append(dict(sign=c["sign"], peak=peak, pmass=pmass, mass=m, conf=conf, share=share, bars=bars))
    return res


def package_suspects(rows, spacings=(5, 10, 15, 20, 25)):
    if rows is None or getattr(rows, "empty", True):
        return []
    r = rows[rows["signed_pct"].abs() > 0].sort_values("strike")
    ks = r["strike"].values.astype(float); vs = r["signed_pct"].values.astype(float)
    idx = {k: i for i, k in enumerate(ks)}
    out = []
    for i, a in enumerate(ks):
        for sp in spacings:
            b, c = a + sp, a + 2 * sp
            if b not in idx or c not in idx:
                continue
            va, vb, vc = vs[i], vs[idx[b]], vs[idx[c]]
            if np.sign(va) == np.sign(vc) != np.sign(vb) and np.sign(vb) != 0:
                wings = abs(va) + abs(vc)
                if wings <= 0:
                    continue
                if 0.5 <= abs(vb) / wings <= 3.0 and max(abs(va), abs(vc)) <= 4.0 * max(1e-9, min(abs(va), abs(vc))):
                    out.append(dict(lo=a, body=b, hi=c, sign_body=int(np.sign(vb))))
    out = sorted(out, key=lambda d: (d["lo"], d["hi"]))
    merged = []
    for d in out:
        if merged and d["lo"] <= merged[-1]["hi"]:
            merged[-1]["hi"] = max(merged[-1]["hi"], d["hi"])
        else:
            merged.append(dict(d))
    return merged


def _in_band(K, bands):
    for b in bands:
        if b["lo"] <= K <= b["hi"]:
            return b
    return None


def _strength(share, conf):
    lab = ("Strong" if share >= 0.35 else "Moderate" if share >= 0.18 else "Weak")
    if conf < 0.35:
        lab += "?"
    return lab


def dan_levels_from_rows(rows, ref, S0, WIN_R=2.5, EXT_X=2.0):
    try:
        cl = signed_clusters(rows, ref - 2 * WIN_R * S0, ref + 2 * WIN_R * S0, min_share=0.01)
    except Exception:
        return None
    W = WIN_R * S0
    sh = [c for c in cl if c["sign"] < 0]
    lg = [c for c in cl if c["sign"] > 0 and abs(c["peak"] - ref) <= W]

    def _tests(side):
        cand = [c for c in sh if side * (c["peak"] - ref) > 0]
        inw = [c for c in cand if abs(c["peak"] - ref) <= W]
        mx = max((c["mass"] for c in inw), default=0.0)
        out = []
        if inw:
            big = [c for c in inw if c["mass"] >= 0.20 * mx]
            t1 = dict(min(big, key=lambda c: abs(c["peak"] - ref)))
        elif cand:
            t1 = dict(max(cand, key=lambda c: c["mass"])); t1["ext"] = True
        else:
            return out
        out.append(t1)
        a_in = [c for c in inw if side * (c["peak"] - t1["peak"]) > 0]
        a_out = [c for c in cand if abs(c["peak"] - ref) > W and side * (c["peak"] - t1["peak"]) > 0]
        crz = [c for c in a_out if mx > 0 and c["mass"] >= EXT_X * mx]
        if crz:
            t2 = dict(min(crz, key=lambda c: side * (c["peak"] - ref))); t2["ext"] = True
        elif a_in:
            t2 = dict(max(a_in, key=lambda c: c["mass"]))
        elif a_out:
            t2 = dict(max(a_out, key=lambda c: c["mass"])); t2["ext"] = True
        else:
            t2 = None
        if t2 is not None:
            out.append(t2)
        for c in out:
            if mx > 0 and c["mass"] < 0.20 * mx:
                c["thin"] = True
            _pm = c.get("pmass", 0.0)
            _oth = max([x["mass"] for x in inw if x["peak"] != c.get("wall_at", c["peak"])] + [0.0])
            _cmpr = max(c["mass"] - _pm, _oth)
            if _pm > 0 and _cmpr > 0 and _pm >= 2.5 * _cmpr:
                c["wall_at"] = c["peak"]; c["peak"] = c["peak"] - side * 5.0; c["wall"] = True
        return out
    ups = _tests(+1); dns = _tests(-1)
    u1 = ups[0]["peak"] if ups else None; d1 = dns[0]["peak"] if dns else None
    corr = [c for c in lg if (u1 is None or c["peak"] < u1) and (d1 is None or c["peak"] > d1)]
    bal = max(corr, key=lambda c: c["mass"]) if corr else None
    return dict(bal=bal, ups=ups, dns=dns)


def key_levels_lines(rows, spot, strad_now, WHT, BULL, BEAR, CYAN, DIM, WARN, ref_spot=None, open_strad=None,
                     lock=None, status_prices=None, header_note=None, levels_out=None, seed_rows=None):
    """KEY LEVELS + TAKEAWAYS (vs3dgbt key_levels_lines, rows = flow-signed contracts)."""
    L = [("KEY LEVELS + TAKEAWAYS  (flow-signed candidates — not clearing data)", WHT, 14, True)]
    if header_note:
        L.append((header_note, DIM, 10.5, False))
    _u1 = _d1 = None
    _nobal = None
    if lock:
        bands = lock.get("bands", []); longs = lock.get("longs", [])
        bal = lock.get("bal"); ups = lock.get("ups", []); dns = lock.get("dns", [])
        longs_ext = lock.get("longs_ext", longs)
        half = lock.get("half", spot * 0.009); s0 = lock.get("spot0", spot)
        _u1 = ups[0]["peak"] if ups else None
        _d1 = dns[0]["peak"] if dns else None
        if bal is None and longs_ext:
            _nobal = longs_ext[0]
    else:
        if rows is None:
            L.append(("  needs Signed mode — naive ± cannot define tests/anchors", DIM, 11, False))
            return L
        ref = float(ref_spot) if ref_spot else spot
        WIN_R = 2.5
        EXT_X = 2.0
        WALL_X = 2.5
        S0 = float(open_strad) if open_strad else max(float(strad_now or 0.0), spot * 0.004)
        if S0 <= 0:
            S0 = spot * 0.009
        half = WIN_R * S0
        bands = package_suspects(rows)
        cl = signed_clusters(rows, ref - 2 * WIN_R * S0, ref + 2 * WIN_R * S0, min_share=0.01)
        for c in cl:
            if _in_band(c["peak"], bands):
                c["conf"] *= 0.5

        def _win(c):
            return abs(c["peak"] - ref) <= WIN_R * S0
        longs_ext = sorted([c for c in cl if c["sign"] > 0 and _win(c)], key=lambda c: -c["mass"])
        longs = longs_ext
        shorts = [c for c in cl if c["sign"] < 0]
        if not longs and not [c for c in shorts if _win(c)]:
            L.append(("  no clusters in range — structureless book", DIM, 11, False))
            return L

        def _tests(side):
            _cand = [c for c in shorts if side * (c["peak"] - ref) > 0]
            _inw = [c for c in _cand if _win(c)]
            _mx = max((c["mass"] for c in _inw), default=0.0)
            out = []
            if _inw:
                _big = [c for c in _inw if c["mass"] >= 0.20 * _mx]
                t1 = dict(min(_big, key=lambda c: abs(c["peak"] - ref)))
                if t1.get("bars"):
                    _fb = [(k, v) for k, v in t1["bars"] if v >= 0.20 * t1["pmass"]]
                    if _fb:
                        t1["peak"] = float(min(_fb, key=lambda kv: abs(kv[0] - ref))[0])
            elif _cand:
                t1 = dict(max(_cand, key=lambda c: c["mass"])); t1["ext"] = True
            else:
                return out
            out.append(t1)
            _abv_in = [c for c in _inw if side * (c["peak"] - t1["peak"]) > 0]
            _abv_out = [c for c in _cand if (not _win(c)) and side * (c["peak"] - t1["peak"]) > 0]
            _crazy = [c for c in _abv_out if _mx > 0 and c["mass"] >= EXT_X * _mx]
            _bb = [(k, v, c) for c in _inw for k, v in (c.get("bars") or [])
                   if side * (k - t1["peak"]) > 0 and v >= 0.20 * c.get("pmass", v)]
            if _crazy:
                t2 = dict(min(_crazy, key=lambda c: side * (c["peak"] - ref))); t2["ext"] = True
            elif _bb:
                _k2, _v2, _c2 = max(_bb, key=lambda t: t[1])
                t2 = dict(_c2); t2["peak"] = float(_k2)
            elif _abv_in:
                t2 = dict(max(_abv_in, key=lambda c: c["mass"]))
            elif _abv_out:
                t2 = dict(max(_abv_out, key=lambda c: c["mass"])); t2["ext"] = True
            else:
                t2 = None
            if t2 is not None:
                out.append(t2)
            for c in out:
                if _mx > 0 and c["mass"] < 0.20 * _mx:
                    c["thin"] = True
                _pm = c.get("pmass", 0.0)
                _oth = max([x["mass"] for x in _inw if x["peak"] != c.get("wall_at", c["peak"])] + [0.0])
                _cmpr = max(c["mass"] - _pm, _oth)
                _onpeak = (not c.get("bars")) or any(abs(k - c["peak"]) < 1e-9 and abs(v - _pm) < 1e-9 for k, v in c["bars"])
                if _onpeak and _pm > 0 and _cmpr > 0 and _pm >= WALL_X * _cmpr:
                    c["wall_at"] = c["peak"]; c["peak"] = c["peak"] - side * 5.0; c["wall"] = True
            return out
        ups = _tests(+1); dns = _tests(-1)
        if len(ups) == 2 and not ups[1]["peak"] > ups[0]["peak"]:
            ups = [ups[0]]
        if len(dns) == 2 and not dns[1]["peak"] < dns[0]["peak"]:
            dns = [dns[0]]
        _u1 = ups[0]["peak"] if ups else None
        _d1 = dns[0]["peak"] if dns else None
        _corr = [c for c in signed_clusters(rows, ref - half, ref + half, min_share=0.0)
                 if c["sign"] > 0 and (_u1 is None or c["peak"] < _u1) and (_d1 is None or c["peak"] > _d1)]
        if _corr:
            bal = dict(max(_corr, key=lambda c: c["mass"]))
            bal["stand"] = _standing(seed_rows, bal["peak"])
            _r2 = sorted((c for c in _corr if c["peak"] != bal["peak"]), key=lambda c: -c["mass"])
            bal["r2"] = (dict(_r2[0], stand=_standing(seed_rows, _r2[0]["peak"])) if _r2 else None)
        else:
            bal = None
            _nobal = longs_ext[0] if longs_ext else None
        _exs = [t["peak"] for t in ups + dns if t.get("ext")]
        L.append((f"  range: open {ref:,.0f} ± {WIN_R * S0:,.0f} (2.5×S0) · S0 ${S0:.2f}"
                  + (" [opening straddle]" if open_strad else " [current straddle stand-in]")
                  + (f" · outer test extended to {', '.join(f'{p:,.0f}' for p in _exs)} (≥2× in-window mass)" if _exs else ""),
                  DIM, 10, False))
        s0 = spot
        if isinstance(levels_out, dict) and (bal or ups or dns):
            levels_out["ok"] = True
            levels_out["levels"] = dict(bal=bal, longs=longs, longs_ext=longs_ext, ups=ups, dns=dns,
                                        bands=bands, half=half, spot0=spot)
    _hi = max(status_prices) if status_prices else None
    _lo = min(status_prices) if status_prices else None

    def _status(t_peak, direction):
        if _hi is None:
            return ""
        if direction > 0:
            if _hi > t_peak + 2:
                return " ·CROSSED"
            if _hi >= t_peak - 2:
                return " ·TESTED"
        else:
            if _lo < t_peak - 2:
                return " ·CROSSED"
            if _lo <= t_peak + 2:
                return " ·TESTED"
        return ""
    if bal is None and _nobal is not None:
        L.append((f"NO BALANCE between tests — nothing to anchor. Nearest long {_nobal['peak']:,.0f} "
                  f"sits {'ABOVE UP1' if (_u1 and _nobal['peak'] >= _u1) else 'BELOW DN1' if (_d1 and _nobal['peak'] <= _d1) else 'at the edge'} "
                  f"— DRIFT MAGNET ONLY, not a balance", WHT, 12, True))
    if bal:
        _pk = " ⚠pkg" if _in_band(bal["peak"], bands) else ""
        _off = ""
        if _u1 is not None and bal["peak"] >= _u1:
            _off = f" — above UP TEST {_u1:,.0f}: drift target while it holds"
        elif _d1 is not None and bal["peak"] <= _d1:
            _off = f" — below DN TEST {_d1:,.0f}: drift target while it holds"
        _st = {"standing": " ·standing", "today-only": " ·today-only"}.get(bal.get("stand"), "")
        L.append((f"BALANCE: {bal['peak']:,.0f} ({_strength(bal['share'], bal['conf'])}){_pk}{_off}{_st}", WHT, 13, True))
        _r2 = bal.get("r2")
        if _r2:
            _s2 = {"standing": " ·standing", "today-only": " ·today-only"}.get(_r2.get("stand"), "")
            L.append((f"  2nd long: {_r2['peak']:,.0f}{_s2}", DIM, 10.5, False))
    for b in bands:
        if s0 - half <= b["body"] <= s0 + half:
            _alt = "long mass (their balance)" if b["sign_body"] < 0 else "short mass (their test)"
            L.append((f"⚠ {b['lo']:,.0f}–{b['hi']:,.0f} fly-shaped — tape can't side packages; "
                      f"if customer-owned, {b['body']:,.0f} is the {_alt}", WARN, 10.5, False))

    def _bal_beyond(t_peak, direction, cap=None):
        cands = [c for c in longs_ext if (c["peak"] > t_peak if direction > 0 else c["peak"] < t_peak)]
        if cap is not None:
            seg = [c for c in cands if (c["peak"] < cap if direction > 0 else c["peak"] > cap)]
            if seg:
                cands = seg
        _rad = [c for c in cands if abs(c["peak"] - t_peak) <= max(float(s0 or 0.0), 10.0)]
        if _rad:
            cands = _rad
        elif cands:
            cands = [min(cands, key=lambda c: abs(c["peak"] - t_peak))]
        if cands:
            c = max(cands, key=lambda c: c.get("mass", 0.0))
            return c["peak"], _strength(c["share"], c["conf"])
        return t_peak + direction * 5.0, "thin"

    def ladder(tests, direction, name, col):
        if not tests:
            L.append((f"{name}: none in range", DIM, 11, False))
            return
        hdr = f"{name}: " + " >> ".join(
            f"{t['peak']:,.0f}" + ("ᵂ" if t.get("wall") else "") + ("ᵉˣᵗ" if t.get("ext") else "")
            + ("ᵗʰⁱⁿ" if t.get("thin") else "") + ("⚠" if _in_band(t["peak"], bands) else "")
            + _status(t["peak"], direction) for t in tests)
        L.append((hdr, col, 12.5, True))
        for t in tests:
            if t.get("wall"):
                L.append((f"  ᵂ {t['peak']:,.0f} set 5 in front of the {t['wall_at']:,.0f} wall — hedges engage early", DIM, 10.5, False))
        for i, t in enumerate(tests):
            b, bl = _bal_beyond(t["peak"], direction, cap=(tests[i + 1]["peak"] if i + 1 < len(tests) else None))
            nxt = (f", or extend and test {tests[i + 1]['peak']:,.0f}" if i + 1 < len(tests) else "")
            L.append((f"  Cross {t['peak']:,.0f} = balance ({bl}) at {b:,.0f}{nxt}", WHT, 11.5, False))
    ladder(ups, +1, "UPSIDE TEST", BULL)
    ladder(dns, -1, "DOWNSIDE TESTS", BEAR)
    L.append(("Reject a test = reverse tests/ranges until balance", DIM, 11, False))
    return L


def _standing(seed_rows, k):
    """vs3dgbt seed_standing: is the strike long in yesterday's book too?"""
    if seed_rows is None or getattr(seed_rows, "empty", True):
        return None
    v = seed_rows.loc[seed_rows["strike"] == float(k), "signed_pct"]
    if not len(v):
        return None
    return "standing" if float(v.iloc[0]) > 0 else "today-only"


def method_card_jpg(lines, simple=True):
    _L = list(lines)
    _cut = next((k for k, t in enumerate(_L) if str(t[0]).startswith("Reject a test")), len(_L) - 1)
    _L = _L[:_cut + 1]
    if simple:
        _keep = ("KEY LEVELS", "PREVIEW", "LOCKED", "BALANCE", "NO BALANCE", "UPSIDE", "DOWNSIDE", "Cross ", "Reject a test")
        _L = [t for t in _L if any(str(t[0]).lstrip().startswith(k) for k in _keep)]
        _L = [(str(t[0]).replace(" ·standing", "").replace(" ·today-only", ""), t[1], t[2], t[3]) for t in _L]
    _css = {"k": "#111111", "g": "#1a8f3c", "r": "#c62828", "d": "#666666", "y": "#8a6d00", "c": "#0a7c8c"}
    _f, _a = plt.subplots(figsize=(6.6, 0.32 * len(_L) + 0.5), dpi=150)
    _f.patch.set_facecolor("#ffffff"); _a.axis("off")
    for _i, (_t, _c, _sz, _b) in enumerate(_L):
        _a.text(0.02, 1 - (_i + 0.8) / (len(_L) + 0.6), str(_t), color=_css.get(_c, "#111"),
                fontsize=max(8.0, float(_sz) - 2.5), family="monospace",
                fontweight="bold" if _b else "normal", va="top", ha="left", transform=_a.transAxes)
    buf = io.BytesIO()
    _f.savefig(buf, format="png", facecolor="#ffffff", bbox_inches="tight")
    plt.close(_f)
    return buf.getvalue()


# ── THE STRIP (vs3dgbt compute_strip; history-derived instead of session state) ──
def compute_strip(cc, sp, ts: dt.datetime, charm_hist=(), fuel0=None, strad_tape=(), vix=None):
    """cc = chain of the 0DTE expiry with dsign. ts = naive ET datetime.
    charm_hist: signs of charm_minis on the previous snapshots (oldest→newest).
    fuel0: |fuel_minis| at the first snapshot ≥ 09:30 (None pre-open).
    strad_tape: [(naive ET datetime, ATM both-leg bid sum)] for today's snapshots.
    vix: Series of VIX 5-min closes for today (oldest→newest) or None."""
    nv = np.where(cc["type"].values == "call", 1.0, -1.0)
    eff = (cc["dsign"].where(cc["dsign"].notna(), pd.Series(nv * GBT_UNSEEDED_W, index=cc.index))
           if "dsign" in cc.columns else pd.Series(nv * GBT_UNSEEDED_W, index=cc.index))
    w = cc["oi"].fillna(0); tt = ts.time()
    gam_expo = float((eff * cc["gamma"].fillna(0) * w).sum())
    gam_minis = 2.0 * abs(gam_expo); gam_pos = gam_expo > 0
    gam_dial = ("HEAVY" if gam_minis >= 250 else "LIGHT" if gam_minis >= 100 else
                "THIN" if gam_minis >= 25 else "VIRTUALLY-NEG") if gam_pos else "TRUE-NEG"
    charm_minis, charm_expo = charm_of(cc, sp, ts, eff, w)
    _hist = (list(charm_hist) + [1 if charm_minis > 0 else -1 if charm_minis < 0 else 0])[-6:]
    charm_persist = len(_hist) >= 3 and len(set(_hist[-3:])) == 1 and _hist[-1] != 0
    charm_gate = abs(charm_expo) >= 20
    fuel_minis = fuel_of(cc, sp, eff, w)
    fuel_pct = (100.0 * abs(fuel_minis) / max(float(fuel0), 1e-9)) if (fuel0 and tt >= dt.time(9, 30)) else None
    _sv = atm_bid_straddle(cc, sp)
    _open = dt.datetime.combine(ts.date(), dt.time(9, 30))
    _rth = [(a, b) for a, b in strad_tape if a >= _open and b > 0]
    if tt < dt.time(10, 0) or len(_rth) < 4:
        strad_cls, strad_col = "ARMED (from 10:00)", "#8a93a6"
    else:
        _t16s = dt.datetime.combine(ts.date(), dt.time(16, 0))
        _a0 = _rth[0]

        def _fr(t):
            return max((_t16s - t).total_seconds(), 0) / max((_t16s - _a0[0]).total_seconds(), 1)
        _ratio = float(np.nanmean([b / max(_a0[1] * math.sqrt(_fr(t)), 1e-9) for t, b in _rth[-12:]]))
        if _ratio > 1.10:
            strad_cls, strad_col = "NOT DECAYING — vol bid, charm OFF", "#f0ad4e"
        elif _rth[-1][1] < 8 and _ratio < 0.9:
            strad_cls, strad_col = "COLLAPSING — pin tightens", "#c792ea"
        else:
            strad_cls, strad_col = "DECAYING ✓", "#3fb950"
    vix_txt, vix_col, vix_hi = "VIX n/a", "#8a93a6", False
    if vix is not None and len(vix):
        _vx = pd.Series(vix).reset_index(drop=True); _vl = float(_vx.iloc[-1])
        _vd = _vl - float(_vx.iloc[-7] if len(_vx) > 7 else _vx.iloc[0])
        vix_hi = _vl >= 20
        _vdir = ("spiking — vanna can beat charm" if _vd > 0.5 else "falling — vanna assists" if _vd < -0.3 else "steady")
        vix_txt = f"VIX {_vl:.1f} {_vdir}"
        vix_col = ("#ef5350" if _vd > 0.5 or vix_hi else "#3fb950" if _vd < -0.3 else "#e8ecf2")
    window = ("PRE-OPEN" if tt < dt.time(9, 30) else "ACTIVE OPEN — levels are bid levels" if tt < dt.time(11, 0)
              else "MIDDAY — settling" if tt < dt.time(13, 30) else "SWEET SPOT — charm turf" if tt < dt.time(15, 0)
              else "CLOSE — local, pin" if tt < dt.time(16, 0) else "AFTER HOURS")
    win_col = {"PRE": "#8a93a6", "ACT": "#f0ad4e", "MID": "#e8ecf2", "SWE": "#3fb950", "CLO": "#c792ea", "AFT": "#8a93a6"}[window[:3]]
    _cup = charm_minis > 0
    if tt < dt.time(9, 30) or tt >= dt.time(16, 0):
        play, play_col = "Outside RTH — strip informational only", "#8a93a6"
    elif vix_hi:
        play, play_col = "VIX 20+ — vanna can overpower charm · size down or sit out", "#ef5350"
    elif strad_col == "#f0ad4e":
        play, play_col = ("STRADDLE NOT DECAYING while CHARM " + ("UP" if _cup else "DOWN")
                          + " — vol bid rules the tape · charm plays OFF · stand down"), "#f0ad4e"
    elif not charm_gate:
        play, play_col = "Charm expo <20 — no directional lean · position-layer (ladder) only", "#8a93a6"
    elif tt < dt.time(11, 0):
        play, play_col = "Active open — expect tests engaged, signals gated until ~11:00", "#f0ad4e"
    else:
        play, play_col = (("Chop leans UP — pin near anchor · sell flies/spreads at target" if _cup
                           else "Chop leans DOWN — fade extremes · put flies/spreads") if gam_pos else
                          ("BULL EXPANSION — needs a trigger · long calls single-leg" if _cup
                           else "BEAR FLUSH — needs a trigger · long puts / put flies")), ("#3fb950" if _cup else "#ef5350")
    chips = [(f"γ{'+' if gam_pos else '−'} {gam_dial} {gam_minis:,.0f}m/$", "#3fb950" if gam_pos else "#ef5350"),
             (f"FUEL {'BUY' if fuel_minis > 0 else 'SELL'} {abs(fuel_minis):,.0f}m"
              + (f" ({fuel_pct:.0f}%)" if fuel_pct is not None else " (baseline @09:30)"),
              "#2fd0d0" if (fuel_pct is None or fuel_pct >= 15) else "#f0ad4e"),
             (f"CHARM {'↑' if _cup else '↓'}{abs(charm_minis):,.0f}m/5m"
              + ("" if charm_gate else " ✗<20") + (" ✓pers" if charm_persist else ""),
              ("#3fb950" if _cup else "#ef5350") if charm_gate else "#8a93a6"),
             ((f"STRADDLE {_sv:.0f}: {strad_cls}" if _sv > 0 else f"STRADDLE n/a: {strad_cls}"), strad_col),
             (vix_txt, vix_col), (window, win_col)]
    return dict(chips=chips, play=(play, play_col), gam_minis=gam_minis, gam_pos=gam_pos,
                charm_minis=charm_minis, fuel_minis=fuel_minis, straddle=_sv)


def charm_of(cc, sp, ts, eff, w):
    _t16 = dt.datetime.combine(ts.date(), dt.time(16, 0))
    _Ty = max((_t16 - ts).total_seconds(), 60) / (365 * 24 * 3600)

    def _charm5m(K, iv):
        if iv <= 0 or _Ty <= 0 or K <= 0 or not sp > 0:
            return 0.0
        sq = math.sqrt(_Ty); d1 = (math.log(sp / K) + (0.05 + 0.5 * iv * iv) * _Ty) / (iv * sq); d2 = d1 - iv * sq
        ch_yr = -math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * (2 * 0.05 * _Ty - d2 * iv * sq) / (2 * _Ty * iv * sq)
        return ch_yr / (365 * 24 * 12)
    _cch = [_charm5m(float(k), float(v) if v == v else 0.0) for k, v in zip(cc["strike"], cc["iv"])]
    charm_expo = float((eff * pd.Series(_cch, index=cc.index) * w).sum())
    return -2.0 * charm_expo, charm_expo


def fuel_of(cc, sp, eff, w):
    _dnow = cc["delta"].fillna(0)
    _term = np.where(cc["type"].values == "call",
                     np.where(cc["strike"].values < sp, 1.0, 0.0),
                     np.where(cc["strike"].values > sp, -1.0, 0.0))
    return -2.0 * float((eff * w * (pd.Series(_term, index=cc.index) - _dnow)).sum())


def atm_bid_straddle(cc, sp):
    _pv = cc.pivot_table(index="strike", columns="type", values="bid", aggfunc="max")
    _pv = _pv.dropna() if len(_pv) else _pv
    if len(_pv):
        _pv = _pv[(_pv > 0).all(axis=1)]
    if not len(_pv) or not sp == sp:
        return 0.0
    _K = float(_pv.index[np.argmin(np.abs(_pv.index.values - sp))])
    return float(np.nan_to_num(_pv.loc[_K].sum()))


def mid_straddle(cc, ref):
    """ATM (nearest 5 to ref) call+put mid — terrain_straddle analogue."""
    if cc is None or cc.empty or not ref == ref:
        return None
    k = cc.loc[(cc["strike"] - ref).abs().idxmin(), "strike"]
    legs = cc[cc["strike"] == k]
    mids = ((legs["bid"] + legs["ask"]) / 2).dropna()
    return float(mids.sum()) if len(mids) == 2 else None


# ── the figure (vs3dgbt book_figure) ───────────────────────────────────
def book_figure(book, spot, straddle, lo, hi, side="Total", openb=None, signed=None, signed_open=None,
                sticks=True, signmode="flow", lock_levels=None, open_levels=None, preview_levels=None,
                intraday_levels=None, show_delta=False, lock_suffix=""):
    def _tx(v):
        return v
    fig, ax = plt.subplots(figsize=(6.5, 9))
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    _legend_force = False
    if signed is not None and len(signed):
        sg = signed[(signed["strike"] >= lo) & (signed["strike"] <= hi)].reset_index(drop=True)
        if signmode.startswith("clean"):
            _pal = ("#1e90ff", "#ff00ff")
        elif signmode.startswith("net"):
            _pal = ("#1e90ff", "#ffd600")
        else:
            _pal = ("#26a69a", "#ef5350")
        for _, r in sg.iterrows():
            v = _tx(float(r["signed_pct"]))
            ax.barh(float(r["strike"]), v, height=3.6, zorder=3, color=(_pal[0] if v >= 0 else _pal[1]),
                    alpha=0.35 + 0.6 * min(1.0, float(r.get("conf", 0.5))))
        if signmode.startswith("net"):
            ax.set_xlabel("NET FLOW · net PAPER contracts — PARTICIPANT VIEW: + net bought (blue) / − net sold "
                          "(yellow) · dot = yesterday-final · no OI, no γ", color="#aaa", fontsize=8)
        elif signmode.startswith("clean"):
            ax.set_xlabel("CLEAN-B · net SINGLE-LEG paper, DEALER view — blue = dealer bought / magenta = "
                          "dealer sold · dot = yesterday-final · no OI", color="#aaa", fontsize=8)
        else:
            ax.set_xlabel("FLOW-SIGNED · dealer NET CONTRACTS — inferred sign × OI (opacity = confidence · "
                          "moves only on sign flips + overnight OI)", color="#aaa", fontsize=8)
        _cur = {float(r["strike"]): _tx(float(r["signed_pct"])) for _, r in sg.iterrows()}

        def _sg_map(df):
            if df is None or getattr(df, "empty", True):
                return None
            d = df[(df["strike"] >= lo) & (df["strike"] <= hi)]
            return {float(r["strike"]): _tx(float(r["signed_pct"])) for _, r in d.iterrows()}
        _op = _sg_map(signed_open)
        if sticks and _op:
            for k, ov in _op.items():
                cv = _cur.get(k, 0.0)
                if ov * cv > 0 and abs(ov) > abs(cv):
                    ax.barh(k, ov - cv, left=cv, height=0.9, color="#9aa5b1", alpha=0.45, zorder=2)
        if _op:
            ax.scatter(list(_op.values()), list(_op.keys()), s=14, color="#6f9bd1", zorder=4, label="market open (seed)")
            _legend_force = True
    else:
        b = book.copy(); b = b[(b["strike"] >= lo) & (b["strike"] <= hi)]
        c = b["call_pd"].fillna(0) / 50.0; p = b["put_pd"].fillna(0) / 50.0; ks = b["strike"].values
        if side == "Calls":
            vals = c.values; cols = ["#26a69a"] * len(ks)
        elif side == "Puts":
            vals = p.values; cols = ["#ef5350"] * len(ks)
        else:
            vals = (c + p).values; cols = ["#26a69a" if v >= 0 else "#ef5350" for v in vals]
        ax.barh(ks, _tx(np.asarray(vals, float)), height=3.6, color=cols, alpha=0.9, zorder=3)
        if openb is not None and not getattr(openb, "empty", True):
            o = openb[(openb["strike"] >= lo) & (openb["strike"] <= hi)]
            oc = o["call_pd"].fillna(0) / 50.0; op = o["put_pd"].fillna(0) / 50.0
            ov = oc.values if side == "Calls" else (op.values if side == "Puts" else (oc + op).values)
            if sticks:
                _cur = {float(k): _tx(float(v)) for k, v in zip(ks, vals)}
                for k, x in zip(o["strike"].values, _tx(np.asarray(ov, float))):
                    cv = _cur.get(float(k), 0.0)
                    if x * cv > 0 and abs(x) > abs(cv):
                        ax.barh(float(k), x - cv, left=cv, height=0.9, color="#9aa5b1", alpha=0.45, zorder=2)
            ax.scatter(_tx(np.asarray(ov, float)), o["strike"].values, s=14, color="#6f9bd1", zorder=4, label="market open")
            _legend_force = True
        ax.set_xlabel("e-minis per $1 (naive calls+ / puts−)", color="#aaa", fontsize=8)
    ax.axhline(spot, color="w", lw=0.9, ls="--", alpha=0.8)
    ax.text(ax.get_xlim()[1], spot, f" {spot:.2f}", color="w", va="center", fontsize=8)
    if straddle:
        for yy, tag in ((spot + straddle, f"+{straddle:.2f}"), (spot - straddle, f"-{straddle:.2f}")):
            ax.axhline(yy, color="#c084fc", lw=0.9, ls=":", alpha=0.9)
            ax.text(ax.get_xlim()[1], yy, f" {yy:.2f} ({tag})", color="#c084fc", va="center", fontsize=7)
    ax.axvline(0, color="#666", lw=0.8)
    ax.tick_params(colors="#aaa", labelsize=7)
    for _sp in ax.spines.values():
        _sp.set_color("#333")
    if _legend_force:
        ax.legend(loc="lower right", fontsize=7, facecolor=BG, labelcolor="#ccc")
    ax.set_ylim(lo, hi)
    from matplotlib.ticker import MultipleLocator
    ax.yaxis.set_major_locator(MultipleLocator(10))
    try:
        import matplotlib.transforms as _mt
        _tr = _mt.blended_transform_factory(ax.transAxes, ax.transData)
        _placed = []

        def _place(y):
            _gap = (hi - lo) * 0.02
            for _slot in range(4):
                if not any(abs(y - _py) < _gap and _ps == _slot for _py, _ps in _placed):
                    _placed.append((y, _slot))
                    return _slot
            _placed.append((y, 4))
            return None

        def _line(y, lab, col, ls, alpha=0.85):
            try:
                y = float(y)
            except Exception:
                return
            if y and lo < y < hi:
                ax.axhline(y, color=col, lw=1.0, ls=ls, alpha=alpha, zorder=5)
                _s = _place(y)
                if _s is None:
                    return
                _x, _ha = ((0.995, "right") if _s in (0, 2) else (0.005, "left"))
                _va = ("bottom" if _s in (0, 1) else "top")
                ax.text(_x, y, f"{lab} {y:,.0f}", transform=_tr, ha=_ha, va=_va, fontsize=8, color=col, zorder=7,
                        bbox=dict(fc=BG, ec=col, lw=0.6, pad=1.5))
        _drew = False
        if isinstance(lock_levels, dict):
            if lock_levels.get("bal"):
                _line(lock_levels["bal"]["peak"], "BALANCE" + lock_suffix, "#e8ecf2", (0, (6, 3)))
            for _t in lock_levels.get("ups", []):
                _line(_t["peak"], "UP TEST" + lock_suffix, "#3fb950", (0, (5, 3)))
            for _t in lock_levels.get("dns", []):
                _line(_t["peak"], "DN TEST" + lock_suffix, "#ef5350", (0, (5, 3)))
            _drew = True
        if isinstance(open_levels, dict) and not _drew:
            if open_levels.get("bal"):
                _line(open_levels["bal"]["peak"], "BAL (open)", "#e8ecf2", (0, (4, 2, 1, 2)), alpha=0.5)
            for _t in open_levels.get("ups", [])[:1]:
                _line(_t["peak"], "UP (open)", "#3fb950", (0, (4, 2, 1, 2)), alpha=0.5)
            for _t in open_levels.get("dns", [])[:1]:
                _line(_t["peak"], "DN (open)", "#ef5350", (0, (4, 2, 1, 2)), alpha=0.5)
            _drew = True
        if (not _drew) and preview_levels:
            if preview_levels.get("bal"):
                _line(preview_levels["bal"]["peak"], "BALANCE (preview)", "#e8ecf2", (0, (2, 3)), alpha=0.55)
            for _t in preview_levels.get("ups", []):
                _line(_t["peak"], "UP TEST (preview)", "#3fb950", (0, (2, 3)), alpha=0.55)
            for _t in preview_levels.get("dns", []):
                _line(_t["peak"], "DN TEST (preview)", "#ef5350", (0, (2, 3)), alpha=0.55)
            ax.text(0.005, 0.02, "PREVIEW — yesterday's book · locks 09:35 ET", transform=ax.transAxes,
                    ha="left", va="bottom", fontsize=8, color="#8a93a6", zorder=7)
            _drew = True
        if not _drew:
            ax.text(0.005, 0.02, "card levels lock at 09:35 ET", transform=ax.transAxes,
                    ha="left", va="bottom", fontsize=8, color="#8a93a6", zorder=7)
        if show_delta and intraday_levels:
            if intraday_levels.get("bal"):
                _line(intraday_levels["bal"]["peak"], "BAL Δ", "#ff9f1a", (0, (3, 2)), alpha=0.85)
            for _t in intraday_levels.get("ups", []):
                _line(_t["peak"], "UPΔ", "#ff9f1a", (0, (3, 2)), alpha=0.6)
            for _t in intraday_levels.get("dns", []):
                _line(_t["peak"], "DNΔ", "#ff9f1a", (0, (3, 2)), alpha=0.6)
    except Exception as e:  # noqa: BLE001
        ax.text(0.005, 0.05, f"⚠ levels overlay error: {type(e).__name__}: {e}", transform=ax.transAxes,
                ha="left", va="bottom", fontsize=8, color="#ef5350", zorder=9)
    fig.tight_layout()
    return fig


def book_spot_overlay(fig, bars, x0, x1):
    """White intraday spot path over the book, session time along the top.
    bars: DataFrame(t = naive ET datetime, c = close)."""
    import matplotlib.dates as _md
    ax = fig.axes[0]
    fig.set_size_inches(11.0, 12.0)
    ax2 = ax.twiny(); ax2.set_ylim(ax.get_ylim()); ax2.set_facecolor("none")
    if bars is not None and len(bars):
        ax2.plot(pd.to_datetime(bars["t"]), pd.to_numeric(bars["c"], errors="coerce"),
                 color="white", lw=1.5, alpha=0.95, zorder=6)
    ax2.set_xlim(x0, x1)
    ax2.xaxis.set_major_formatter(_md.DateFormatter("%H:%M"))
    ax2.tick_params(colors="#8a93a6", labelsize=8)
    for s in ax2.spines.values():
        s.set_visible(False)
    return fig


def fig_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
