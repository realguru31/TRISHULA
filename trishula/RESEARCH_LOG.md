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
✅ Our noisy "now" edge after a restart = the 1,000-print replay cap (the past came from too few prints). v0.16.4 patched
   with 5-min candles; v0.18 rebuilds the past from 1-min candles (sweep every 5 min, 0DTE+1DTE).
🟡 v0.18 2-D ridgeline (baseline at strike, SPX on the same axis, occluding fills) LOOKS like his view; not yet compared
   minute-by-minute with one of his posts.
❓ Does our ridge show the SAME spikes at the SAME minutes as his? → NEXT: 21 Oct full-day Colab dump
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
❓ His vertical COLUMNS (whole time slices changing colour at once) — global scaling fails; maybe 3-D occlusion.
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
OPEN: the 22 Oct 7720P block — bought or sold? (21 Oct full-day dump answers it).

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
