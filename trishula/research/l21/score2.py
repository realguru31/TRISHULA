import numpy as np, pandas as pd
from scipy.stats import spearmanr, rankdata
def scores(MM, T, mask, ks, St):
    tv=T.values
    g=spearmanr(MM[mask],tv[mask]).correlation
    # temporal: per strike, Spearman across time
    rs=[]
    for i in range(MM.shape[0]):
        m=mask[i]
        if m.sum()<20 or np.nanstd(tv[i,m])==0 or np.std(MM[i,m])==0: continue
        rs.append(spearmanr(MM[i,m],tv[i,m]).correlation)
    tmp=np.nanmean(rs) if rs else np.nan
    # cross-section per time
    cs=[]
    for j in range(MM.shape[1]):
        m=mask[:,j]
        if m.sum()<20 or np.nanstd(tv[m,j])==0 or np.std(MM[m,j])==0: continue
        cs.append(spearmanr(MM[m,j],tv[m,j]).correlation)
    return g, tmp, np.nanmean(cs) if cs else np.nan
