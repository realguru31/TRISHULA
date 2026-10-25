import sys; sys.path.insert(0,"/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/l25")
import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from pipe import scores, AG
src=open("brute21.py").read().split("rows = []")[0]
exec(src)                                              # legs, W, Wm, names, gk, A, T, mask, St, cols, K ...
base=-np.abs(K[:,None]-St[None,:]); print("distance-from-spot baseline:", [round(x,3) for x in scores(base,T,mask)])
sh=pd.Series(T.values.ravel()).value_counts(normalize=True).sort_index().values
def bandify(M):
    q=np.quantile(M[np.isfinite(M)],np.cumsum(sh)[:-1]); return np.digitize(M,q)
def build(ivmode,kind,gname,combo):
    ci=names.index(combo); g=["gamma","vega","avanna","adelta","charm","one"].index(gname)
    M=np.zeros((len(K),len(cols)))
    for j,t in enumerate(cols):
        Tt=np.maximum((expT-pd.Timestamp(t).value)/1e9/(365*86400),300/(365*86400))
        iv=ivs if ivmode=="snapshot" else np.where(np.isfinite(ivl.loc[t].values)&(ivl.loc[t].values>0),ivl.loc[t].values,ivs)
        if kind=="per-strike": M[:,j]=A@(gk(St[j],Kl,Tt,iv,cpv)[g]*Wm[j][:,ci])
        else: M[:,j]=gk(K[:,None],Kl[None,:],Tt[None,:],iv[None,:],cpv[None,:])[g]@Wm[j][:,ci]
    return M
if __name__=="__main__":
    picks=[("live","price-grid","gamma",("+week","oicum","sum"),"time_peak","#1 live IV · price grid · γ · OI + traded · 0DTE→Fri"),
           ("live","price-grid","gamma",("all 6","oicum","sum"),"time_peak","#2 same, all 6 expiries"),
           ("live","price-grid","gamma",("0DTE","oicum","sum"),"time_peak","same, 0DTE only"),
           ("snapshot","per-strike","gamma",("0DTE","oi","sum"),"strike_peak","OUR CURRENT Tetris A (0DTE · OI×γ · per-strike peak)")]
    fig,ax=plt.subplots(3,2,figsize=(18,15),facecolor="#0b0f14"); ax=ax.ravel()
    ax[0].imshow(plt.imread("ag21.png")); ax[0].axis("off"); ax[0].set_title("AG 21 Oct",color="#ddd")
    def show(a,B,title):
        a.imshow(B,origin="lower",aspect="auto",cmap=ListedColormap(AG),vmin=-.5,vmax=6.5,extent=[0,B.shape[1],K[0]-2.5,K[-1]+2.5])
        a.plot(np.arange(len(cols))+.5,St,"w",lw=1.2); a.set_title(title,color="#ddd",fontsize=10)
        a.set_xticks(range(0,len(cols),24)); a.set_xticklabels([f"{t:%H:%M}" for t in cols[::24]],color="#aaa",fontsize=8); a.tick_params(colors="#aaa")
    show(ax[1],T.values,"AG 21 Oct re-gridded")
    for a,(ivm,kd,gn,cb,nn,ttl) in zip(ax[2:],picks):
        M=build(ivm,kd,gn,cb)
        X=M/(np.abs(M).max(axis=0,keepdims=True)+1e-12) if nn=="time_peak" else M/(np.abs(M).max(axis=1,keepdims=True)+1e-12)
        sc=scores(X,T,mask); show(a,bandify(X),f"{ttl}\noverall {sc[0]:.2f} · over time {sc[1]:.2f} · across strikes {sc[2]:.2f}")
    fig.tight_layout(); fig.savefig("compare21.png",dpi=62,facecolor="#0b0f14")
