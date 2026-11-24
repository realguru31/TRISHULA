import sys, json, glob, os
sys.path.insert(0, '/home/claude/trishula/trishula')
import numpy as np, pandas as pd
from core import lean as LN
S='/tmp/claude-0/-home-claude-trishula/fc136471-c5b1-5ac9-aa3e-34336981f738/scratchpad'
def days():
    out=[]
    for f in sorted(glob.glob(S+'/state/lean/*.json')):
        d=LN.trim(json.load(open(f)))
        if LN.rth_minutes(d)>0: out.append(d)
    return out
E=dict(bar=1, flow="0DTE", src="bar", win=20, mode="band", X=0.15, conf=True, cool=10, skip=0, hold=True)
