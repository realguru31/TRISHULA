exec(open("../l34/l34.py").read().split("rows=[]")[0].replace('B="/tmp','B="/tmp'))
import numpy as np, pandas as pd
def field(L,S,day,model):
    idx=pd.date_range(f"{day} 09:30",f"{day} 15:50",freq=TT.BUCKET)
    Sb=S.groupby(S.index.floor(TT.BUCKET)).last().reindex(idx).ffill().bfill(); s0=float(Sb.iloc[0])
    LL=L[(L.strike-s0).abs()<=200]; M=TT.greek_field(LL,Sb,pd.Timestamp(f"{day} 16:00"),model)
    ks=M.index.values; keep=np.abs(ks-s0)<=100
    return M[keep]
def bands_ag(Msub):
    V=Msub.div(Msub.abs().max(axis=1).replace(0,np.nan),axis=0).fillna(0).values
    q=np.quantile(V,np.cumsum(TT.AG_SHARE)[:-1]); return np.digitize(V,q)
rows=[]
for x in days:
    S=x["S"].dropna(); day=x["day"]; fw={h:S.shift(-h)-S for h in (10,20,30)}; valid=fw[20].dropna().index
    for model in ("A","E"):
        M=field(x["L"],S,day,model); ks=M.index.values; cols=M.columns; prev=None; last={"V1":None,"V2":None}
        mu=float(fw[20].loc[valid].mean())
        for j in range(3,len(cols)):
            te=cols[j]+pd.Timedelta(minutes=10)
            if te not in S.index: continue
            Bn=bands_ag(M.iloc[:,:j+1]); warm=Bn>=4
            if prev is not None:
                newly=warm[:, :j] & ~prev[:, :j] if prev.shape[1]>=j else warm[:, :j]
                # V1
                k=np.argmin(np.abs(ks-S[te]))
                if warm[k,j] and not (prev.shape[1]==j and prev[k,j-1] and False) and te>=pd.Timestamp(f"{day} 10:00"):
                    was=prev[k,-1] if prev.shape[1]>0 else False
                    mv=S[te]-S.get(te-pd.Timedelta(minutes=30),np.nan)
                    if not was and mv==mv and abs(mv)>=3 and (last["V1"] is None or te-last["V1"]>=pd.Timedelta(minutes=30)) and te in valid:
                        d=-int(np.sign(mv)); last["V1"]=te
                        rows.append(dict(day=day,model=model,var="V1",t=te,d=d,r10=fw[10].get(te,np.nan)*d,r20=fw[20][te]*d,r30=fw[30].get(te,np.nan)*d,edge=fw[20][te]*d-mu*d))
                # V2
                w30=S[te-pd.Timedelta(minutes=30):te]; hi,lo=w30.max(),w30.min()
                for ext,d in ((hi,-1),(lo,1)):
                    if abs(ext-S[te])<5: continue
                    near=np.abs(ks-ext)<=10
                    cmask=np.zeros(j,bool); cmask[max(0,j-3):j]=True
                    if (newly[near][:,cmask]).any() and (last["V2"] is None or te-last["V2"]>=pd.Timedelta(minutes=30)) and te in valid:
                        last["V2"]=te
                        rows.append(dict(day=day,model=model,var="V2",t=te,d=d,r10=fw[10].get(te,np.nan)*d,r20=fw[20][te]*d,r30=fw[30].get(te,np.nan)*d,edge=fw[20][te]*d-mu*d))
                        break
            prev=warm
R=pd.DataFrame(rows); R.to_pickle("l43_events.pkl")
for (m,v),g in R.groupby(["model","var"]):
    t=g.edge.mean()/(g.edge.std()/np.sqrt(len(g))+1e-9) if len(g)>1 else np.nan
    dp=(g.groupby("day").edge.mean()>0).mean()
    print(f"{m} {v}: n {len(g):3d} on {g.day.nunique():2d} days · right {100*(g.r20>0).mean():3.0f}% · pts@10 {g.r10.mean():+.2f} @20 {g.r20.mean():+.2f} @30 {g.r30.mean():+.2f} · edge20 {g.edge.mean():+.2f} · t {t:.2f} · days+ {100*dp:.0f}%")
