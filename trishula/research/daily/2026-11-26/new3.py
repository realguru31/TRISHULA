# N7-N9, pre-registered in prereg.txt (26 Nov 16:52 ET)
import sys; sys.path.insert(0, sys.argv[1]); from common import *
from money_frame import frame
H = json.load(open(sys.argv[2]))
import datetime as dt
raw = {}
for f in sorted(glob.glob(S + '/state/state/lean/*.json')):
    d = LN.trim(json.load(open(f)))
    if LN.rth_minutes(d) > 0: raw[d['day']] = frame(d)
print('lean days', list(raw))
# N7
print('\nN7 last-hour flow (15:00-15:29) -> 15:30..15:59')
rows = []
for day, (s, r) in raw.items():
    if s.index.max() < pd.Timestamp(day + ' 15:59'): print(' skip', day, 'ends', s.index.max().time()); continue
    f = (r.sb - r.sr).loc[day + ' 15:00':day + ' 15:29'].sum(); sg = np.sign(f)
    mv = s.c[pd.Timestamp(day + ' 15:59')] - s.c[pd.Timestamp(day + ' 15:30')]
    drift30 = (s.c.shift(-29) - s.c).dropna().mean()
    rows.append(dict(day=day, flow=round(f, 2), dir=sg, move=round(mv, 1), pnl=round(sg * mv - 0.5, 1), edge=round(sg * (mv - drift30), 1)))
A = pd.DataFrame(rows); print(A.to_string(index=False))
print(f" n {len(A)} hit {(A.pnl > -0.5).mean():.0%}... right {(A.dir*A.move>0).mean():.0%} mean pnl {A.pnl.mean():+.1f} total {A.pnl.sum():+.1f} edge {A.edge.mean():+.1f}")
# N8
print('\nN8 short ATM 0DTE straddle (app quotes) held to close, -0.5')
rows = []
for day in sorted(H['strad']):
    if day not in H['series']: continue
    sd = pd.DataFrame(H['strad'][day], columns=['t', 'k', 'p']); sd['t'] = pd.to_datetime(sd.t)
    se = pd.DataFrame([x[:3] for x in H['series'][day]], columns=['t', 'spot', 'src']); se['t'] = pd.to_datetime(se.t)
    se = se[(se.src == 'spx') & (se.t <= pd.Timestamp(day + ' 16:00')) & (se.t >= pd.Timestamp(day + ' 09:30'))]
    if se.empty or se.t.max() < pd.Timestamp(day + ' 15:55'): print(' skip', day, 'spx ends', se.t.max()); continue
    close = se.spot.iloc[-1]; row = dict(day=day, close=close)
    for hh in ('10:00', '12:00', '14:00'):
        q = sd[(sd.t >= pd.Timestamp(day + ' ' + hh)) & (sd.p > 0)]
        if q.empty: row[hh] = np.nan; continue
        k, p = q.k.iloc[0], q.p.iloc[0]; row[hh] = round(p - abs(close - k) - 0.5, 1); row['p' + hh] = p
    rows.append(row)
B = pd.DataFrame(rows); print(B.to_string(index=False))
for hh in ('10:00', '12:00', '14:00'): print(f" {hh}: mean {B[hh].mean():+.1f} days+ {(B[hh] > 0).sum()}/{B[hh].count()} total {B[hh].sum():+.1f}")
# N9
print('\nN9 gap fade 09:35 -> 10:30 when |gap| >= 5')
import pandas.tseries.offsets as off
from pandas.tseries.holiday import USFederalHolidayCalendar
days = list(raw); rows = []
for i, day in enumerate(days[1:], 1):
    prev = days[i - 1]
    bd = pd.bdate_range(prev, day)
    hol = {'2026-11-11'} - {'2026-11-11'}  # Veterans Day: NYSE open
    if len(bd) != 2: print(' skip', day, '(prev saved', prev, 'is not the previous trading day)'); continue
    sp, _ = raw[prev]; s, _ = raw[day]
    if sp.index.max() < pd.Timestamp(prev + ' 15:59'): print(' skip', day, '(prev file ends', sp.index.max().time(), ')'); continue
    gap = s.o[pd.Timestamp(day + ' 09:30')] - sp.c.iloc[-1]
    if abs(gap) < 5: rows.append(dict(day=day, gap=round(gap, 1), traded=False)); continue
    mv = s.c[pd.Timestamp(day + ' 10:30')] - s.c[pd.Timestamp(day + ' 09:35')]
    rows.append(dict(day=day, gap=round(gap, 1), traded=True, move=round(mv, 1), fade=round(-np.sign(gap) * mv - 0.5, 1), follow=round(np.sign(gap) * mv - 0.5, 1)))
C = pd.DataFrame(rows); print(C.to_string(index=False)); T_ = C[C.traded]
print(f" traded {len(T_)} fade right {(T_.fade > -0.5).mean():.0%} fade total {T_.fade.sum():+.1f} · follow total {T_.follow.sum():+.1f}")
