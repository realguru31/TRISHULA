import numpy as np, pandas as pd, pickle, warnings; warnings.filterwarnings("ignore")
def rz(V,W=30,mh=10):
    b=V.shift(1); med=b.rolling(W,min_periods=mh).median(); mad=(b-med).abs().rolling(W,min_periods=mh).median()
    return (V-med)/(1.4826*mad+1)
def feats(x, near=50):
    rth=x["rth"]; S=x["S"]; o=x["o"]
    o=o.assign(bull=np.where(o.cp==1,o.askv,o.bidv), bear=np.where(o.cp==1,o.bidv,o.askv))
    vol=o.pivot_table(index="t",columns="strike",values="volume",aggfunc="sum").reindex(rth).fillna(0)
    bu=o.pivot_table(index="t",columns="strike",values="bull",aggfunc="sum").reindex(rth).reindex(columns=vol.columns).fillna(0)
    be=o.pivot_table(index="t",columns="strike",values="bear",aggfunc="sum").reindex(rth).reindex(columns=vol.columns).fillna(0)
    K=vol.columns.values.astype(float)
    N=np.abs(K[None,:]-S.values[:,None])<=near
    Zs=rz(vol).values
    f=pd.DataFrame(index=rth)
    f["S"]=S.values
    f["tot"]=(vol.values*N).sum(1)
    f["ztot"]=rz(f["tot"]).values
    f["breadth"]=((Zs>4)&N).sum(1)
    f["bull"]=(bu.values*N).sum(1); f["bear"]=(be.values*N).sum(1)
    for k in (3,5,10):
        nb=(f.bull-f.bear).rolling(k,min_periods=1).sum(); tt=(f.bull+f.bear).rolling(k,min_periods=1).sum()
        f[f"share{k}"]=nb/(tt+1); f[f"dp{k}"]=S.diff(k).values
        f[f"ztot{k}"]=f["ztot"].rolling(k,min_periods=1).max(); f[f"br{k}"]=f["breadth"].rolling(k,min_periods=1).max()
    f["dp15"]=S.diff(15).values; f["dp30"]=S.diff(30).values
    # DT-style band crossings on cumulative participant net per strike (bull−bear) since 09:30
    nf=(bu-be).cumsum(); seen={}; blue=np.zeros(len(rth)); mag=np.zeros(len(rth)); hol=np.zeros(len(rth))
    for i,t in enumerate(rth):
        sp=S.iloc[i]
        for k in K[np.abs(K-sp)<=sp*0.01]:
            cur=nf.iat[i,list(K).index(k)]; band=100.0
            n=int(abs(cur)//band)
            if n>seen.get(k,0):
                if cur>0: blue[i]+=n-seen.get(k,0)
                else: mag[i]+=n-seen.get(k,0)
                seen[k]=n
    f["dt_blue"]=blue; f["dt_mag"]=mag
    for k in (5,10): f[f"dt{k}"]=(pd.Series(blue,index=rth)-pd.Series(mag,index=rth)).rolling(k,min_periods=1).sum()
    for h in (10,20,30): f[f"fw{h}"]=S.shift(-h).values-S.values
    f["day"]=x["day"]
    return f
if __name__=="__main__":
    D=pickle.load(open("days.pkl","rb"))
    F=pd.concat([feats(x) for x in D]); F.to_pickle("F.pkl"); print(F.shape); print(F.describe().T[["mean","std","min","max"]].round(2).to_string())
