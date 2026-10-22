# TRISHULA — RESEARCH LOG (exploration, findings, open questions)

One place for everything we explored: what is CRACKED (with the evidence), what is OPEN, and the NEXT step + the data it
needs. Build items live in TRISHULA_QUEUE.md; this file is the lab notebook. Updated 22 Oct 2026 (v0.18.0).
Scripts: research/lNN/ in the repo (no tokens). Colab pull scripts stay OUTSIDE the repo (they carry tokens).

Status legend: ✅ cracked / proven · 🟡 partly · ❌ rejected · ❓ open

---------------------------------------------------------------------------------------------------------------
## 1. AG RIDGES (his "volume per strike through time")
✅ Height = raw CONTRACTS per minute, ALL volume (not single-leg): his 7750P pane read 4,081 = our total volume at ~10:38
   on 20 Oct (single-leg would be ~3,100). Unsmoothed — his spikes are single minutes. One linear scale (research/l22).
✅ His ridges include 1DTE: 22 Oct 7750C (21 Oct morning post), 22 Oct 7720P (21 Oct afternoon post, scale 0–1.2k c/min).
✅ His window = the recent hours (11:36 → 13:16 in the 21 Oct post), not the whole overnight session.
✅ AG chart time labels are CENTRAL time (calibrated twice on his price line).
✅ ROOT CAUSE found 22 Oct: dxfeed sends 1-min candles as {=m}; the recorder only accepted "=1m" → every 1-min option
   candle was dropped since v0.16.1 (backfill always 0). Fixed in v0.18.1.
✅ Our noisy "now" edge after a restart = the 1,000-print replay cap (the past came from too few prints). v0.16.4 patched
   with 5-min candles; v0.18 rebuilds the past from 1-min candles (sweep every 5 min, 0DTE+1DTE).
🟡 v0.18 2-D ridgeline (baseline at strike, SPX on the same axis, occluding fills) LOOKS like his view; not yet compared
   minute-by-minute with one of his posts.
✅ 21 Oct full tape (Colab 22 Oct 02:15) vs his 7720P post: the spike is the 22 Oct 7720P at 14:27 ET = 13:27 CT,
   1,503 contracts, 1,500 at the ASK (bought) @ $6.80 — exactly his volume bar after his "1pm" (CT) label; his $6.45 low =
   our $6.46; his ridge jump at "11:36" = our all-strike burst + price jump at 12:37 ET (CT confirmed again). Our
   ridgeline on the same window shows the same pinned spike at the same minute (scratchpad rv/cmp_ridge.png).
   His header "vol 3,383" ≈ the contract's volume inside his window (11:00 ET → post), not the day's (4,136 by 14:35).
(was) ❓ Does our ridge show the SAME spikes at the SAME minutes as his? → NEXT: 21 Oct full-day Colab dump
   (trishula_21oct_dump.py) → our ridgeline 21 Oct 0+1DTE vs his 21 Oct 7720P post, spike by spike.

## 2. AG TETRIS
✅ Best family (two days, brute force): PRICE GRID — for each price level P, Σ legs w·greek(P, K, T, iv), not a per-strike sum.
   20 Oct (l21, 4,800 candidates): price-grid OI·|vanna| 0.81 overall / 0.38 over time; γ family top-3.
   21 Oct (l25, 25,256 candidates): LIVE IV · price grid · γ · (OI + traded since 20:15) · each TIME COLUMN scaled to its
   peak: 0DTE→Fri 0.68 / 0.51 (vs baseline 0.56 / 0.15, our old model A −0.04 / 0.20). → shipped as Tetris G (v0.18).
🟡 VISUALLY it is NOT his chart: G gives smooth horizontal layers (warm core above price, blue, purple); his has vertical
   columns that flicker bucket to bucket. The score (0.68) says the colour ORDER by price matches, not the look. (The first
   v0.18 picture was worse still: wrong colour shares + too-narrow grid — fixed 22 Oct 02:40.)
🟡 Caveat: each fit is one screenshot = one day. vanna won 20 Oct, γ won 21 Oct → could be curve fitting.
❓ His vertical COLUMNS — L30 (22 Oct, full 21 Oct data, hypotheses pre-registered in scratchpad l30/PREREG.md):
   G × activity, rolling-window traded (15/30/60 min), bucket flow only, global vs per-column scaling, OI only — NONE
   draws columns. Two variants passed the pre-registered numeric rule (rolling 15 m time-peak: overall 0.65, column 0.75;
   OI-only time-peak 0.61 / 0.71) but the PICTURES are smooth layers → the column metric was badly chosen; counted as FAIL.
   AG column colour vs activity −0.16, vs price −0.45. Leading explanation now: RENDERING — his chart is 3-D pillars seen
   at an angle; a tall pillar hides the ones behind it on screen, which reads as vertical streaks when re-gridded.
   MOCK (22 Oct 03:00, l30/pillars.py): G drawn as 3-D pillars, re-gridded at the floor like his chart → occlusion SHIFTS
   colours (front pillars cover the cells behind them) but makes NO columns: G's heights barely change through time, so
   the covering is the same in every column. → Rendering alone can't explain his columns; his pillar HEIGHTS (or colours)
   must change through time.
   Also tried 22 Oct 03:05 (exploratory, NOT pre-registered): per-strike / strike×time scaling (−0.46 … −0.08), γ × traded
   in the last 30/60/120 min without OI (best 0.62 / 0.23), change of the field over 30/60/120 min (best 0.61 / 0.33). The
   flow versions move through time but are still bands centred on price; none beats G (0.68 / 0.44). User 22 Oct: "ours
   looks like a band only" — agreed; his warm blobs (04:20–06:20 above, 05:20–06:50 below) and the purple bowl under price
   after 08:00 are NOT reproduced by any field we have tried. Open idea: height = a time-varying quantity (e.g. traded volume) while colour = gamma level.
