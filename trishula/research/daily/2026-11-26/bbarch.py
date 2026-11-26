# Rebuild the SPX BB archive from trishula-state git history. First: git log --reverse --format="%H %cI" origin/trishula-state -- state/bb_history.json > $S/work/bbcommits.txt ; then python3 bbarch.py $S
import subprocess,json,sys
S=sys.argv[1]; L=[l.split() for l in open(S+'/work/bbcommits.txt')]
best={}; bests={}; alerts={}
for i,(h,t) in enumerate(L):
    if i%30 and i!=len(L)-1: continue
    try: d=json.loads(subprocess.check_output(['git','show',h+':state/bb_history.json']))
    except Exception as e: continue
    for k,v in d.get('series',{}).items():
        if len(v)>len(best.get(k,[])): best[k]=v
    for k,v in d.get('strad',{}).items():
        if len(v)>len(bests.get(k,[])): bests[k]=v
    for a in d.get('alerts',[]): alerts[tuple(map(str,a))]=a
out={'series':best,'strad':bests,'alerts':sorted(alerts.values())}
json.dump(out,open(S+'/work/bb_archive.json','w'))
for k in sorted(best): print(k,len(best[k]),best[k][0][0],best[k][-1][0],len(bests.get(k,[])))
