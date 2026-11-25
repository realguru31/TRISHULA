import sys, json, os, time
sys.path.insert(0, "/home/claude/trishula/trishula")
from fr import *
from core import unusual as UN
out = "/tmp/claude-0/-home-claude/dee3bb00-9e12-54e5-970a-89cb0441116b/scratchpad/unu2/seed"; os.makedirs(out, exist_ok=True)
for mkt in ("SPX", "ES", "SPY"):
    hist = []
    for day, d in DAYS.items():
        t = time.time()
        f = spx_frame(day, d) if mkt == "SPX" else x_frame(day, d, mkt)
        if not len(f): continue
        xe = day if mkt == "SPX" else (xexp(day, d, mkt) or "")
        j = UN.summary(f, mkt, pd.Timestamp(day), exp=xe, hist=hist[-10:])
        json.dump(j, open(f"{out}/{day}_{mkt}.json", "w"), separators=(",", ":"))
        hist.append(j)
        print(mkt, day, len(f), "score", j.get("score"), f"{time.time()-t:.0f}s", flush=True)