❓ His asymmetry (warm core above spot after the open on 16 Oct).
NEXT: score Tetris G (unchanged) on his NEXT Tetris post before any change — an out-of-sample check, not a refit.
   Data: his screenshot + that day's Colab dump (OI + 1-min candles with imp_vol, 0DTE→Fri).

## 3. THE 21 OCT CAPTION ("they wanted some puts before the dip") — tape read
✅ From the tape (1-min candles): 09:40–10:00 calls 7800–7815 SOLD ~2:1 with SPX flat ~7734; puts 7715–7735 net BOUGHT;
   dip 10:00–10:11 to 7711; puts SOLD at the low. Long at the low: 22 Oct (1DTE) 7750C ~340 bought at the ask 10:05/10:08.
❌ As a rule ("loading setup" S2) it FAILED out of sample (negative on the fresh days) → dropped.
✅ The 1DTE block became S1 (aggressive block against the move).
User note (22 Oct): his captions are always "someone positioned BEFORE the news" → S7 below.

## 4. SIGNALS FROM THE TAPE (turns / fades) — locked test L29
Method: causal features only; outcome = SPX points 10/20/30 min later in the signal's direction; edge = minus 200 random
same-day same-direction entries; split halves; FRESH days = never used to design anything; 18 tests → one t≈2 expected by
chance → we want t ≈ 3. Rules locked 21 Oct 14:05 ET (research/l28/l29.py), run unchanged.
Results (20 sessions, 9 fresh: 24 Sep–5 Oct + 21 Oct; table shipped in core/data/signal_history.csv):
   S1 aggressive block vs move ×10: fresh +1.42 pts/20 min, t 2.03, n 160, 6/9 days → WATCH (closest to an edge)
   S4 DT v2 follow 2 strikes: fresh +1.81, t 1.25, n 33 → unproven (in-sample +3.4 was mostly design days)
   S1 ×5 +1.01 (t 1.5) · S5 initiation, S6 exhaustion, S3 near-spot flip → near 0 → unproven
   S2 loading setup → negative → ❌ rejected
Earlier (l24, 11 design days): most fade rules failed the holdout (regime-dependent: range week favoured fading, trend week
   following). Survivors there: initiation follow, the DT adaptive band, follow only when dealer GEX > 0 (textbook GEX switch
   failed), filled/hollow squares carry NO open-interest information.
S7 "quiet big block" (NEW, locked 22 Oct, no history): one 0/1DTE contract-minute ≥ 1,000 contracts and ≥ 10× its own
   median, ≥ 90 % one side, last 30 min range ≤ 15 pts → bought put / sold call = bearish. Example that motivated it:
   22 Oct 7720P, ~1.5k+ in one minute late on 21 Oct with SPX flat at the highs; SPX then fell hard. ONE case.
NEXT: rerun l29.py UNCHANGED (+ S7) when ~25–30 fresh days exist. Data: weekly Colab history pull (last 5 sessions) —
   tastytrade keeps ~4 weeks of expired option candles — or the 📦 day zip each evening.
✅ 22 Oct 7720P block (21 Oct 14:27 ET): 1,500 BOUGHT at the ask @ $6.80 with SPX 7,769 at the day's high and a 7-pt
   30-min range → S7 fires bearish. SPX: −7 at 20 min (14:47), −27 at 30 min (14:57), low 7,733 at 15:02 (−36).
   A second 1,506 bought at 15:12 @ $18.86 (after the drop). ONE case — S7 stays "new" until scored on later days.

## 5. DT (dealer tape squares)
✅ The "band % of dot" setting was inert (the 200-contract floor always set the band) → adaptive band α × own 30-min volume.
✅ v2 defaults (α 0.25, floor 200, ±0.30 %, watch 15, follow ≥2 strikes/3 min, GEX>0 gate) reproduce the research exactly.
❌ Plain DT follow: only 17 % of settings positive in both halves. Hollow/filled ≠ next-morning OI change.

## 6. HISTORY DEPTH (data we can get)
✅ Expired SPXW 1-min candles: 8 sessions back to 24 Sep pulled on 21 Oct (~4 weeks).
🟡 The run stopped because SPX's own 1-min candles ran out (24 Sep had 289/407 minutes) — NOT proven that option candles
   stop there. → trishula_history2_dump.py (uses SPX 5-min/daily for the strike range; a day is empty only when the OPTIONS
   are) answers it.
✅ Daily-candle OI of a contract = OI at the next session start (r = 1.000 vs Summary). Summary OI of an expired contract
   = OI on the morning of expiry. TimeAndSale replay: last 1,000 prints per contract. 5-min candles: uncapped.

## 7. TASTIER / misc parked
❓ L19k: rebuild TASTIER history/surfaces without snapshots (OI + spot + imp_vol from 1-min candles) — prototype
   scratchpad l19k/proto.py worked on 20 Oct; recorder 1-min candles would need imp_vol stored.
❓ Chain-wide "lean" gauge: averaging the whole chain washed the 21 Oct signal out; z-scores missed the constant call
   selling. Not pursued.
