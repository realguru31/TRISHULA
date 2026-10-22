import sys; sys.path.insert(0,"/home/claude/trishula")
import numpy as np, pandas as pd, plotly.graph_objects as go, plotly.io as pio
from scipy.stats import norm
from scipy.ndimage import gaussian_filter1d
from core.classify import bucket
from load16 import implied_vol
T="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/today"
MAG=["#7a1fa2","#d36ad6","#7fd1e8","#1f4fa8","#d12b1f","#f08a24","#e8cf8a"]
MIDC="#ffe066"
et=lambda ms: pd.to_datetime(ms,unit="ms",utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
c=pd.read_parquet(f"{T}/candles.parquet"); c=c[c.ts_ms<2e12].drop_duplicates(["sym","ts_ms"],keep="last"); c["t"]=et(c.ts_ms)
ch=pd.read_parquet(f"{T}/chain.parquet")
p=pd.read_parquet(f"{T}/prints.parquet"); p=p[(p["flags"].astype(int)&2)==0].copy(); p["t"]=et(p.ts_ms)
es=c[c.sym.str.startswith("/ES")].set_index("t").sort_index().close; spx=c[c.sym.str.startswith("SPX{")].set_index("t").sort_index().close
j=pd.concat([es.rename("es"),spx.rename("spx")],axis=1,sort=True).dropna(); basis=float((j.es-j.spx).median())
spot=(es-basis); spot.update(spx)
o=c[c.sym.str.startswith(".SPXW")].copy(); o["base"]=o.sym.str.split("{").str[0]
o=o.merge(ch[["sym","strike","cp","oi","iv"]].rename(columns={"sym":"base"}),on="base",how="left")
o[["bidv","askv"]]=o[["bidv","askv"]].fillna(0)
BKT="10min"
t0=pd.Timestamp("2026-10-19 19:00"); t1=pd.Timestamp(sys.argv[1] if len(sys.argv)>1 else "2026-10-20 11:20")
idx=pd.date_range(t0,t1,freq=BKT); rth=pd.Timestamp("2026-10-20 09:30")
o["b"]=o.t.dt.floor(BKT); o["net"]=o.askv-o.bidv
legs=ch[["sym","strike","cp","oi","iv"]].dropna(subset=["strike"])
ks=np.arange(7600,7905,5.0)
legs=legs[legs.strike.isin(ks)]
# 1) "fixed" signed-OI snapshot at the open: customer sign inferred from overnight (GTH) net flow; no GTH trades → naive ×0.2
gth=o[o.t<rth].groupby("base").agg(n=("net","sum"),v=("volume","sum"))
def cust_sign(r):
    if r.sym in gth.index and gth.at[r.sym,"v"]>0: return float(np.clip(gth.at[r.sym,"n"]/gth.at[r.sym,"v"],-1,1))
    return 0.2*(-1.0 if r.cp==1 else 1.0)          # naive: customers short calls / long puts
legs=legs.assign(cs=[cust_sign(r) for r in legs.itertuples()])
# 2) RTH overlay: cumulative customer net from 09:30
rn=o[o.t>=rth].pivot_table(index="b",columns="base",values="net",aggfunc="sum").reindex(idx).fillna(0).cumsum()
S=spot.groupby(spot.index.floor(BKT)).last().reindex(idx).ffill().bfill()
Tt=np.maximum((pd.Timestamp("2026-10-20 16:00")-idx).total_seconds()/(365*24*3600),1/(365*24*12))
E=pd.DataFrame(0.0,index=ks,columns=idx); M_=pd.DataFrame(0.0,index=ks,columns=idx)
for r in legs.itertuples():
    iv=r.iv if r.iv==r.iv and r.iv>0 else 0.2
    d1=(np.log(S.values/r.strike)+0.5*iv*iv*Tt)/(iv*np.sqrt(Tt))
    vg=S.values*norm.pdf(d1)*np.sqrt(Tt)/100                           # vega
    rc=rn[r.sym].values if r.sym in rn else 0.0
    E.loc[r.strike]+=(-(r.cs*r.oi)-rc)*vg                               # dealer sign
    M_.loc[r.strike]+=(r.oi+np.abs(rc))*vg                              # size
Es=pd.DataFrame(gaussian_filter1d(E.values,sigma=3,axis=0),index=ks,columns=idx)
Ms=pd.DataFrame(gaussian_filter1d(M_.values,sigma=3,axis=0),index=ks,columns=idx)
q=np.nanpercentile(Ms.values,99) or 1.0
C=(Ms/q).clip(0,1); H=np.sign(Es)*C
band=np.clip(np.digitize(C.values,np.linspace(0,1,8)[1:-1]),0,6)
# 3) "undecided" MID trades (prints): 10-min cells where ≥40 % of ≥50 contracts printed at mid → yellow
p["bk"]=[bucket(a,b_,c_) for a,b_,c_ in zip(p.px,p.bid,p.ask)]; p["b"]=p.t.dt.floor(BKT)
pm=p.groupby(["strike","b"]).apply(lambda d: pd.Series({"v":d["size"].sum(),"m":d.loc[d.bk==2,"size"].sum()}))
mid=set(i for i,r in pm.iterrows() if r.v>=50 and r.m/r.v>=0.4)
print("basis",round(basis,2),"mid cells",len(mid), "prints span", p.t.min(), p.t.max())
X,Y,Z,I,J,K,FC=[],[],[],[],[],[],[]
tri=[(0,1,2),(0,2,3),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
gap=0.14; base=-1.0
for i,k in enumerate(ks):
    for jx,b in enumerate(idx):
        top=max(float(H.iat[i,jx]),base+0.03)
        x0,x1=jx+gap,jx+1-gap; y0,y1=k-2.5+0.6,k+2.5-0.6; n=len(X)
        for (x,y,z) in [(x0,y0,base),(x1,y0,base),(x1,y1,base),(x0,y1,base),(x0,y0,top),(x1,y0,top),(x1,y1,top),(x0,y1,top)]:
            X.append(x);Y.append(y);Z.append(z)
        col=MIDC if (k,b) in mid else MAG[band[i,jx]]
        for a,b_,c_ in tri: I.append(n+a);J.append(n+b_);K.append(n+c_);FC.append(col)
f=go.Figure(go.Mesh3d(x=X,y=Y,z=Z,i=I,j=J,k=K,facecolor=FC,flatshading=True,
            lighting=dict(ambient=0.85,diffuse=0.45,specular=0.05,roughness=0.9),lightposition=dict(x=-1e4,y=-2e4,z=3e4),hoverinfo="skip"))
sp2=spot[(spot.index>=t0)&(spot.index<=t1)]
tx=np.asarray((sp2.index-t0)/pd.Timedelta(BKT))
ki=np.clip(np.searchsorted(ks,sp2.values),0,len(ks)-1); ji=np.clip(tx.astype(int),0,len(idx)-1); zl=np.maximum(H.values[ki,ji],-0.97)+0.06
f.add_scatter3d(x=tx,y=sp2.values,z=zl,mode="lines",line=dict(color="white",width=7),hoverinfo="skip")
f.add_scatter3d(x=[tx[-1]+3],y=[sp2.values[-1]],z=[zl[-1]+0.1],mode="text",text=[f"<b>{sp2.values[-1]:,.2f}</b>"],textfont=dict(color="#ff4d4d",size=15))
op=(rth-t0)/pd.Timedelta(BKT)
f.add_scatter3d(x=[op,op],y=[ks[0],ks[-1]],z=[1.13,1.13],mode="lines",line=dict(color="#bbbbbb",width=3,dash="dash"),hoverinfo="skip")
tickv=list(range(0,len(idx),24)); tickt=[(t0+pd.Timedelta(minutes=10*v)).strftime("%H:%M") for v in tickv]
BG="#1e2a4a"; ax=dict(backgroundcolor=BG,gridcolor="#2c3a63",color="#c9d1d9",showbackground=True,title="")
f.update_layout(paper_bgcolor=BG,height=780,width=1150,margin=dict(l=0,r=0,t=30,b=0),showlegend=False,
    title=dict(text="TETRIS · 20 Oct 0DTE · colour = position-weighted vega (open OI + RTH flow, smoothed) · height = dealer sign · yellow = mostly-MID trades · ET",font=dict(color="#c9d1d9",size=12),x=0.01),
    scene=dict(xaxis=dict(tickvals=tickv,ticktext=tickt,**ax),yaxis=dict(**ax),zaxis=dict(range=[-1,1.25],tickvals=[-1,0,1],**ax),
               aspectmode="manual",aspectratio=dict(x=2.0,y=1.6,z=0.32),camera=dict(eye=dict(x=0.55,y=-1.75,z=1.25))))
pio.write_html(f,"tetris_today_vega.html",include_plotlyjs=True)
