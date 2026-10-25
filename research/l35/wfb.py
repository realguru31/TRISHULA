import numpy as np, pandas as pd
import os; MODE=os.environ.get("MODE","01"); E=pd.read_pickle(f"l35_events_{MODE}.pkl"); E["p"]=E.p.astype(str)
days=sorted(E.day.unique()); assert len(days)==22, len(days)
folds=[(days[:i],days[i:i+3]) for i in (10,13,16,19)]
def tstat(x): return x.mean()/(x.std(ddof=1)/np.sqrt(len(x))+1e-9) if len(x)>1 else np.nan
rows=[]; picks=[]
for code,g in E.groupby("code"):
    params=g.p.unique()
    for pos in ("fewer","middle","more"):
        oos=[]; fsign=[]
        for k,(tr,te) in enumerate(folds):
            gt=g[g.day.isin(tr)]; cnt=gt.groupby("p").size().reindex(params).fillna(0)
            order=cnt.sort_values().index.tolist(); third=max(1,len(order)//3)
            cand={"fewer":order[:third],"more":order[-third:],"middle":order}[pos]
            st=[(tstat(gt[gt.p==p].edge),p) for p in cand if cnt[p]>=15]
            if not st: fsign.append(np.nan); continue
            best=max(st)[1]; ge=g[g.day.isin(te)&(g.p==best)]
            oos.append(ge.assign(fold=k,pick=best)); fsign.append(ge.edge.mean() if len(ge) else np.nan)
            picks.append((code,pos,k,best,len(ge)))
        O=pd.concat(oos) if oos else pd.DataFrame(columns=["edge","r20"])
        fpos=sum(1 for v in fsign if v==v and v>0); nf=sum(1 for v in fsign if v==v)
        t=tstat(O.edge) if len(O) else np.nan
        ok=bool(len(O) and O.edge.mean()>0 and t>=2 and fpos>=3)
        rows.append(dict(code=code,position=pos,n_oos=len(O),per_day=round(len(O)/12,1),hit=round(100*(O.r20>0).mean()) if len(O) else None,
                         edge20=round(O.edge.mean(),2) if len(O) else None,t=round(t,2) if t==t else None,folds_pos=f"{fpos}/{nf}",PASS=ok,
                         last_pick=picks[-1][3] if picks and picks[-1][0]==code and picks[-1][1]==pos else None))
R=pd.DataFrame(rows); pd.set_option("display.width",220); print(R.to_string(index=False))
R.to_csv(f"wf_result_{MODE}.csv",index=False); pd.DataFrame(picks,columns=["code","position","fold","pick","n_test"]).to_csv(f"wf_picks_{MODE}.csv",index=False)
