import sys; sys.path.insert(0, "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/l25")
import numpy as np, pandas as pd, time, warnings
from scipy.stats import norm
from pipe import _t, scores, norms
warnings.filterwarnings("ignore")
D = "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/d21/"
T = pd.read_pickle("T21.pkl"); s = pd.read_pickle("spot21.pkl")
cols = T.columns; K = np.array(T.index, float); St = s.reindex(cols, method="nearest").values
mask = np.isfinite(T.values) & (np.abs(K[:, None] - St[None, :]) > 7)
c = pd.read_pickle(D + "candles.pkl"); c = c[c.ts_ms < 2e12]
ch = pd.read_pickle(D + "chain.pkl"); xc = pd.read_pickle(D + "xchain.pkl")
legs = pd.concat([ch[["sym", "exp", "strike", "cp", "oi", "iv"]], xc[["sym", "exp", "strike", "cp", "oi", "iv"]]], ignore_index=True)
legs = legs[(legs.strike >= K[0] - 150) & (legs.strike <= K[-1] + 150)].drop_duplicates("sym").reset_index(drop=True)
legs["oi"] = pd.to_numeric(legs.oi, errors="coerce").fillna(0); legs["iv"] = pd.to_numeric(legs.iv, errors="coerce")
legs["iv"] = legs.iv.where(legs.iv > 0, legs.groupby("exp").iv.transform("median")).fillna(0.18)
o = c[c.sym.str.startswith(".SPXW")].copy(); o["base"] = o.sym.str.split("{").str[0]; o = o[o.base.isin(legs.sym)]
o["t"] = _t(o.ts_ms); o[["bidv", "askv", "volume"]] = o[["bidv", "askv", "volume"]].fillna(0)
mi = pd.date_range("2026-10-20 18:00", cols[-1], freq="1min")
def piv(col, how="sum"):
    return o.pivot_table(index="t", columns="base", values=col, aggfunc=how).reindex(mi).reindex(columns=legs.sym)
vol = piv("volume").fillna(0); ask = piv("askv").fillna(0); bid = piv("bidv").fillna(0)
ivl = piv("imp_vol", "last").ffill()
cpv = legs.cp.values
cum = vol.cumsum().reindex(cols).values; net = (ask - bid).cumsum().reindex(cols).values
bear = np.where(cpv[None, :] == 1, bid.cumsum().reindex(cols).values, ask.cumsum().reindex(cols).values)
bull = np.where(cpv[None, :] == 1, ask.cumsum().reindex(cols).values, bid.cumsum().reindex(cols).values)
oi = np.broadcast_to(legs.oi.values, cum.shape)
W = dict(oi=oi, cum=cum, oicum=oi + cum, net=net, absnet=np.abs(net), bear=bear, bull=bull)
SIDES = dict(sum=np.ones(len(legs)), calls=(cpv == 1) * 1.0, puts=(cpv == -1) * 1.0, c_minus_p=np.where(cpv == 1, 1.0, -1.0))
exps = sorted(legs.exp.unique()); e0 = "2026-10-21"
ESETS = {"0DTE": [e0], "+1DTE": [e0, "2026-10-22"], "+week": [e0, "2026-10-22", "2026-10-23"], "all 6": exps}
names, Wm = [], []
for en, es in ESETS.items():
    inc = legs.exp.isin(es).values * 1.0
    for wn, w in W.items():
        for sn, sv in SIDES.items():
            names.append((en, wn, sn)); Wm.append(w * (inc * sv)[None, :])
Wm = np.stack(Wm, axis=2)                       # time × legs × combos
print("legs", len(legs), "combos", Wm.shape[2], flush=True)
Kl = legs.strike.values; ivs = legs.iv.values
expT = np.array([pd.Timestamp(f"{e} 16:00").value for e in legs.exp], dtype=np.int64)
A = (Kl[None, :] == K[:, None]) * 1.0           # strike aggregation (K × legs)
GN = ["gamma", "vega", "avanna", "adelta", "charm", "one"]
def gk(S, Kx, Tt, iv, cp):
    sq = np.sqrt(Tt); d1 = (np.log(S / Kx) + 0.5 * iv * iv * Tt) / (iv * sq); d2 = d1 - iv * sq; pdf = norm.pdf(d1)
    return [pdf / (S * iv * sq) * S * S / 100, S * pdf * sq / 100, np.abs(pdf * d2 / iv),
            np.abs(np.where(cp == 1, norm.cdf(d1), norm.cdf(d1) - 1)), np.abs(pdf * (-d2 / (2 * Tt))), np.ones_like(d1)]
rows = []; t0 = time.time()
for ivmode in ("snapshot", "live"):
    for kind in ("per-strike", "price-grid"):
        F = np.zeros((len(GN), len(K), len(cols), Wm.shape[2]))
        for j, t in enumerate(cols):
            Tt = np.maximum((expT - pd.Timestamp(t).value) / 1e9 / (365 * 86400), 300 / (365 * 86400))
            iv = ivs if ivmode == "snapshot" else np.where(np.isfinite(ivl.loc[t].values) & (ivl.loc[t].values > 0), ivl.loc[t].values, ivs)
            if kind == "per-strike":
                G = gk(St[j], Kl, Tt, iv, cpv)
                for g in range(len(GN)):
                    F[g, :, j, :] = A @ (G[g][:, None] * Wm[j])
            else:
                G = gk(K[:, None], Kl[None, :], Tt[None, :], iv[None, :], cpv[None, :])
                for g in range(len(GN)):
                    F[g, :, j, :] = G[g] @ Wm[j]
        for g, gn in enumerate(GN):
            for ci, (en, wn, sn) in enumerate(names):
                M = F[g, :, :, ci]
                if not np.isfinite(M).all() or np.nanstd(M) == 0:
                    continue
                for nn, X in norms(M):
                    for sgn in ((1,) if sn != "c_minus_p" and wn != "net" else (1, -1)):
                        sc = scores(sgn * X, T, mask)
                        rows.append((ivmode, kind, gn, en, wn, sn, nn, sgn) + sc)
        print(ivmode, kind, "done", round(time.time() - t0), "s", len(rows), flush=True)
R = pd.DataFrame(rows, columns=["iv", "kind", "greek", "expiries", "weight", "side", "norm", "sign", "overall", "over_time", "across"])
R["combo"] = R.overall + R.over_time
R.to_pickle("R21.pkl")
print(R.sort_values("combo", ascending=False).head(30).round(3).to_string(index=False))
