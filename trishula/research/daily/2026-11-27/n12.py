# N12 (pre-registered 27 Nov 16:49 ET): 0DTE GEX sign (naive book) -> lag-1 autocorr of 5-min SPX returns next 30 min
import sys; sys.path.insert(0, sys.argv[1]); from common import *
from core import terrain as T
ET = 'America/New_York'
rows = []
for day, z in ZIPS.items():
    Z = f"{S}/data/{z}/"
    c = pd.read_parquet(Z + 'chain_snapshots.parquet'); c['exp'] = c.exp.astype(str); c = c[c.exp == day]
    c['type'] = np.where(c.cp > 0, 'call', 'put')
    s = pd.read_parquet(Z + 'spx1m.parquet'); s['t'] = pd.to_datetime(s.ts_ms, unit='ms', utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    s = s[s.t.dt.date == pd.Timestamp(day).date()].set_index('t').sort_index().close
    for hh in np.arange(10.0, 15.01, 0.5):
        now = pd.Timestamp(day) + pd.Timedelta(hours=float(hh)); ms = int(now.tz_localize(ET).value // 10**6)
        cs = c[(c.ts_ms <= ms) & (c.ts_ms >= ms - 600000)]
        if cs.empty: continue
        ch = cs[cs.ts_ms == cs.ts_ms.max()]
        g, _ = T.gamma_exposure_minis(ch, signed=False)
        fut = s[(s.index >= now) & (s.index <= now + pd.Timedelta('30min'))]
        if g is None or len(fut) < 28: continue
        r5 = fut.resample('5min', origin=now).last().diff().dropna().values
        if len(r5) < 5: continue
        rows.append(dict(day=day, t=now.strftime('%H:%M'), gex=g, r=r5))
R = pd.DataFrame(rows); R['reg'] = np.where(R.gex > 0, '+GEX', '-GEX')
def ac(rs):
    a = np.concatenate([x[:-1] for x in rs]); b = np.concatenate([x[1:] for x in rs])
    return np.corrcoef(a, b)[0, 1], len(a)
for reg, g in R.groupby('reg'):
    v, n = ac(g.r); print(f" {reg}: {len(g)} windows on {g.day.nunique()} days · lag-1 autocorr {v:+.2f} (pairs {n})")
held = 0; tot = 0
for day, g in R.groupby('day'):
    if g.reg.nunique() < 2: print(' ', day, 'one regime only:', g.reg.iloc[0], len(g)); continue
    p = ac(g[g.reg == '+GEX'].r)[0]; m = ac(g[g.reg == '-GEX'].r)[0]; tot += 1; held += p < m
    print(f"  {day}: +GEX {p:+.2f} · -GEX {m:+.2f}")
print(f" inequality ac(+) < ac(-) held {held}/{tot} days with both regimes")
