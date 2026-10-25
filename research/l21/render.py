import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, warnings; warnings.filterwarnings("ignore")
from matplotlib.colors import ListedColormap
from scipy.stats import norm
from brute import fields
from target import AG
def bandify(M, shares):
    c=np.cumsum(shares)[:-1]; q=np.quantile(M[np.isfinite(M)],c); return np.digitize(M,q)
def grid(F,K,St,fn,wn,norm_=None):
    out=np.zeros((len(K),len(St))); w=F["W"][wn]
    for j in range(len(St)):
        T_=F["Tt"][j]; iv=np.where(F["IV"][j]>0,F["IV"][j],0.2); PP=K[:,None]; KK=F["K"][None,:]; sq=np.sqrt(T_)
        d1=(np.log(PP/KK)+0.5*iv*iv*T_)/(iv*sq); d2=d1-iv*sq; pdf=norm.pdf(d1)
        g=dict(avanna=np.abs(pdf*d2/iv), gamma=pdf/(PP*iv*sq), vega=PP*pdf*sq)[fn]
        out[:,j]=(g*w[j][None,:]).sum(axis=1)
    if norm_=="time_peak": out=out/np.abs(out).max(axis=0,keepdims=True)
    return out
def panel(ax,B,T,s,title):
    ax.imshow(B,origin="lower",aspect="auto",cmap=ListedColormap(AG),vmin=-.5,vmax=6.5,extent=[0,B.shape[1],T.index[0],T.index[-1]])
    ss=s.reindex(T.columns,method="nearest"); ax.plot(np.arange(len(ss))+.5,ss.values,"w",lw=1.3)
    ax.set_xticks(range(0,B.shape[1],24)); ax.set_xticklabels([f"{t:%H:%M}" for t in T.columns[::24]],fontsize=8); ax.set_title(title,fontsize=10)
