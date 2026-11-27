# N10 (pre-registered 27 Nov 16:49 ET): robustness of unusual "new positions" (v0.44.0 default settings)
import sys; sys.path.insert(0, sys.argv[1]); from common import *
from uv44 import base_files, spx_frame
from core import unusual as UN
BF = base_files('SPX'); lean = {d['day']: d for d in days()}
ev = []
for day, z in ZIPS.items():
    Z = f"{S}/data/{z}/"; hist = [BF[k] for k in sorted(BF) if k < day][-UN.NDAYS:]
    f = spx_frame(day, Z); p = dict(UN.DEF); cut = UN.cuts(hist, 'single-leg', p)
    o, bu = UN.detect(f, 'SPX', pd.Timestamp(day), 'single-leg', UN.FLAGS, p, exp=day, cut=cut)
    sp = pd.DataFrame(lean[day]['spx'], columns=['m', 'o', 'h', 'l', 'c']).drop_duplicates('m', keep='last')
    t0 = UN._t0(day); px = pd.Series(sp.c.values, index=((sp.m.values - t0) // 60000).astype(int)).reindex(range(0, 391))
    m = ((o.ts_ms.values - t0) // 60000).astype(int); d = np.where(o.bull.values > 0, 1.0, -1.0)
    for h in (10, 20, 30):
        fw = px.reindex(m + h).values - px.reindex(m).values
        base = {s_: np.nanmean(fw[d == s_]) for s_ in (1.0, -1.0)}
        sel = o['new'].values.astype(bool); dd = np.where(o.new_bull.values > 0, 1.0, -1.0)[sel]
        ed = fw[sel] * dd - np.array([base[x] * x for x in dd])
        for mm, e in zip(m[sel], ed):
            if np.isfinite(e): ev.append(dict(day=day, h=h, pm=mm >= 150, edge=e))
E = pd.DataFrame(ev)
print('N10 new positions — event-level edge (pts), days positive')
for h, g in E.groupby('h'):
    bd = g.groupby('day').edge.mean()
    print(f" h{h}: n {len(g)} pooled {g.edge.mean():+.2f} day-avg {bd.mean():+.2f} days+ {(bd>0).sum()}/{len(bd)}")
g = E[E.h == 20]
for pm, gg in g.groupby('pm'):
    bd = gg.groupby('day').edge.mean()
    print(f" h20 {'PM >=12:00' if pm else 'AM <12:00'}: n {len(gg)} pooled {gg.edge.mean():+.2f} days+ {(bd>0).sum()}/{len(bd)}")
print(' leave-one-day-out pooled edge at 20:', {d: round(g[g.day != d].edge.mean(), 2) for d in sorted(g.day.unique())})
print(' per day h20:', g.groupby('day').edge.agg(['count', 'mean']).round(2).to_dict('index'))
