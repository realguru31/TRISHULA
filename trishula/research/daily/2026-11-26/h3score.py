import pandas as pd, numpy as np, sys
R = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 else "h3_raw.pkl")
R = R[R.res.notna()].copy()
R["above"] = R.dist > 0
R = R.sort_values(["day", "var", "kind", "above", "touch_i"])
keep = []; last = {}
for r in R.itertuples():
    key = (r.day, r.var, r.kind, r.above)
    p = last.get(key)
    if p is not None and r.touch_i - p[0] <= 10 and abs(r.level - p[1]) <= 5: continue
    last[key] = (r.touch_i, r.level); keep.append(r.Index)
R = R.loc[keep]
R["rev"] = (R.res == "R").astype(float)
R["null"] = R.null_r / (R.null_r + R.null_b).replace(0, np.nan)
rng = np.random.default_rng(0)
for (v, k), g in R.groupby(["var", "kind"]):
    g = g.dropna(subset=["null"])
    byday = g.groupby("day").apply(lambda x: pd.Series(dict(n=len(x), line=x.rev.mean(), null=x["null"].mean())))
    diff = (g.rev - g["null"]).values; days = g.day.values; ud = np.unique(days)
    bs = []
    for _ in range(10000):
        pick = rng.choice(ud, len(ud)); bs.append(np.concatenate([diff[days == d] for d in pick]).mean())
    lo, hi = np.percentile(bs, [2.5, 97.5])
    pos = int(((byday.line - byday.null) > 0).sum())
    print(f"\n{v} {k}: n {len(g)}  line rev {g.rev.mean():.0%}  null {g['null'].mean():.0%}  diff {diff.mean():+.0%}  CI [{lo:+.0%}, {hi:+.0%}]  days + {pos}/{len(byday)}")
    print(byday.round(2).to_string())
