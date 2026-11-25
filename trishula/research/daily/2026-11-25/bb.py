import json,sys,numpy as np,pandas as pd
S=sys.argv[1]; H=json.load(open(S+'/state/state/bb_history.json'))
out=[]
for day in sorted(H['series']):
    s=pd.DataFrame(H['series'][day]); s.columns=['t','spot','src','ck','cb','ca','pk','pb','pa']
    s['t']=pd.to_datetime(s.t); s=s[(s.t>=pd.Timestamp(day+' 09:30'))&(s.t<=pd.Timestamp(day+' 16:00'))]
    s['w']=s.ck-s.pk
    w=s.set_index('t').w.resample('1min').last().ffill()
    sd=pd.DataFrame(H['strad'][day],columns=['t','k','strad']); sd['t']=pd.to_datetime(sd.t)
    sd=sd[(sd.t>=pd.Timestamp(day+' 09:30'))&(sd.t<=pd.Timestamp(day+' 16:00'))&(sd.strad>0)].set_index('t').strad
    m=pd.DataFrame({'w':w,'s':sd}).dropna(); m=m[m.w>0]
    m['r']=m.w/m.s; ro=m.r.rolling(30,min_periods=10); m['z']=(m.r-ro.mean())/ro.std()
    for h in (15,30,60):
        m[f'dw{h}']=(m.w.shift(-h)/m.w-1)*100; m[f'ds{h}']=(m.s.shift(-h)/m.s-1)*100
    # episodes: first |z|>2 then 30-min cooldown per sign
    last={1:None,-1:None}; ev=[]
    for t,z in m.z.items():
        if z==z and abs(z)>2:
            sg=int(np.sign(z))
            if last[sg] is None or (t-last[sg])>=pd.Timedelta('30min'): ev.append((t,sg)); last[sg]=t
    for t,sg in ev:
        r=m.loc[t]; out.append(dict(day=day,t=t.time(),sign=sg,z=round(r.z,2),**{k:r[k] for k in ['dw15','ds15','dw30','ds30','dw60','ds60']}))
    base=m[[c for c in m if c.startswith('d')]].mean().round(2).to_dict(); print(day,'minutes',len(m),'baseline mean %chg',base)
E=pd.DataFrame(out); pd.set_option('display.width',200)
print(E.round(1).to_string(index=False))
print(E.groupby('sign')[['dw15','ds15','dw30','ds30','dw60','ds60']].agg(['mean','count']).round(1).to_string())
