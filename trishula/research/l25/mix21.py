import sys; sys.path.insert(0,"/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/l25")
exec(open("render21.py").read().split('if __name__=="__main__":')[0])
import numpy as np
B=build("live","price-grid","gamma",("+week","oicum","sum")); Bn=B/(np.abs(B).max(axis=0,keepdims=True)+1e-12)
flows={}
for fname,cb,iv in (("net puts (0DTE)",("0DTE","net","puts"),"snapshot"),("net puts (+week)",("+week","net","puts"),"snapshot"),
                    ("bear flow (+week)",("+week","bear","sum"),"live"),("net all C−P (+week)",("+week","net","c_minus_p"),"live"),
                    ("net calls (+week)",("+week","net","calls"),"live")):
    F=build(iv,"price-grid","gamma",cb); flows[fname]=F
rows=[]
for fname,F in flows.items():
    for sgn in (1,-1):
        Fz=sgn*F/(np.nanmax(np.abs(F))+1e-12)
        for lam in (0.1,0.25,0.5,1,2):
            sc=scores(Bn+lam*Fz,T,mask); rows.append((fname,sgn,lam)+tuple(round(x,3) for x in sc))
R=pd.DataFrame(rows,columns=["flow","sign","λ","overall","over_time","across"]); R["combo"]=R.overall+R.over_time
print(R.sort_values("combo",ascending=False).head(15).to_string(index=False))
R.to_pickle("mix21.pkl")
