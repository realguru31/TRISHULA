import sys, json, glob, os
S = os.environ.get('TRS', '/tmp/claude-0/-home-claude-trishula/dff9d8c6-57a3-5af1-a46d-2b8a03bb2a16/scratchpad')
sys.path.insert(0, S + '/app/trishula')          # app code at origin/main (v0.44.0)
import numpy as np, pandas as pd
from core import lean as LN
def days():
    out = []
    for f in sorted(glob.glob(S + '/state/state/lean/*.json')):
        d = LN.trim(json.load(open(f)))
        if LN.rth_minutes(d) > 0: out.append(d)
    return out
E = dict(bar=1, flow="0DTE", src="bar", win=20, mode="band", X=0.15, conf=True, cool=10, skip=0, hold=True)
ZIPS = {'2026-11-12': 'z_20261112_close', '2026-11-16': 'z_20261116_close', '2026-11-18': 'z_20261118_close',
        '2026-11-20': 'z_20261120_close', '2026-11-23': 'z_20261123_1400', '2026-11-24': 'z_20261124_close',
        '2026-11-25': 'z_20261125_1400'}
