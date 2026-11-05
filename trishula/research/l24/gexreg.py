import numpy as np, pandas as pd, glob, warnings; warnings.filterwarnings("ignore")
from scipy.stats import norm
exec(open("idea3.py").read().split("\nrows=[]")[0])          # D, F, events, prep, squares_cd, bursts, W1, W2
OIH="/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/oih"
def morning_oi(day):
    sm=pd.read_parquet(f"{OIH}/{day.replace('-','')}/summary.parquet"); lg=pd.read_parquet(f"{OIH}/{day.replace('-','')}/legs.parquet")
    m=lg[lg.exp==day].merge(sm[["sym","oi"]],on="sym",how="left")
    return m
reg={}
for x in D:
    day=x["day"]; m=morning_oi(day); S=x["S"]; o=x["o"]
    # ATM IV from the 09:35 straddle
    t5=x["rth"][5]; s0=S.iloc[5]; atm=round(s0/5)*5
    pr=o[(o.t==t5)&(o.strike==atm)].groupby("cp").close.last()
    T0=(pd.Timestamp(f"{day} 16:00")-t5).total_seconds()/(365*86400)
    iv=float(np.clip((pr.sum() if len(pr)==2 else s0*0.002)/(0.8*s0*np.sqrt(T0)),0.06,0.6))
    K=m.strike.values; cp=m.cp.values; oi=m.oi.fillna(0).values
    g=[]
    for t,s in S.items():
        T=max((pd.Timestamp(f"{day} 16:00")-t).total_seconds()/(365*86400),300/(365*86400))
        d1=(np.log(s/K)+0.5*iv*iv*T)/(iv*np.sqrt(T)); gm=norm.pdf(d1)/(s*iv*np.sqrt(T))
        g.append((np.where(cp==1,1,-1)*oi*gm*100*s*s*0.01).sum())
    reg[day]=pd.Series(g,index=x["rth"])
    print(day,"iv",round(iv,3),"GEX at open $%.2fB"%(g[0]/1e9),"share of minutes GEX>0: %.0f%%"%(100*np.mean(np.array(g)>0)),flush=True)
F["gex"]=pd.concat(reg.values())
rows=[]
for mode,cool in (("v2",10),("v2",0),("yours",0),("yours",5)):
    G=F.join(pd.concat([bursts(x,squares_cd(x,mode,cool),2) for x in D]).rename("sig"))
    for thr in (1,2,3):
        dirn=np.sign(G.sig)*(np.abs(G.sig)>=thr); pos=G.gex>0
        rules={"follow always":(dirn>0,dirn<0),"fade always":(dirn<0,dirn>0),
               "GEX switch: +GEX fade, −GEX follow":(((~pos)&(dirn>0))|(pos&(dirn<0)),((~pos)&(dirn<0))|(pos&(dirn>0))),
               "only −GEX, follow":((~pos)&(dirn>0),(~pos)&(dirn<0)),"only +GEX, fade":(pos&(dirn<0),pos&(dirn>0)),
               "only +GEX, follow":(pos&(dirn>0),pos&(dirn<0))}
        for rn,(u,d) in rules.items():
            res={}
            for wn,wd in (("w1",W1),("w2",W2),("all",W1+W2)):
                mm=G.day.isin(wd); E=events(G[mm],u[mm],d[mm])
                res[wn]=(len(E),E.r20.mean() if len(E) else np.nan,(E.r20>0).mean() if len(E) else np.nan,f"{(E.groupby('day').r20.mean()>0).sum()}/{E.day.nunique()}" if len(E) else "-")
            rows.append(dict(dt=mode,cool=cool,thr=thr,rule=rn,**{f"{k}_{w}":v for w in res for k,v in zip(("n","r20","hit","days"),res[w])}))
R=pd.DataFrame(rows); R["both"]=(R.r20_w1>0)&(R.r20_w2>0)&(R.n_w1>=8)&(R.n_w2>=8); R.to_pickle("gexreg.pkl")
pd.set_option("display.width",250)
print(R.round(2).to_string(index=False))
print(R.groupby("rule").both.mean().round(2))
