import pandas as pd, numpy as np
O = pd.read_pickle("uo_orders.pkl"); days = sorted(O)
rng = np.random.default_rng(1)
def edge(sel, base_all, h="f20"):
    """edge per day = mean(fwd of selected) - mean(fwd of all orders that day same dir mix) → avg + day bootstrap"""
    r = []
    for d in sel:
        s, a = sel[d], base_all[d]
        s = s[s[h].notna()]
        if len(s) < 3: continue
        # drift control: compare with all orders that day with same direction
        ref = np.array([a.loc[a.dir == x, h].mean() for x in s.dir])
        r.append((d, len(s), float((s[h].values - ref).mean()), float((s[h] > 0).mean())))
    if not r: return None
    R = pd.DataFrame(r, columns=["day", "n", "edge", "hit"])
    bs = [R.sample(len(R), replace=True, random_state=int(rng.integers(1e9))).edge.mean() for _ in range(3000)]
    return R.n.sum(), R.edge.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5), int((R.edge > 0).sum()), len(R), (R.hit * R.n).sum() / R.n.sum()
def show(name, sel):
    for h in ("f10", "f20", "f30"):
        e = edge(sel, O, h)
        if e: print(f"{name:42s} {h}: n {e[0]:6d}  edge {e[1]:+5.2f} pts  CI [{e[2]:+.2f},{e[3]:+.2f}]  days+ {e[4]}/{e[5]}  hit {e[6]:.0%}")
# 1 time-of-day big cut-offs, walk-forward
for q in (0.9995, 0.9999):
    sel = {}
    for i, d in enumerate(days[1:], 1):
        base = pd.concat([O[x] for x in days[:i]]); cut = base.groupby("b").dn.quantile(q)
        o = O[d]; sel[d] = o[o.dn.values >= cut.reindex(o.b).values]
    show(f"BIG tod 1/{int(1/(1-q))}", sel)
    show(f"BIG tod 1/{int(1/(1-q))} paid", {d: s[s.paid] for d, s in sel.items()})
# 2 bought calls / bought puts / sold calls / sold puts, AM/PM, orders >= 20 lots
for nm, f in (("bought calls", lambda o: (o.aggr_side == "BUY") & (o.cp > 0)), ("bought puts", lambda o: (o.aggr_side == "BUY") & (o.cp < 0)),
              ("sold calls", lambda o: (o.aggr_side == "SELL") & (o.cp > 0)), ("sold puts", lambda o: (o.aggr_side == "SELL") & (o.cp < 0))):
    for sess, sf in (("AM", lambda o: o.m < 720), ("PM", lambda o: o.m >= 720)):
        show(f"{nm} {sess} ≥20 lots paid", {d: o[f(o) & sf(o) & (o["size"] >= 20) & o.paid] for d, o in O.items()})
# 3 auction vs auto
show("auction prints ≥20", {d: o[o.auct & (o["size"] >= 20)] for d, o in O.items()})
show("auto prints ≥20", {d: o[~o.auct & (o["size"] >= 20)] for d, o in O.items()})
