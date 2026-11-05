import sys, numpy as np, pandas as pd, plotly.graph_objects as go, plotly.io as pio
exec(open("oi_model.py").read().split('if __name__=="__main__":')[0])
V=pd.read_pickle("rowvar.pkl"); key=sys.argv[1]; out=sys.argv[2]
M=[v for k,v in V.items() if k.startswith(key)][0].clip(0,1)
MAG=["#7a1fa2","#d36ad6","#7fd1e8","#1f4fa8","#d12b1f","#f08a24","#e8cf8a"]
import os
if os.environ.get("CAL"):
    target=np.array([0.37,0.05,0.20,0.33,0.03,0.015,0.005])          # AG colour shares (purple → tan), measured from his inset
    edges=np.quantile(M.values.ravel(),np.cumsum(target)[:-1])
    band=np.clip(np.digitize(M.values,edges),0,6)
else:
    band=np.clip(np.digitize(M.values,np.linspace(0,1,8)[1:-1]),0,6)
Hh=M.values*2-1
X,Y,Z,I,J,K,FC=[],[],[],[],[],[],[]
tri=[(0,1,2),(0,2,3),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
gap=0.14; base=-1.0; ks_=M.index.values
for i,k in enumerate(ks_):
    for j in range(M.shape[1]):
        top=max(float(Hh[i,j]),base+0.03); x0,x1=j+gap,j+1-gap; y0,y1=k-2.5+0.6,k+2.5-0.6; n=len(X)
        for (x,y,z) in [(x0,y0,base),(x1,y0,base),(x1,y1,base),(x0,y1,base),(x0,y0,top),(x1,y0,top),(x1,y1,top),(x0,y1,top)]:
            X.append(x);Y.append(y);Z.append(z)
        for a,b,c in tri: I.append(n+a);J.append(n+b);K.append(n+c);FC.append(MAG[band[i,j]])
f=go.Figure(go.Mesh3d(x=X,y=Y,z=Z,i=I,j=J,k=K,facecolor=FC,flatshading=True,lighting=dict(ambient=0.85,diffuse=0.45,specular=0.05,roughness=0.9),lightposition=dict(x=-1e4,y=-2e4,z=3e4),hoverinfo="skip"))
sp2=spot[(spot.index>=t0)&(spot.index<=t1)]; tx=np.asarray((sp2.index-t0)/pd.Timedelta(minutes=10))
ki=np.clip(np.searchsorted(ks_,sp2.values),0,len(ks_)-1); ji=np.clip(tx.astype(int),0,M.shape[1]-1); zl=Hh[ki,ji]+0.06
f.add_scatter3d(x=tx,y=sp2.values,z=zl,mode="lines",line=dict(color="white",width=7),hoverinfo="skip")
f.add_scatter3d(x=[tx[-1]+3],y=[sp2.values[-1]],z=[zl[-1]+0.15],mode="text",text=[f"<b>{sp2.values[-1]:,.2f}</b>"],textfont=dict(color="#ff4d4d",size=15))
tickv=list(range(0,M.shape[1],24)); tickt=[(t0+pd.Timedelta(minutes=10*v)).strftime("%H:%M") for v in tickv]
BG="#1e2a4a"; ax=dict(backgroundcolor=BG,gridcolor="#2c3a63",color="#c9d1d9",showbackground=True,title="")
f.update_layout(paper_bgcolor=BG,height=780,width=1150,margin=dict(l=0,r=0,t=30,b=0),showlegend=False,
    title=dict(text=f"TETRIS · 16 Oct · {key} · each strike to its own peak · bands {'calibrated to AG colour shares' if os.environ.get('CAL') else 'equal'} · ET",font=dict(color="#c9d1d9",size=13),x=0.01),
    scene=dict(xaxis=dict(tickvals=tickv,ticktext=tickt,**ax),yaxis=dict(**ax),zaxis=dict(range=[-1,1.25],tickvals=[-1,0,1],**ax),
               aspectmode="manual",aspectratio=dict(x=2.0,y=1.6,z=0.32),camera=dict(eye=dict(x=0.45,y=-1.8,z=1.35))))
pio.write_html(f,out+".html",include_plotlyjs=True)
