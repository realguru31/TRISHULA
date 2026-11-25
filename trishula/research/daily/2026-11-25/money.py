"""M1 money-state flips, M2 opening money vs gap, N4 morning lean -> afternoon, N6 first-hour break + lean.
Rules exactly as research/daily/2026-11-25/prereg.txt (written 16:50 ET before running)."""
import sys; sys.path.insert(0, sys.argv[1]); from common import *
ET = 'America/New_York'
rng = np.random.default_rng(11)


def frame(d):
    r = pd.DataFrame(d['rows'], columns=['m', 'g', 'sb', 'sr', 'ab', 'ar'])
    r = r[r.g == 0].groupby('m')[['sb', 'sr']].sum()
    s = pd.DataFrame(d['spx'], columns=['m', 'o', 'h', 'l', 'c']).drop_duplicates('m', keep='last').set_index('m')
    t = pd.to_datetime(s.index, unit='ms', utc=True).tz_convert(ET).tz_localize(None)
    s.index = t; r.index = pd.to_datetime(r.index, unit='ms', utc=True).tz_convert(ET).tz_localize(None)
    day = d['day']
    rth = pd.date_range(pd.Timestamp(day + ' 09:30'), min(s.index.max(), pd.Timestamp(day + ' 15:59')), freq='1min')
    s = s.reindex(rth).ffill(); r = r.reindex(rth).fillna(0.0)
    return s, r


ds = days()
M1, BASE, M2, N4, N6 = [], [], [], [], []
PC = {'2026-11-05':7688.62,'2026-11-09':7376.86,'2026-11-10':7549.94,'2026-11-11':7520.93,'2026-11-12':7619.38,
      '2026-11-16':7561.67,'2026-11-17':7416.59,'2026-11-18':7340.53,'2026-11-20':7175.83,'2026-11-23':6910.39,
      '2026-11-24':7237.17,'2026-11-25':7201.09}   # Yahoo ^GSPC daily close of the previous session
prev_close = None
for d in ds:
    day = d['day']; s, r = frame(d); c = s.c
    drift = {h: (c.shift(-h) - c).mean() for h in (10, 20, 30)}
    net = (r.sb - r.sr)
    st = np.sign(net.rolling(15, min_periods=15).sum())
    # ---- M1
    last = None
    for i in range(1, len(st)):
        t = st.index[i]
        if not (st.iloc[i] != 0 and st.iloc[i - 1] != 0 and st.iloc[i] != st.iloc[i - 1]): continue
        if t.strftime('%H:%M') < '09:45' or t.strftime('%H:%M') > '15:29': continue
        if last is not None and t - last < pd.Timedelta('10min'): continue
        last = t; dr = st.iloc[i]
        row = dict(day=day, t=t, dir=dr)
        for h in (10, 20, 30):
            j = i + h
            row[f'f{h}'] = (c.iloc[j] - c.iloc[i]) * dr if j < len(c) else np.nan
            row[f'x{h}'] = row[f'f{h}'] - drift[h] * dr
        M1.append(row)
    # random-time control: 500 minutes 09:45-15:29, random dir with the day's flip up/down mix
    fl = [x for x in M1 if x['day'] == day]
    pu = np.mean([x['dir'] > 0 for x in fl]) if fl else .5
    ok = np.where((st.index.strftime('%H:%M') >= '09:45') & (st.index.strftime('%H:%M') <= '15:29'))[0]
    for i in rng.choice(ok, 500):
        dr = 1 if rng.random() < pu else -1
        row = dict(day=day)
        for h in (10, 20, 30):
            j = i + h
            row[f'f{h}'] = (c.iloc[j] - c.iloc[i]) * dr if j < len(c) else np.nan
        BASE.append(row)
    # ---- M2
    if True:
        gap = s.o.iloc[0] - PC[day]
        money = np.sign(net.iloc[:5].sum())
        if len(c) > 65:
            out = c.iloc[65] - s.o.iloc[5]
            M2.append(dict(day=day, gap=round(gap, 1), money=int(money), out=round(out, 1),
                           hit=int(np.sign(out) == money), agree=int(np.sign(gap) == money)))
    pc = d.get('spx')
    prev_close = c.iloc[-1] if s.index[-1].strftime('%H:%M') >= '15:59' else None   # only a full prior session
    # ---- N4
    am = net[:pd.Timestamp(day + ' 11:59')].sum()
    end = min(c.index[-1], pd.Timestamp(day + ' 15:30'))
    if c.index[-1] >= pd.Timestamp(day + ' 13:00'):
        mv = c[end] - c[pd.Timestamp(day + ' 12:00')]
        N4.append(dict(day=day, am=round(am, 1), pm_move=round(mv, 1), end=end.strftime('%H:%M'), hit=int(np.sign(am) == np.sign(mv))))
    # ---- N6
    fh = s[:pd.Timestamp(day + ' 10:29')]
    hi, lo = fh.h.max(), fh.l.min()
    after = c[pd.Timestamp(day + ' 10:30'):pd.Timestamp(day + ' 15:00')]
    for side, cond in ((1, after > hi), (-1, after < lo)):
        if cond.any():
            t = cond.idxmax(); i = c.index.get_loc(t)
            if i + 30 >= len(c): continue
            mv = (c.iloc[i + 30] - c.iloc[i]) * side
            ln = np.sign(net.iloc[i - 14:i + 1].sum())
            agree = ln == side
            N6.append(dict(day=day, t=t.strftime('%H:%M'), side=side, lean_agree=bool(agree),
                           follow=round(mv - .5, 1), rule=round((mv if agree else -mv) - .5, 1)))

