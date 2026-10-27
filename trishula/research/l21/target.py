import numpy as np, pandas as pd
from PIL import Image
AG=["#7a1fa2","#d36ad6","#7fd1e8","#1f4fa8","#d12b1f","#f08a24","#e8cf8a"]
def hx(h): return np.array([int(h[i:i+2],16) for i in (1,3,5)],float)
P=np.array([hx(h) for h in AG]); Pn=P/P.max(axis=1,keepdims=True)
def classify(px):
    px=px.reshape(-1,3).astype(float); mx=px.max(axis=1)
    ok=(mx>70)&~((px.min(axis=1)>200))
    n=px[ok]/mx[ok,None]
    d=((n[:,None,:]-Pn[None,:,:])**2).sum(-1)
    return np.argmin(d,axis=1)
def build(path, base, x0, pxh, a, slope, tmin, tmax, kmin, kmax, step_min=5, kstep=5, r=3):
    im=np.asarray(Image.open(path).convert("RGB"))
    ts=pd.date_range(tmin,tmax,freq=f"{step_min}min"); ks=np.arange(kmin,kmax+kstep,kstep)
    T=np.full((len(ks),len(ts)),np.nan)
    for j,t in enumerate(ts):
        x=int(round(x0+(t-pd.Timestamp(base)).total_seconds()/3600*pxh))
        for i,k in enumerate(ks):
            y=int(round(a+slope*k))
            if not(r<=x<im.shape[1]-r and r<=y<im.shape[0]-r): continue
            c=classify(im[y-r:y+r+1,x-r:x+r+1])
            if len(c)>=5: T[i,j]=np.bincount(c,minlength=7).argmax()
    return pd.DataFrame(T,index=ks,columns=ts)
