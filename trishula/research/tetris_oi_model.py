from load16 import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
O="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/oct16oi"
AG=["#7a1fa2","#d36ad6","#7fd1e8","#1f4fa8","#d12b1f","#f08a24","#e8cf8a"]
summ=pd.read_parquet(f"{O}/summary.parquet")[["strike","cp","oi","prev_close"]]
g,spot,basis=load("10min")
t0,t1=pd.Timestamp("2026-10-15 19:00"),pd.Timestamp("2026-10-16 12:10")
ks=np.arange(7600,8055,5.0); idx=pd.date_range(t0,t1,freq="10min")
grid=pd.MultiIndex.from_product([idx,ks,[1,-1]],names=["b","strike","cp"]).to_frame(index=False)
grid=grid.merge(g[["b","strike","cp","vol","buy","sell","px"]],on=["b","strike","cp"],how="left").merge(summ,on=["strike","cp"],how="left")
grid=grid.sort_values(["strike","cp","b"])
grid["px"]=grid.groupby(["strike","cp"])["px"].ffill()
grid["px"]=grid["px"].fillna(grid["prev_close"])
for c in ("vol","buy","sell"): grid[c]=grid[c].fillna(0)
sp=spot.groupby(spot.index.floor("10min")).last(); grid["S"]=grid["b"].map(sp).ffill()
exp=pd.Timestamp("2026-10-16 16:00")
grid["T"]=np.maximum((exp-grid.b).dt.total_seconds()/(365*24*3600),1/(365*24*12))
grid["iv"]=implied_vol(grid.px.values,grid.S.values,grid.strike.values,grid["T"].values,grid.cp.values)
grid["iv"]=grid.groupby(["strike","cp"])["iv"].transform(lambda s: s.ffill().bfill())
grid["iv"]=grid["iv"].fillna(grid.groupby("b")["iv"].transform("median"))
d1=(np.log(grid.S/grid.strike)+0.5*grid.iv**2*grid["T"])/(grid.iv*np.sqrt(grid["T"]))
grid["gamma"]=norm.pdf(d1)/(grid.S*grid.iv*np.sqrt(grid["T"]))
grid["cumnet"]=grid.groupby(["strike","cp"])["buy"].cumsum()-grid.groupby(["strike","cp"])["sell"].cumsum()
grid["oi"]=grid["oi"].fillna(0)
def exposure(mode):
    # dealer convention: OI calls +, puts −; customer net buys flip the dealer the other way
    if mode=="oi":       pos=grid.cp*grid.oi
    elif mode=="oi+flow": pos=grid.cp*grid.oi - grid.cumnet
    elif mode=="flowonly": pos=-grid.cumnet
    e=pos*grid.gamma*grid.S**2*0.01*100
    return grid.assign(e=e).pivot_table(index="strike",columns="b",values="e",aggfunc="sum").reindex(index=ks,columns=idx)
if __name__=="__main__":
    sp2=spot[(spot.index>=t0)&(spot.index<=t1)]
    E1=exposure("oi+flow"); E0=exposure("oi")
    panels=[]
    q=np.nanpercentile(np.abs(E1.values),98)
    panels.append(("1 · OI+flow dealer γ · signed · global scale", (E1/q).clip(-1,1), True))
    panels.append(("2 · OI+flow dealer γ · |magnitude| · global", (E1.abs()/q).clip(0,1), False))
    colmax=E1.abs().max(axis=0)
    panels.append(("3 · OI+flow dealer γ · signed · per-time-column scale", (E1/colmax).clip(-1,1), True))
    panels.append(("4 · OI+flow dealer γ · |magnitude| · per column", (E1.abs()/colmax).clip(0,1), False))
    fig,axs=plt.subplots(2,2,figsize=(18,11),facecolor="#1b2440")
    for ax,(ttl,M,signed) in zip(axs.flat,panels):
        nb=BoundaryNorm(np.linspace(-1,1,8),7) if signed else BoundaryNorm(np.linspace(0,1,8),7)
        ax.pcolormesh(idx,ks,M.values,cmap=ListedColormap(AG),norm=nb,shading="nearest")
        ax.plot(sp2.index,sp2.values,color="white",lw=1.6)
        ax.set_title(ttl,color="w",fontsize=11,loc="left"); ax.tick_params(colors="#c9d1d9")
    plt.tight_layout(); plt.savefig("oi_cand.png",dpi=75,facecolor=fig.get_facecolor())
    print("oi total", summ.oi.sum(), "basis", basis)
