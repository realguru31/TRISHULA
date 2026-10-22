import numpy as np, pandas as pd, warnings, sys; warnings.filterwarnings("ignore")
from scipy.stats import norm
from brute import fields
from score2 import scores
def setup(Tp, spotp, optp, chain, expc):
    T=pd.read_pickle(Tp); s=pd.read_pickle(spotp); opt=pd.read_pickle(optp)
    K=np.array(T.index,float); St=s.reindex(T.columns,method="nearest").values
    F=fields(T.columns, list(K), opt, chain, s, pd.Timestamp(expc))
    o=opt[opt.strike.isin(K)]
    vol=o.pivot_table(index="t",columns="base",values="volume",aggfunc="sum")
    net=o.pivot_table(index="t",columns="base",values="askv",aggfunc="sum").sub(o.pivot_table(index="t",columns="base",values="bidv",aggfunc="sum"),fill_value=0)
    allt=pd.date_range(min(vol.index.min(),T.columns[0]),T.columns[-1],freq="1min")
    syms=chain[chain.strike.isin(K)].set_index("sym").index
    vol=vol.reindex(allt).reindex(columns=syms).fillna(0); net=net.reindex(allt).reindex(columns=syms).fillna(0)
    R={}
    for W in (15,30,60,120,240):
        R[f"vol{W}"]=vol.rolling(W,min_periods=1).sum().reindex(T.columns).values
        R[f"absnet{W}"]=net.rolling(W,min_periods=1).sum().abs().reindex(T.columns).values
    mask=np.isfinite(T.values)&(np.abs(K[:,None]-St[None,:])>7)
    return T,s,K,St,F,R,mask
def grid(F,K,St,fn,w):
    out=np.zeros((len(K),len(St)))
    for j in range(len(St)):
        T_=F["Tt"][j]; iv=np.where(F["IV"][j]>0,F["IV"][j],0.2); PP=K[:,None]; KK=F["K"][None,:]; sq=np.sqrt(T_)
        d1=(np.log(PP/KK)+0.5*iv*iv*T_)/(iv*sq); d2=d1-iv*sq; pdf=norm.pdf(d1)
        g=dict(avanna=np.abs(pdf*d2/iv), gamma=pdf/(PP*iv*sq), vega=PP*pdf*sq)[fn]
        out[:,j]=(g*w[j][None,:]).sum(axis=1)
    return out
