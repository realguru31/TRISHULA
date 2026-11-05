import numpy as np, pandas as pd
from PIL import Image
im=np.asarray(Image.open("ag_ridge.png").convert("RGB")).astype(int)
Y0=60; R=im[Y0:420,0:460]
mx=R.max(2); mn=R.min(2); sat=mx-mn
ridge=(sat>55)&(mx>100)&~(mn>190)
base=[40,47,54,62,70,78,86,95,103,112,121,131,140,150,161,171,182,193,205,217,229,241,255,268,282,297,312,328,344]
strikes=[7790-5*i for i in range(len(base))]
H=np.full((len(base),460),np.nan)
for i,b in enumerate(base):
    col=np.median(R[b-1:b+2,40:200].reshape(-1,3),axis=0)
    up=base[i-1] if i>0 else b-12
    lo=up+2
    for x in range(460):
        ys=np.arange(max(lo,0),b+3)
        cand=[y for y in ys if ridge[y,x] and np.abs(R[y,x]-col).sum()<110]
        if cand: H[i,x]=b-min(cand)
    # floor at flat left region
out=pd.DataFrame(H,index=strikes)
out.to_pickle("H_raw.pkl")
# per ridge: right end and open step
info=[]
for i,b in enumerate(base):
    h=H[i]; xs=np.where(np.isfinite(h))[0]
    xe=xs.max() if len(xs) else np.nan
    left=np.nanmedian(h[20:200]); 
    sm=pd.Series(h).rolling(9,center=True,min_periods=3).median()
    step=np.nan
    for x in range(200,int(xe)-5):
        if sm[x]>=left+1.0 and np.nanmedian(sm[x:x+15])>=left+1.0: step=x; break
    info.append((strikes[i],b+Y0,xe,left,step))
info=pd.DataFrame(info,columns=["strike","y","x_end","floor_px","x_open"]); print(info.to_string())
info.to_pickle("info.pkl")
