import numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, warnings; warnings.filterwarnings("ignore")
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image
RIDGE=LinearSegmentedColormap.from_list("r",[(0,"#1b6f8f"),(0.35,"#22d3ee"),(0.6,"#a3e635"),(0.8,"#facc15"),(1,"#fb923c")])
ks=list(range(7790,7645,-5))
o=pd.read_pickle("../l21/opt.pkl"); s=pd.read_pickle("../l21/spot.pkl"); o=o[o.strike.isin(ks)].copy()
o["prem"]=o.volume*o.close*100
allm=pd.date_range("2026-10-19 20:15","2026-10-20 10:36",freq="1min")
def mat(col):
    x=o.pivot_table(index="t",columns="strike",values=col,aggfunc="sum").reindex(allm).fillna(0)
    return x.reindex(columns=ks).fillna(0)
win=pd.date_range("2026-10-20 07:00","2026-10-20 10:36",freq="1min")
def X(t):
    m=(t-pd.Timestamp("2026-10-20 07:00")).total_seconds()/60
    return np.where(m<150, m*0.6, 90+(m-150))
def variants():
    V=mat("volume"); Pm=mat("prem")
    def z(Vv,W):
        b=Vv.shift(1); med=b.rolling(W,min_periods=5).median(); mad=(b-med).abs().rolling(W,min_periods=5).median()
        return ((Vv-med)/(1.4826*mad+1)).clip(lower=0)
    def ratio(Vv,W):
        med=Vv.shift(1).rolling(W,min_periods=5).median(); return np.log1p(Vv/(med+1))
    yield "A · v0.16.2: premium $/min, one linear scale", Pm.rolling(3,center=True,min_periods=1).mean()
    yield "B · contracts/min, one linear scale", V
    yield "C · unusualness: robust z vs own last 30 min", z(V,30)
    yield "D · log(contracts ÷ own 60-min median)", ratio(V,60)
    yield "E · unusualness z vs own last 60 min (3-min smooth)", z(V.rolling(3,center=True,min_periods=1).mean(),60)
    yield "F · sqrt contracts/min, one scale", np.sqrt(V)
def draw(ax, M, title, act):
    M=M.reindex(win); q=np.nanmax(M.values) or 1
    xs=X(win)
    for i,k in enumerate(ks[::-1]):           # back first: high strikes at top
        k=ks[i]; y0=(len(ks)-1-i)*1.0
        h=M[k].values/q*3.0
        ax.plot(xs, y0+h, color=RIDGE(act[k]), lw=1.1)
    ss=s.reindex(win,method="nearest"); ax.plot(xs,(ss.values-ks[-1])/5,"w",lw=1.3)
    ax.axvline(90,color="#33415f",lw=0.8,ls=":")
    ax.set_facecolor("#0d1530"); ax.set_xlim(0,X(win[-1:])[0]*1.08); ax.set_ylim(-1,len(ks)+3)
    ax.set_yticks([0,10,20,28]); ax.set_yticklabels([ks[-1],ks[-11],ks[-21],ks[0]],fontsize=7,color="#9aa")
    ax.set_xticks([0,60,90,120,150]); ax.set_xticklabels(["07:00","08:40","09:30","10:00","10:30"],fontsize=7,color="#9aa")
    ax.set_title(title,fontsize=9,color="#ddd")
fig=plt.figure(figsize=(16,15),facecolor="#0b0f14")
ax=fig.add_subplot(4,2,1); ax.imshow(Image.open("ag_ridge.png").crop((0,60,460,420))); ax.axis("off"); ax.set_title("AG 20 Oct (07:00–10:36 ET)",color="#ddd",fontsize=10)
V=mat("volume"); tot=V.reindex(win).sum(); act=((tot/tot.max())**1.6).to_dict()
for j,(t,M) in enumerate(variants()):
    draw(fig.add_subplot(4,2,j+2),M,t,act)
fig.tight_layout(); fig.savefig("ridge_variants.png",dpi=70,facecolor="#0b0f14")
