exec(open("l34.py").read().split("rows=[]")[0])
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
x=days[-1]; S=x["S"].dropna(); day=x["day"]
idx=pd.date_range(f"{day} 09:30",f"{day} 15:50",freq=TT.BUCKET)
Sb=S.groupby(S.index.floor(TT.BUCKET)).last().reindex(idx).ffill().bfill(); s0=float(Sb.iloc[0])
fig,ax=plt.subplots(2,2,figsize=(18,10),facecolor="#0b0f14")
for r,model in enumerate(("A","E")):
    LL=x["L"][(x["L"].strike-s0).abs()<=200]; M=TT.greek_field(LL,Sb,pd.Timestamp(f"{day} 16:00"),model)
    ks=M.index.values; keep=np.abs(ks-s0)<=100
    Vold=M.div(M.max(axis=1).replace(0,np.nan),axis=0).fillna(0)          # v0.18: whole-day peak (uses the future)
    q=np.quantile(Vold.values,np.cumsum(TT.AG_SHARE)[:-1]); Bold=np.digitize(Vold.values,q)
    Bnew=TT.bands(TT.per_strike_peak(M,0),"AG")
    for c_,(Bx,tt) in enumerate(((Bold,f"{model} · v0.18: scaled to the DAY's peak (needs the future → repaints)"),(Bnew,f"{model} · no repaint: scaled to peak SO FAR"))):
        a=ax[r,c_]; a.imshow(Bx[keep],origin="lower",aspect="auto",cmap=ListedColormap(TT.AG_COLORS),vmin=-.5,vmax=6.5,extent=[0,len(idx),ks[keep][0]-2.5,ks[keep][-1]+2.5])
        a.plot(np.arange(len(idx))+.5,Sb.values,"w",lw=1.2); a.set_title(tt,color="#ddd")
        a.set_xticks(range(0,len(idx),6)); a.set_xticklabels([f"{t:%H:%M}" for t in idx[::6]],color="#aaa"); a.tick_params(colors="#aaa")
    print(model,"cells at running peak (=1):", round(float((TT.per_strike_peak(M,0).values[keep]>=0.999).mean()),2))
fig.tight_layout(); fig.savefig("tetris_repaint_vs_causal.png",dpi=60,facecolor="#0b0f14")
