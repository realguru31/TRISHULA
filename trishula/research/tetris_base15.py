from oi_model import *
from scipy.ndimage import gaussian_filter1d
MAG=["#7a1fa2","#d36ad6","#7fd1e8","#1f4fa8","#d12b1f","#f08a24","#e8cf8a"]
sp2=spot[(spot.index>=t0)&(spot.index<=t1)]
d=pd.read_parquet(f"{O}/daily.parquet"); d["t"]=pd.to_datetime(d.ts_ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
d["base"]=d.sym.str.split("{").str[0]; d["strike"]=d.base.str[-4:].astype(float); d["cp"]=d.base.str[11].map({"C":1,"P":-1})
d["net"]=d.askv.fillna(0)-d.bidv.fillna(0)
y15=d[d.t==pd.Timestamp("2026-10-14 20:00")].groupby(["strike","cp"]).net.sum()
cum=d[d.t<=pd.Timestamp("2026-10-14 20:00")].groupby(["strike","cp"]).net.sum()
g=grid.copy(); g["iv"]=g.groupby(["strike","cp"])["iv"].transform(lambda s: s.ffill().bfill()).fillna(0.2)
d1=(np.log(g.S/g.strike)+0.5*g.iv**2*g["T"])/(g.iv*np.sqrt(g["T"]))
g["gam"]=norm.pdf(d1)/(g.S*g.iv*np.sqrt(g["T"]))*g.S**2*0.01*100
g["net"]=g.buy-g.sell
rth=pd.Timestamp("2026-10-16 09:30")
g["run_all"]=g.groupby(["strike","cp"])["net"].cumsum()
g["run_rth"]=g.assign(n=np.where(g.b>=rth,g.net,0)).groupby(["strike","cp"])["n"].cumsum()
key=list(zip(g.strike,g.cp))
g["B15"]=[y15.get(k,0.0) for k in key]; g["Bcum"]=[cum.get(k,0.0) for k in key]
def field(val, smooth=3):
    M=g.assign(e=val).pivot_table(index="strike",columns="b",values="e",aggfunc="sum").reindex(index=ks,columns=idx).fillna(0)
    return pd.DataFrame(gaussian_filter1d(M.values,smooth,axis=0),index=ks,columns=idx) if smooth else M
bull=g.cp
P=[("15-Oct signed (C+P) + all flow since 19:00 · contracts", field(g.B15+g.run_all)),
   ("15-Oct signed + flow since 19:00 · bullish-signed (calls+ puts−)", field((g.B15+g.run_all)*bull)),
   ("15-Oct signed + flow · γ-weighted (C+P)", field((g.B15+g.run_all)*g.gam)),
   ("15-Oct signed + RTH flow only · γ-weighted bullish", field((g.B15+g.run_rth)*bull*g.gam)),
   ("ALL prior days signed (≈signed OI) + flow · γ-weighted", field((g.Bcum+g.run_all)*g.gam)),
   ("ALL prior days signed + flow · contracts bullish", field((g.Bcum+g.run_all)*bull))]
fig,axs=plt.subplots(2,4,figsize=(28,11),facecolor="#1b2440")
import matplotlib.image as mpimg
axs[0,0].imshow(mpimg.imread("ag16_inset.png")); axs[0,0].axis("off"); axs[0,0].set_title("AG inset (Central)",color="w",loc="left")
axs[1,0].imshow(mpimg.imread("ag16_inset.png")[::-1]); axs[1,0].axis("off"); axs[1,0].set_title("AG inset flipped vertically (if its top = low strikes)",color="w",loc="left")
for ax,(t,M) in zip(list(axs[0,1:])+list(axs[1,1:]),P):
    M=(M.abs()/np.nanpercentile(M.abs().values,99)).clip(0,1)
    ax.pcolormesh(idx,ks,M.values,cmap=ListedColormap(MAG),norm=BoundaryNorm(np.linspace(0,1,8),7),shading="nearest")
    ax.plot(sp2.index,sp2.values,color="white",lw=1.4); ax.set_title(t,color="w",fontsize=9.5,loc="left"); ax.tick_params(colors="#c9d1d9",labelsize=7)
plt.tight_layout(); plt.savefig("base15.png",dpi=55,facecolor=fig.get_facecolor())
print("15-Oct |net| total", y15.abs().sum(), "cum |net|", cum.abs().sum())
