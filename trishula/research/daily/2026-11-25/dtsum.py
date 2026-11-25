import pandas as pd, numpy as np, sys
S=sys.argv[1]
C=pd.read_pickle(S+'/work/dt_card.pkl'); B=pd.read_pickle(S+'/work/base.pkl')
for h in (10,20,30):
    m=B[B.h==h].set_index('day').long_mean; C[f'b{h}']=C.day.map(m)*C.d; C[f'x{h}']=C[f'fw{h}']-C[f'b{h}']
C.loc[C.src=='DTv2','type']=C.type
fg=C[(C.type=='follow')&(C.gex_pos==True)].assign(type='follow·GEX>0')
C2=pd.concat([C,fg])
def summ(g):
    m=g.dropna(subset=['fw20'])
    return pd.Series(dict(n=len(g),days=g.day.nunique(),fw10=g.fw10.mean(),fw20=m.fw20.mean(),fw30=g.fw30.mean(),hit20=(m.fw20>0).mean(),rand20=m.b20.mean(),edge20=m.x20.mean(),edge30=g.x30.mean(),
        t20=m.x20.mean()/(m.x20.std(ddof=1)/np.sqrt(len(m))) if len(m)>2 else np.nan, days_pos=f"{(m.groupby('day').x20.mean()>0).sum()}/{m.day.nunique()}"))
pd.set_option('display.width',250)
print('ALL days'); print(C2.groupby('type').apply(summ).round(2).to_string())
print('\nTODAY 25 Nov'); print(C2[C2.day=='2026-11-25'].groupby('type').apply(summ).round(2).to_string())
print('\nbaseline |move| per h:',B.groupby('h').abs_mean.mean().round(2).to_dict())
