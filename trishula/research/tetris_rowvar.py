from oi_model import *
from scipy.ndimage import gaussian_filter1d
import matplotlib.image as mpimg
MAG=["#7a1fa2","#d36ad6","#7fd1e8","#1f4fa8","#d12b1f","#f08a24","#e8cf8a"]
sp2=spot[(spot.index>=t0)&(spot.index<=t1)]
g=grid.copy(); g["iv0"]=g.groupby(["strike","cp"])["iv"].transform("median").fillna(0.2)
S0=float(g.S.iloc[0])
def greeks(S):
    K,T,v=g.strike,g["T"],g.iv0
    d1=(np.log(S/K)+0.5*v*v*T)/(v*np.sqrt(T))
    return norm.pdf(d1)/(S*v*np.sqrt(T)), S*norm.pdf(d1)*np.sqrt(T)/100
gam_live,veg_live=greeks(g.S); gam_fix,veg_fix=greeks(pd.Series(S0,index=g.index))
g["cflow"]=(g.groupby(["strike","cp"])["buy"].cumsum()+g.groupby(["strike","cp"])["sell"].cumsum())   # traded so far
def F(e,smooth=0):
    M=g.assign(e=e).pivot_table(index="strike",columns="b",values="e",aggfunc="sum").reindex(index=ks,columns=idx).fillna(0)
    if smooth: M=pd.DataFrame(gaussian_filter1d(M.values,smooth,axis=0),index=ks,columns=idx)
    return M.div(M.max(axis=1).replace(0,np.nan),axis=0).fillna(0)
V={"A · OI·γ live spot · per-strike max":F(g.oi*gam_live),
   "B · OI·γ FIXED spot (19:00) · per-strike max":F(g.oi*gam_fix),
   "C · (OI + traded)·γ live · per-strike max":F((g.oi+g.cflow)*gam_live),
   "D · (OI + traded)·γ live · smoothed ±15":F((g.oi+g.cflow)*gam_live,3),
   "E · OI·vega live · per-strike max":F(g.oi*veg_live),
   "F · (OI + traded)·vega · smoothed ±15":F((g.oi+g.cflow)*veg_live,3)}
pd.to_pickle(V,"rowvar.pkl")
fig,axs=plt.subplots(2,4,figsize=(30,11),facecolor="#1b2440")
axs[0,0].imshow(mpimg.imread("ag16_inset.png")); axs[0,0].axis("off"); axs[0,0].set_title("AG inset",color="w",loc="left")
axs[1,0].imshow(mpimg.imread("ag16_inset.png")[::-1]); axs[1,0].axis("off"); axs[1,0].set_title("AG inset flipped vertically",color="w",loc="left")
for ax,(t,M) in zip(list(axs[0,1:])+list(axs[1,1:]),V.items()):
    ax.pcolormesh(idx,ks,M.clip(0,1).values,cmap=ListedColormap(MAG),norm=BoundaryNorm(np.linspace(0,1,8),7),shading="nearest")
    ax.plot(sp2.index,sp2.values,color="white",lw=1.4); ax.set_title(t,color="w",fontsize=10,loc="left"); ax.tick_params(colors="#c9d1d9",labelsize=7)
plt.tight_layout(); plt.savefig("rowvar.png",dpi=55,facecolor=fig.get_facecolor())
