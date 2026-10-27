exec(open("base15.py").read().split("P=[")[0])
g["vega"]=g.S*norm.pdf(d1)*np.sqrt(g["T"])/100
pre=np.asarray(idx<rth)
def sc(M):
    M=M.abs(); out=M.copy()
    for m in (pre,~pre):
        q=np.nanpercentile(M.values[:,m],99) or 1; out.loc[:,m]=(M.loc[:,m]/q).clip(0,1).values
    return out
P=[("15-Oct signed + flow · γ-weighted (C+P)", field((g.B15+g.run_all)*g.gam)),
   ("15-Oct signed + flow · vega-weighted (C+P)", field((g.B15+g.run_all)*g.vega)),
   ("15-Oct signed + flow · γ-weighted bullish", field((g.B15+g.run_all)*g.gam*bull)),
   ("all-prior signed + flow · vega-weighted bullish", field((g.Bcum+g.run_all)*g.vega*bull)),
   ("15-Oct signed + flow · contracts (C+P)", field(g.B15+g.run_all)),
   ("all-prior signed + flow · γ-weighted (C+P)", field((g.Bcum+g.run_all)*g.gam))]
fig,axs=plt.subplots(2,4,figsize=(28,11),facecolor="#1b2440")
import matplotlib.image as mpimg
axs[0,0].imshow(mpimg.imread("ag16_inset.png")); axs[0,0].axis("off"); axs[0,0].set_title("AG inset (Central)",color="w",loc="left")
axs[1,0].imshow(mpimg.imread("ag16_inset.png")[::-1]); axs[1,0].axis("off"); axs[1,0].set_title("AG inset flipped vertically",color="w",loc="left")
for ax,(t,M) in zip(list(axs[0,1:])+list(axs[1,1:]),P):
    ax.pcolormesh(idx,ks,sc(M).values,cmap=ListedColormap(MAG),norm=BoundaryNorm(np.linspace(0,1,8),7),shading="nearest")
    ax.plot(sp2.index,sp2.values,color="white",lw=1.4); ax.set_title(t+" · overnight/RTH scaled apart",color="w",fontsize=9,loc="left"); ax.tick_params(colors="#c9d1d9",labelsize=7)
plt.tight_layout(); plt.savefig("base15b.png",dpi=55,facecolor=fig.get_facecolor())
