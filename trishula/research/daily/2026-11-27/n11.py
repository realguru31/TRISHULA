# N11 (pre-registered 27 Nov 16:49 ET): 30-min opening-range break, price-only yardstick
import sys; sys.path.insert(0, sys.argv[1]); from common import *
from money_frame import frame
rows = []
for f in sorted(glob.glob(S + '/state/state/lean/*.json')):
    d = LN.trim(json.load(open(f)))
    if LN.rth_minutes(d) <= 0: continue
    s, _ = frame(d); day = d['day']
    if s.index.min() > pd.Timestamp(day + ' 09:31') or s.index.max() < pd.Timestamp(day + ' 10:30'):
        print(' skip', day, s.index.min().time(), s.index.max().time()); continue
    orb = s.loc[day + ' 09:30':day + ' 09:59']; H, L = orb.h.max(), orb.l.min()
    w = s.loc[day + ' 10:00':day + ' 12:59']
    br = w[(w.c > H) | (w.c < L)]
    drift = (s.c.shift(-60) - s.c).dropna().mean()
    if br.empty: rows.append(dict(day=day, t='-', dir=0, pnl=0.0, edge=0.0, ORw=round(H - L, 1))); continue
    t = br.index[0]; dr = 1.0 if br.c.iloc[0] > H else -1.0
    t2 = min(t + pd.Timedelta('60min'), s.index.max()); mv = s.c[t2] - s.c[t]
    rows.append(dict(day=day, t=t.strftime('%H:%M'), dir=dr, ORw=round(H - L, 1), move=round(mv, 1), pnl=round(dr * mv - 0.5, 1), edge=round(dr * (mv - drift), 1)))
A = pd.DataFrame(rows); print(A.to_string(index=False))
tr = A[A.dir != 0]
print(f" traded {len(tr)}/{len(A)} days · right {(tr.dir*tr.move>0).mean():.0%} · mean {tr.pnl.mean():+.1f} · total {tr.pnl.sum():+.1f} · edge vs drift {tr.edge.mean():+.1f} · days + {(tr.pnl>0).sum()}/{len(tr)}")
