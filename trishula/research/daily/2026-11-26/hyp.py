"""Pre-registered 25 Nov (RESEARCH_LOG §22): H4 fade biggest orders (1 in 10,000 per half-hour, prior days' cut),
H5 PM sold calls >=20 lots follow, H6 AM bought puts >=20 lots fade, + AM bought calls >=20 follow; all at 20 min,
order definitions exactly as research/unusual/uo.py (single-leg 0DTE, BUY/SELL side, same contract/side/second,
print delta, 'paid' = at or through the quote). Edge per day = mean(fwd x dir) - mean(fwd x dir of all orders that day
in that direction). In-sample 12-24 Nov, OUT OF SAMPLE from 25 Nov. Forward SPX = lean-file 1-min (no forward fill).
Also N5 (SPY sweep proxy) per prereg.txt and the random-entry cost baseline for the call log."""
import sys; sys.path.insert(0, sys.argv[1]); from common import *
ET = 'America/New_York'
lean = {d['day']: d for d in days()}
rng = np.random.default_rng(3)


def pxpath(day):
    sp = pd.DataFrame(lean[day]['spx'], columns=['m', 'o', 'h', 'l', 'c']).drop_duplicates('m', keep='last')
    t = pd.to_datetime(sp.m, unit='ms', utc=True).dt.tz_convert(ET)
    mm = (t.dt.hour * 60 + t.dt.minute).values
    return pd.Series(sp.c.values, index=mm).groupby(level=0).last().reindex(range(570, 961))