pd.set_option('display.width', 220)
A = pd.DataFrame(M1); B = pd.DataFrame(BASE)
print('M1 money-state flips (15-bar sign of buyers-sellers, 0DTE single-leg)')
for h in (10, 20, 30):
    g = A.groupby('day')[f'x{h}'].mean()
    print(f"  {h}m: n {A[f'f{h}'].notna().sum()} fwd {A[f'f{h}'].mean():+.2f} right {(A[f'f{h}'].dropna() > 0).mean():.0%} "
          f"edge-vs-drift {A[f'x{h}'].mean():+.2f} days+ {(g > 0).sum()}/{g.notna().sum()} | random-time same-mix {B[f'f{h}'].mean():+.2f}")
print('  per day 20m:', A.groupby('day').agg(n=('x20', 'size'), x20=('x20', 'mean')).round(1).T.to_string())
print('  today:', A[A.day == ds[-1]['day']][['t', 'dir', 'f10', 'f20', 'f30']].round(1).to_string(index=False))
print('\nM2 opening money vs gap'); M = pd.DataFrame(M2); print(M.to_string(index=False))
if len(M): print(f"  money->10:35 hit {M.hit.mean():.0%} (n {len(M)}) · agree-with-gap hit {M[M.agree == 1].hit.mean():.0%} n {int(M.agree.sum())} · disagree hit {M[M.agree == 0].hit.mean():.0%} n {int((M.agree == 0).sum())}")
print('\nN4 morning lean -> afternoon'); N = pd.DataFrame(N4); print(N.to_string(index=False)); print(f"  hit {N.hit.mean():.0%} n {len(N)}")
print('\nN6 first-hour break + lean'); Q = pd.DataFrame(N6); print(Q.to_string(index=False))
if len(Q): print(f"  rule total {Q.rule.sum():+.1f} (n {len(Q)}, right {(Q.rule > 0).mean():.0%}) · always-follow {Q.follow.sum():+.1f} · agree n {Q.lean_agree.sum()} follow-when-agree {Q[Q.lean_agree].follow.sum():+.1f} · fade-when-disagree {Q[~Q.lean_agree].rule.sum():+.1f}")
A.to_pickle(S + '/work/m1.pkl')
