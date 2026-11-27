# TG (pre-registered 27 Nov 16:49 ET): Terrain Gamma, full coded grid, H1' / H2' on raw data, max-null over configs
import sys; sys.path.insert(0, sys.argv[1]); from common import *
import datetime as dt
from core import terrain as T, signs as SG
ET = 'America/New_York'; rows = []
for day, z in ZIPS.items():
    Z = f"{S}/data/{z}/"; d = dt.date.fromisoformat(day)
    c = pd.read_parquet(Z + 'chain_snapshots.parquet'); c['exp'] = c.exp.astype(str)
    c['type'] = np.where(c.cp > 0, 'call', 'put'); c['volume'] = c['day_volume']
    s = pd.read_parquet(Z + 'spx1m.parquet'); s['t'] = pd.to_datetime(s.ts_ms, unit='ms', utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    s = s[s.t.dt.date == d].set_index('t').sort_index()
    bk = pd.read_parquet(Z + 'book.parquet') if os.path.exists(Z + 'book.parquet') else None
    if bk is not None: bk['exp'] = bk.exp.astype(str)
    P = pd.read_parquet(Z + 'prints.parquet'); C5 = pd.read_parquet(Z + 'candles5.parquet'); legs = json.load(open(Z + 'legs.json'))
    for col in ('exp', 'sym', 'ev_type'):
        if col in P: P[col] = P[col].astype(str)
    for hh in range(10, 16):
        now = dt.datetime(d.year, d.month, d.day, hh); ms = int(pd.Timestamp(now).tz_localize(ET).value // 10**6)
        cs = c[(c.ts_ms <= ms) & (c.ts_ms >= ms - 600000)]
        if cs.empty: continue
        ch0 = cs[cs.ts_ms == cs.ts_ms.max()].copy()
        spot = float(ch0.spot.dropna().iloc[-1]) if ch0.spot.notna().any() else np.nan
        fut = s[(s.index > now) & (s.index <= now + pd.Timedelta('60min'))]
        if not np.isfinite(spot) or len(fut) < 50: continue
        rng = fut.high.max() - fut.low.min(); mv = fut.close.iloc[-1] - spot
        exps_all = sorted(e for e in ch0.exp.unique() if e >= day)
        signs = {'naive': None, 'signed all': 'dsign'}
        for e in exps_all[:2]:
            for sl, nm in ((True, 'single-leg'), (False, 'opening')):
                tb = SG.dsign_table(P, C5, legs, e, ms, single_leg=sl)
                if len(tb):
                    col = 'seed_dsign' if nm == 'opening' else 'dsign'
                    signs.setdefault(nm, {}).update(dict(zip(tb['sym'].astype(str), tb[col])))
        for sname, sv in signs.items():
            ch = ch0.copy()
            if isinstance(sv, dict): ch['dsign'] = ch['sym'].astype(str).map(sv)
            for exset in ('0DTE', '0+1DTE', '0DTE+book.35', '0DTE+book1', '0+1DTE+book.35'):
                ex = exps_all[:1] if exset.startswith('0DTE') else exps_all[:2]; chx = ch
                if 'book' in exset and bk is None: continue
                if 'book' in exset:
                    w = 0.35 if '.35' in exset else 1.0
                    b2 = bk[~bk.exp.isin(ex)].assign(dsign=lambda q: np.where(q.cp > 0, 1.0, -1.0) * w, day_volume=0.0)
                    b2 = b2.assign(type=np.where(b2.cp > 0, 'call', 'put'), volume=0.0)
                    chx = pd.concat([ch, b2[[k for k in b2.columns if k in ch.columns]]], ignore_index=True); ex = ex + sorted(b2.exp.unique())
                for wt in T.WEIGHTS:
                    for vw in ((0.05, 0.25, 1.0) if ('Vol' in wt or '+' in wt) else (1.0,)):
                        for fm in T.FIELD_MODES:
                            try:
                                pg, F, taus = T.terrain_grid(chx, spot, ex, now, d, greek='Gamma', field_mode=fm, p_min=spot - 60, p_max=spot + 60,
                                                             n_price=121, n_time=40, weighting=wt, signed=(sname != 'naive'), units='minis', vol_w=vw)
                            except Exception as er:
                                continue
                            j = int(np.argmin([abs((t - now).total_seconds()) for t in taus])); col = F[:, j]
                            at = float(np.interp(spot, pg, col)); zc = pg[np.where(np.diff(np.sign(col)) != 0)[0]]
                            nz = zc[np.argmin(np.abs(zc - spot))] if len(zc) else np.nan
                            rows.append(dict(day=day, t=hh, cfg=f"{sname}|{exset}|{wt}|{vw}|{fm.split()[0]}", at=at, rng=rng, mv=mv, dist=nz - spot))
    print(day, len(rows), flush=True)
R = pd.DataFrame(rows); R.to_pickle(S + '/work/tg.pkl'); print('rows', len(R), 'cfgs', R.cfg.nunique())