O = {}; SW = []; RB = []
for day, z in ZIPS.items():
    Z = f"{S}/data/{z}/"
    p = pd.read_parquet(Z + "prints.parquet", columns=["ts_ms", "sym", "exp", "cp", "strike", "aggr_side", "size", "px", "bid", "ask", "delta", "spot", "spread_leg", "valid"])
    px = pxpath(day)
    q = p[(p.exp.astype(str) == day) & p.valid.astype(bool) & (~p.spread_leg.fillna(False).astype(bool)) & p.aggr_side.isin(["BUY", "SELL"])]
    t = pd.to_datetime(q.ts_ms, unit="ms", utc=True).dt.tz_convert(ET); m = t.dt.hour * 60 + t.dt.minute
    q = q[(m >= 570) & (m < 960)].copy(); q["m"] = m[q.index]
    q["paid"] = np.where(q.aggr_side == "BUY", q.px >= q.ask, q.px <= q.bid); q["sec"] = q.ts_ms // 1000
    o = q.groupby(["sym", "aggr_side", "sec"]).agg(m=("m", "first"), cp=("cp", "first"), size=("size", "sum"),
                                                    d=("delta", lambda x: np.nanmean(np.abs(x)) if x.notna().any() else np.nan), S=("spot", "first"),
                                                    paid=("paid", "max")).reset_index()
    o["d"] = o.d.fillna(0.3); o["dn"] = o.d * o["size"] * 100 * o.S
    o["dir"] = np.where((o.aggr_side == "BUY") == (o.cp > 0), 1, -1); o["b"] = ((o.m - 570) // 30).clip(0, 12)
    for h in (10, 20, 30):
        o[f"f{h}"] = (px.reindex(o.m + h).values - px.reindex(o.m).values) * o.dir
    O[day] = o
    # ---- random-entry cost baseline: 1DTE call/put one strike ITM, bought at the ask, sold at the bid 30 min later.
    pe = p[(p.exp.astype(str) > day) & p.valid.astype(bool)]
    if len(pe):
        e1 = sorted(pe.exp.astype(str).unique())[0]
        pe = pe[pe.exp.astype(str) == e1].copy()
        te = pd.to_datetime(pe.ts_ms, unit="ms", utc=True).dt.tz_convert(ET); pe["m"] = (te.dt.hour * 60 + te.dt.minute).values
        pe = pe[(pe.m >= 570) & (pe.m < 960) & (pe.bid > 0) & (pe.ask > pe.bid)]
        last = pe.sort_values("ts_ms").groupby(["sym", "m"]).agg(bid=("bid", "last"), ask=("ask", "last"), K=("strike", "first"), cp=("cp", "first"))
        mins = [x for x in range(585, 930) if np.isfinite(px.get(x, np.nan)) and np.isfinite(px.get(x + 30, np.nan))]
        for mi in rng.choice(mins, min(150, len(mins)), replace=False):
            s0 = px[mi]; cp = 1 if rng.random() < .5 else -1
            K = (np.floor(s0 / 5) * 5) if cp > 0 else (np.ceil(s0 / 5) * 5)        # first strike ITM
            sym = f".SPXW{pd.Timestamp(e1).strftime('%y%m%d')}{'C' if cp > 0 else 'P'}{int(K)}"
            try:
                a = last.loc[sym]
            except KeyError:
                continue
            a0 = a[(a.index <= mi) & (a.index >= mi - 5)]; a1 = a[(a.index <= mi + 30) & (a.index >= mi + 25)]
            if len(a0) and len(a1):
                RB.append(dict(day=day, buy=a0.ask.iloc[-1], sell=a1.bid.iloc[-1], spread=a0.ask.iloc[-1] - a0.bid.iloc[-1],
                               move=(px[mi + 30] - s0) * cp))
    # ---- N5 SPY sweeps
    fn = Z + 'x_spy_prints.parquet'
    if os.path.exists(fn):
        x = pd.read_parquet(fn); x = x[x.valid.astype(bool) & ~x.eth.astype(bool) & ~x.spread_leg.astype(bool) & (x.aggr != 0)]
        x = x[x.sym.astype(str).str.contains(pd.Timestamp(day).strftime('%y%m%d'))]
        tx = pd.to_datetime(x.ts_ms, unit='ms', utc=True).dt.tz_convert(ET); x = x.assign(m=(tx.dt.hour * 60 + tx.dt.minute).values, sec=x.ts_ms // 1000)
        x = x[(x.m >= 570) & (x.m < 960)]
        g = x.groupby(['sym', 'aggr', 'sec']).agg(m=('m', 'first'), cp=('cp', 'first'), n=('px', 'size'), npx=('px', 'nunique'), size=('size', 'sum')).reset_index()
        g['dir'] = np.sign(g.aggr) * np.sign(g.cp)
        g['f20'] = (px.reindex(g.m + 20).values - px.reindex(g.m).values) * g.dir
        g['sweep'] = (g.n >= 3) & (g.npx >= 2) & (g['size'] >= 50)
        ref = {s_: g.loc[g.dir == s_, 'f20'].mean() for s_ in (1, -1)}
        sw = g[g.sweep & g.f20.notna()]
        if len(sw):
            SW.append(dict(day=day, n=len(sw), edge=float((sw.f20 - sw.dir.map(ref)).mean()), hit=float((sw.f20 > 0).mean()),
                           bull=int((sw.dir > 0).sum())))
    print(day, len(o), flush=True)


def edge(sel, h="f20", sign=1):
    r = []
    for d, s in sel.items():
        a = O[d]; s = s[s[h].notna()]
        if len(s) < 3: continue
        ref = np.array([a.loc[a.dir == x, h].mean() for x in s.dir])
        r.append((d, len(s), sign * float((s[h].values - ref).mean()), float(((sign * s[h]) > 0).mean())))
    return pd.DataFrame(r, columns=["day", "n", "edge", "hit"])


def show(name, sel, sign=1):
    for h in ("f10", "f20", "f30"):
        R = edge(sel, h, sign)
        if not len(R): print(f"{name:34s} {h}: none"); continue
        ins, oos = R[R.day < '2026-11-25'], R[R.day >= '2026-11-25']
        f = lambda X: f"n {X.n.sum():5d} edge {X.edge.mean():+5.2f} days+ {(X.edge > 0).sum()}/{len(X)}" if len(X) else "—"
        print(f"{name:34s} {h}: IN {f(ins)} | OOS {f(oos)} | ALL {f(R)} hit {(R.hit * R.n).sum() / R.n.sum():.0%}")


days_ = sorted(O); big = {}
for i, d in enumerate(days_[1:], 1):
    base = pd.concat([O[x] for x in days_[:i]]); cut = base.groupby("b").dn.quantile(0.9999)
    o = O[d]; big[d] = o[o.dn.values >= cut.reindex(o.b).values]
print('\n(sign -1 = the pre-registered FADE; + = rule made money)')
show("H4 fade biggest (1/10,000 tod)", big, -1)
show("H5 PM sold calls >=20 paid FOLLOW", {d: o[(o.aggr_side == "SELL") & (o.cp > 0) & (o.m >= 720) & (o["size"] >= 20) & o.paid] for d, o in O.items()})
show("H6 AM bought puts >=20 paid FADE", {d: o[(o.aggr_side == "BUY") & (o.cp < 0) & (o.m < 720) & (o["size"] >= 20) & o.paid] for d, o in O.items()}, -1)
show("AM bought calls >=20 paid FOLLOW", {d: o[(o.aggr_side == "BUY") & (o.cp > 0) & (o.m < 720) & (o["size"] >= 20) & o.paid] for d, o in O.items()})
print('\nN5 SPY sweep proxy (>=3 prints, >=2 prices, >=50 lots, same second):'); W = pd.DataFrame(SW); print(W.round(2).to_string(index=False))
if len(W): print(f"  pooled edge {(W.edge * W.n).sum() / W.n.sum():+.2f}, day-avg {W.edge.mean():+.2f}, days+ {(W.edge > 0).sum()}/{len(W)}")
B = pd.DataFrame(RB)
if len(B):
    B['pnl'] = B.sell - B.buy
    print('\nRANDOM-ENTRY COST BASELINE (1DTE 1 strike ITM, ask in, bid out 30 min later):')
    print(B.groupby('day').agg(n=('pnl', 'size'), pnl=('pnl', 'mean'), spread=('spread', 'mean'), move=('move', 'mean')).round(2).to_string())
    print(f"  ALL n {len(B)} mean P&L {B.pnl.mean():+.2f} SPX pts/contract (median {B.pnl.median():+.2f}), win {(B.pnl > 0).mean():.0%}, mean entry spread {B.spread.mean():.2f}")
