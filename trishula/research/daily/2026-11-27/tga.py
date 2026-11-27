# TG analysis: per config within-day Spearman (field at spot vs 60-min range) and H2 toward-zero share; max-null by shuffling within day
import sys, numpy as np, pandas as pd
from scipy.stats import spearmanr
R = pd.read_pickle(sys.argv[1]); R['rr'] = R.rng - R.groupby(['day', 'cfg']).rng.transform('mean')
R['key'] = R.day + R.t.astype(str)
def stats(R, rr):
    out = {}
    for cfg, g in R.groupby('cfg'):
        x = g['at'].values; y = rr[g.index]
        rho = spearmanr(x, y).correlation if np.std(x) > 0 else np.nan
        h = g[g.dist.abs() > 2]; tw = float((np.sign(h.dist) == np.sign(h.mv)).mean()) if len(h) else np.nan
        out[cfg] = (rho, tw, len(g), len(h), g.day.nunique(), float((g['at'] < 0).mean()))
    return pd.DataFrame(out, index=['rho', 'toward', 'n', 'nh', 'days', 'red']).T
A = stats(R, R.rr)
print('configs', len(A), '· checkpoints per config median', A.n.median(), '· days', A.days.max())
print('rho distribution (within-day): min %.2f p5 %.2f median %.2f p95 %.2f max %.2f' % tuple(np.nanpercentile(A.rho, [0, 5, 50, 95, 100])))
print('toward share: min %.0f%% median %.0f%% max %.0f%%' % tuple(100 * np.nanpercentile(A.toward, [0, 50, 100])))
print('\nbest 8 by most negative rho (H1 prediction rho<0):'); print(A.sort_values('rho').head(8).round(2).to_string())
print('\nbest 8 by toward share (H2 prediction >50%):'); print(A.sort_values('toward', ascending=False).head(8).round(2).to_string())
# max-null: shuffle the outcome (rr and mv jointly) across checkpoints within each day, same permutation for all configs
rng = np.random.default_rng(1); keys = R[['day', 'key']].drop_duplicates()
mn_rho, mx_tw = [], []
base = R.drop_duplicates('key').set_index('key')[['rng', 'mv']]
for b in range(200):
    perm = {}
    for d, g in keys.groupby('day'):
        k = g.key.values; perm.update(dict(zip(k, rng.permutation(k))))
    R2 = R.copy(); src = R2.key.map(perm)
    R2['rng'] = base.rng.reindex(src).values; R2['mv'] = base.mv.reindex(src).values
    rr2 = R2.rng - R2.groupby(['day', 'cfg']).rng.transform('mean')
    B = stats(R2, rr2); mn_rho.append(np.nanmin(B.rho)); mx_tw.append(np.nanmax(B.toward))
print(f"\nmax-null (200 within-day shuffles): best-config rho 5th pct {np.percentile(mn_rho, 5):+.2f} (observed best {np.nanmin(A.rho):+.2f}) · "
      f"best toward 95th pct {np.percentile(mx_tw, 95):.0%} (observed best {np.nanmax(A.toward):.0%})")
for nm in ['naive|0DTE+book.35|Vol else OI (legacy)|0.25|Aggregate', 'naive|0DTE|OI (opening book)|1.0|Aggregate']:
    if nm in A.index: print(' ', nm, A.loc[nm].round(2).to_dict())
by = A.groupby(A.index.str.split('|').str[0])[['rho', 'toward', 'red']].median().round(2); print('\nby sign source (median over configs):'); print(by.to_string())
by = A.groupby(A.index.str.split('|').str[1])[['rho', 'toward', 'red']].median().round(2); print('\nby expiry set:'); print(by.to_string())
by = A.groupby(A.index.str.split('|').str[4])[['rho', 'toward', 'red']].median().round(2); print('\nby field mode:'); print(by.to_string())
A.to_csv(sys.argv[1].replace('.pkl', '_cfg.csv'))
