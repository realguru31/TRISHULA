import numpy as np, pandas as pd, itertools, sys
from scipy.stats import norm, spearmanr, rankdata
YEAR=365*24*3600.0
def bs(S,K,T,iv,cp):
    iv=np.where(iv>0,iv,0.2); sq=np.sqrt(T); d1=(np.log(S/K)+0.5*iv*iv*T)/(iv*sq); d2=d1-iv*sq
    pdf=norm.pdf(d1)
    return dict(gamma=pdf/(S*iv*sq), vega=S*pdf*sq/100, delta=np.abs(np.where(cp==1,norm.cdf(d1),norm.cdf(d1)-1)),
                vanna=np.abs(-pdf*d2/iv), charm=np.abs(-pdf*(-d2/(2*T))), dgamma=pdf/(S*iv*sq)*S*S/100, one=np.ones_like(d1))
def fields(T_cols, ks, opt, chain, spot, exp_close):
    # per contract per 5-min time: iv, cumvol, cumnet; then greeks
    o=opt.copy(); o["k"]=o["strike"]
    o=o[o.k.isin(ks)]
    vol=o.pivot_table(index="t",columns="base",values="volume",aggfunc="sum").fillna(0)
    net=o.pivot_table(index="t",columns="base",values="askv",aggfunc="sum").fillna(0)-o.pivot_table(index="t",columns="base",values="bidv",aggfunc="sum").fillna(0)
    ivp=o.pivot_table(index="t",columns="base",values="imp_vol",aggfunc="last")
    allt=pd.date_range(min(vol.index.min(),T_cols[0]),T_cols[-1],freq="1min")
    vol=vol.reindex(allt).fillna(0); net=net.reindex(allt).fillna(0); ivp=ivp.reindex(allt).ffill()
    cum=vol.cumsum().reindex(T_cols); cnet=net.cumsum().reindex(T_cols)
    rth=vol.copy(); rth.loc[rth.index<pd.Timestamp("2026-10-20 09:30")]=0; cumr=rth.cumsum().reindex(T_cols)
    roll=vol.rolling(60,min_periods=1).sum().reindex(T_cols)
    ivp=ivp.reindex(T_cols)
    legs=chain[chain.strike.isin(ks)].set_index("sym")
    syms=legs.index
    cum=cum.reindex(columns=syms).fillna(0); cnet=cnet.reindex(columns=syms).fillna(0); cumr=cumr.reindex(columns=syms).fillna(0)
    roll=roll.reindex(columns=syms).fillna(0); ivp=ivp.reindex(columns=syms)
    K=legs.strike.values; cp=legs.cp.values; oi=legs.oi.fillna(0).values; iv0=legs.iv.fillna(0.2).values
    out={}
    S=spot.reindex(T_cols,method="nearest").values
    Tt=np.array([max((exp_close-t).total_seconds()/YEAR,300/YEAR) for t in T_cols])
    IV=ivp[syms].values; IV=np.where(np.isfinite(IV),IV,iv0[None,:])
    G=bs(S[:,None],K[None,:],Tt[:,None],IV,cp[None,:])
    W=dict(oi=np.broadcast_to(oi,(len(T_cols),len(oi))), cum=cum[syms].values, cumrth=cumr[syms].values,
           oicum=oi[None,:]+cum[syms].values, absnet=np.abs(cnet[syms].values), roll60=roll[syms].values,
           net=cnet[syms].values)
    return dict(G=G,W=W,K=K,cp=cp,S=S,Tt=Tt,IV=IV,oi=oi)
def agg(F, wname, gname, comb, ks):
    v=F["W"][wname]*F["G"][gname]
    sgn={"sum":np.ones_like(F["cp"],float),"cminusp":np.where(F["cp"]==1,1.,-1.),"call":(F["cp"]==1)*1.,"put":(F["cp"]==-1)*1.}[comb]
    v=v*sgn[None,:]
    M=np.zeros((len(F["S"]),len(ks)))
    idx={k:i for i,k in enumerate(ks)}
    for j,k in enumerate(F["K"]): M[:,idx[k]]+=v[:,j]
    if comb=="cminusp": M=np.abs(M)
    return M.T   # strikes x time
def norms(M):
    eps=1e-12
    yield "none", M
    yield "log", np.log1p(np.abs(M)/ (np.nanmax(np.abs(M))+eps)*1e4)
    yield "strike_peak", M/(np.nanmax(np.abs(M),axis=1,keepdims=True)+eps)
    yield "time_peak", M/(np.nanmax(np.abs(M),axis=0,keepdims=True)+eps)
    yield "z_time", (M-M.mean(axis=1,keepdims=True))/(M.std(axis=1,keepdims=True)+eps)
    yield "z_strike", (M-M.mean(axis=0,keepdims=True))/(M.std(axis=0,keepdims=True)+eps)
    yield "rank_time", np.apply_along_axis(rankdata,0,M)
    yield "share_time", M/(np.abs(M).sum(axis=0,keepdims=True)+eps)

def pricegrid(F, wname, gname, comb, ks):
    """value at price level P = Σ_legs w · greek(P, K_leg) (what the book would carry if spot were at P)."""
    from brute import bs
    P=np.array(ks,float); out=np.zeros((len(P),len(F["S"])))
    sgn={"sum":np.ones_like(F["cp"],float),"cminusp":np.where(F["cp"]==1,1.,-1.),"call":(F["cp"]==1)*1.,"put":(F["cp"]==-1)*1.}[comb]
    for j in range(len(F["S"])):
        G=bs(P[:,None],F["K"][None,:],F["Tt"][j],F["IV"][j][None,:],F["cp"][None,:])[gname]
        out[:,j]=(G*(F["W"][wname][j]*sgn)[None,:]).sum(axis=1)
    return out
def norms2(M):
    eps=1e-12
    for nm,X in norms(M): yield nm,X
    d=M-M[:,[0]]; yield "d_open", d
    yield "d_open_abs", np.abs(d)
    yield "signed_unit", M/(np.nanmax(np.abs(M))+eps)
