"""Unusual flags with the v0.44.0 code (UN.history-style seed+state baselines -> UN.cuts -> UN.detect), walk-forward:
each day flagged only against the PREVIOUS sessions' half-hour cut-offs. Variants: drop mid on/off x drop crosses on/off.
Score = SPX h min later x flag direction minus all single-leg orders that day in the same direction (as UN._score),
h = 10/20/30. SPX path = lean-file SPX 1-min (25 Nov to 14:33; NaN after, never forward-filled)."""
import sys; sys.path.insert(0, sys.argv[1]); from common import *
from core import unusual as UN
ET = 'America/New_York'
SEED = S + '/app/trishula/core/data/unusual/'; STATE = S + '/state/unusual/'


def base_files(mkt):
    out = {}
    for d in (SEED, STATE):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(f'_{mkt}.json'): out[fn[:10]] = json.load(open(d + fn))
    return out


def spx_frame(day, Z):
    p = pd.read_parquet(Z + 'prints.parquet', columns=["ts_ms", "sym", "exp", "strike", "cp", "px", "size", "bid", "ask", "aggr", "spread_leg", "eth", "valid", "spot", "ev_type"])
    p = p[(p.exp.astype(str) == day) & p.valid.astype(bool) & (p.ev_type.astype(str) != '2')]
    c = pd.read_parquet(Z + "chain_snapshots.parquet", columns=["ts_ms", "sym", "oi"])
    oi = c.dropna(subset=["oi"]).sort_values("ts_ms").groupby("sym")["oi"].first()
    s = pd.read_parquet(Z + "spx1m.parquet"); mp = dict(zip((s.ts_ms // 60000) * 60000, s.close))
    Sx = p.spot.values.astype(float); miss = ~np.isfinite(Sx)
    Sx[miss] = pd.Series((p.ts_ms.values[miss] // 60000) * 60000).map(mp).values
    f = pd.DataFrame({"ts_ms": p.ts_ms.values.astype("int64"), "sym": p.sym.astype(str).values, "strike": p.strike.values.astype(float),
                      "cp": p.cp.values.astype(float), "px": p.px.values.astype(float), "size": p["size"].values.astype(float),
                      "bid": p.bid.values.astype(float), "ask": p.ask.values.astype(float), "aggr": np.nan_to_num(p.aggr.values.astype(float)),
                      "sl": ~p.spread_leg.fillna(False).values.astype(bool), "eth": p.eth.fillna(False).values.astype(bool), "S": Sx,
                      "oi": p.sym.astype(str).map(oi).values.astype(float)})
    return f.sort_values("ts_ms", kind="stable").reset_index(drop=True)


if __name__ == '__main__':
    BF = base_files('SPX')
    lean = {d['day']: d for d in days()}
    rows = []
    for day, z in ZIPS.items():
        Z = f"{S}/data/{z}/"
        hist = [BF[k] for k in sorted(BF) if k < day][-UN.NDAYS:]
        f = spx_frame(day, Z)
        sp = pd.DataFrame(lean[day]['spx'], columns=['m', 'o', 'h', 'l', 'c']).drop_duplicates('m', keep='last')
        t0 = UN._t0(day)
        px = pd.Series(sp.c.values, index=((sp.m.values - t0) // 60000).astype(int)).reindex(range(0, 391))   # NO ffill
        for dm in (False, True):
            for dc in (False, True):
                p = dict(UN.DEF, drop_mid=dm, drop_cross=dc)
                cut = UN.cuts(hist, 'single-leg', p)
                o, bu = UN.detect(f, 'SPX', pd.Timestamp(day), 'single-leg', UN.FLAGS, p, exp=day, cut=cut)
                if not len(o): continue
                m = ((o.ts_ms.values - t0) // 60000).astype(int)
                d = np.where(o.bull.values > 0, 1.0, -1.0)
                for h in (10, 20, 30):
                    fw = px.reindex(m + h).values - px.reindex(m).values
                    base = {s_: np.nanmean(fw[d == s_]) for s_ in (1.0, -1.0)}
                    for k in UN.FLAGS:
                        if k == 'burst':
                            if not len(bu): continue
                            mm = bu.m.values.astype(int); dd = np.where(bu.b.values > 0, 1.0, -1.0)
                            mv = (px.reindex(mm + h).values - px.reindex(mm).values) * dd
                        else:
                            sel = o[k].values.astype(bool)
                            if not sel.any(): continue
                            dd = (np.where(o.new_bull.values > 0, 1.0, -1.0) if k == 'new' else d)[sel]
                            mv = fw[sel] * dd
                        ed = mv - np.array([base[x] * x for x in dd])
                        ok = np.isfinite(ed)
                        rows.append(dict(day=day, dm=dm, dc=dc, h=h, flag=k, n=int(ok.sum()), raw=np.nanmean(mv) if ok.any() else np.nan,
                                         edge=np.nanmean(ed) if ok.any() else np.nan, hit=float((mv[ok] > 0).mean()) if ok.any() else np.nan,
                                         cut=cut is not None))
        print(day, 'hist', len(hist), 'cut', UN.cuts(hist, 'single-leg', UN.DEF) is not None, flush=True)
    R = pd.DataFrame(rows); R.to_pickle(S + '/work/uv44.pkl')
    pd.set_option('display.width', 220)
    R = R[R.n > 0]
    def agg(g):
        w = g.n
        return pd.Series(dict(days=g.day.nunique(), n=int(w.sum()), edge_dayavg=g.edge.mean(), edge_pooled=(g.edge * w).sum() / w.sum(),
                              hit=(g.hit * w).sum() / w.sum(), days_pos=f"{(g.edge > 0).sum()}/{len(g)}"))
    print('\nALL days (walk-forward cut-offs; big/pay/burst only once >=3 previous sessions)')
    print(R.groupby(['flag', 'dm', 'dc', 'h']).apply(agg).round(2).to_string())
    print('\nTODAY 25 Nov, h=20')
    print(R[(R.day == '2026-11-25') & (R.h == 20)][['flag', 'dm', 'dc', 'n', 'raw', 'edge', 'hit']].round(2).to_string(index=False))
    print('\nper day, default (drop mid off, crosses on), h=20')
    print(R[(~R.dm) & (R.dc) & (R.h == 20)].pivot(index='day', columns='flag', values=['n', 'edge']).round(1).to_string())
