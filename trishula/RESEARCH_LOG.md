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


## 8. 25 Oct — L34 (Tetris warm block = reversal) and L35 (walk-forward thresholds)
❌ L34 (research/l34, pre-registered): the warm Tetris A/E blocks at highs/lows (user circles 23 Oct) come from scaling each
   strike to the DAY's peak — a strike peaks when price comes closest to it, i.e. at the turn, known only afterwards.
   Causal version (peak so far): almost no warm blocks; 12 days with OI → 1 event (lost). Not tradeable live.
🟡 L35 (research/l35, pre-registered walk-forward, 22 days, 4 folds × 3 test days): only S6 exhaustion + breadth "middle"
   passed (+2.74 / t 2.05 / 3 of 4 blocks; setting 8-pt move, ≥ 7 unusual strikes); S1 +0.7 in 4/4 blocks but t 1.2–1.4;
   S7 negative; S3/S4/S5 ≈ 0. One pass in 18 is what luck gives → keep collecting days, rerun unchanged at ~40 days.

🟡 L35 rerun per mode (25 Oct, all 22 days with 1DTE): 0DTE → S6 "middle" passes (+2.74 / t 2.05 / 3 of 4); 0+1DTE → S6
   "more" passes (+2.70 / t 2.66 / 4 of 4, setting 8-pt move ≥ 3 unusual strikes). S6 positive in all 6 position × mode
   runs → the most consistent candidate. Still 36 tests in total → keep collecting; rerun unchanged at ~40 days.

## 9. 25 Oct — correction + L43
✅ CORRECTION: scaling to the window UP TO NOW (AG's way) uses no future data; it only re-ranks past colours. The L34
   "hindsight" verdict applied to the end-of-day picture, not to what a trader sees live.
❌ L43 (research/l43, pre-registered, 12 days): AG-scale Tetris rebuilt every 10 min. A: fading "price into heat" −0.78
   (t −0.8); "turn confirmed" −3.8 (n 10). E: "price into heat" +5.3 pts at 20 min (t 2.1, 70 % right) on only 10 trades.
   Fails the A-and-E rule. E V1 = something to re-check on more days, not to trade.
🟡 L44 status: the l25 brute force (25,256 combos on 21 Oct, 4,800 on 20 Oct) already included per-strike scaling over the
   window up to AG's posting time; best remained the price grid. Without NEW AG screenshots there is nothing new to fit
   — and fitting more on 3 pictures is curve fitting. Resume when he posts again.

## 10. 5 Nov — L47 LEAN CANDLES (paint SPX candles by options-flow lean)
Data: 22 sessions 24 Sep–23 Oct (1-min, ALL prints via candle bid/ask split — history has no single-leg flag) + 4 Nov (5-min).
Flow = bull/bear in delta $ (flat 14 % IV only to weight contracts). Grid: 256 settings = bars 1/5 · 0DTE vs 0+1DTE ·
noise L 0.03–0.15 · size gate off / today-so-far 60th pct · baseline none / rolling 30 · confirm (close breaks prior 2
bars' high/low) on/off · cooldown 0/3. Scored at each colour SWITCH: SPX 10/20/30 min later in the colour's direction.
Controls: 2-bar break with no flow ≈ 0 (1-min t 0.0, 5-min t −1.0); random ≈ 0.
🟡 Best: 1-min · 0DTE · L 0.15 · gate 60 · no baseline · no confirm · cooldown 3 → +0.81 pts/20 min, t 2.9 (overlapping);
   non-overlapping +0.93, t 1.8, 13/22 days up; halves +1.47 / +0.06 → edge sits in the first half. Next best (roll
   baseline) +1.08 non-overlap, t 2.3, 15/22. Best of 256 tries → not significant after the multiple-test penalty.
❌ Confirm rule (2-bar break): lowers every variant (1-min mean t 0.9 → 0.55; 5-min 0.27 → −0.08) and makes the colour
   100 % the candle's own direction — it becomes a price filter.
✅ Cooldown 3 helps a little everywhere (1-min t 0.90 → 1.07) and cuts switches ~30 %.
❌ Low noise (L 0.03) = worst (t −1.4). 5-min bars: nothing near t 2.
🟡 Colour = the candle's own direction 84 % of the time → mostly coincident. Divergence bars: 5-min L 0.06 → price went
   the CANDLE's way next 10 min (t −2.7/−3.0, flow wrong, as L23); 1-min L 0.15 gate 60 → +1.31 at 20 min, t 1.5, 18/22 days.
Even the best setting paints ~50 switches a day on 1-min. Verdict: a context paint, not an entry trigger. Rerun at ~40 days
with SINGLE-LEG prints (needs the daily zips). Scripts: scratchpad l47/ (lean_test.py, percheck.py, div.py, img.py).

## 11. 5 Nov — L48 lean candles, EVERY combination traded (scratchpad l48/)
7,680 rules (lean per bar ×4 variants / rolling 5–60 m / since open · band / sticky · X 1–25 % · 2-bar confirm · cooldown
0/3/5/10 · skip first 10 min · grey = flat / hold) × 0DTE / 0+1DTE × 1 / 5-min, executed at every colour change, 0.5 pt per
round trip. 4 Nov in three flow versions (all prints · viewer hybrid · single-leg ESTIMATE: candle ask/bid × each contract's
single-leg share from its replayed prints — 42 % at the ask, 29 % at the bid) + 22 history days (all prints).
❌ NULL TEST: the same grid with each day's flow TIME-SHIFTED (no information about price timing) gives as many winning rules
   (1-min 26 % vs real 27 %; 5-min 43 % vs 34 %), MORE robust rules (96 vs 54; 279 vs 92) and the same best total (+345 vs
   +315; +354 vs +354). → on all-prints data the lean adds nothing to timing; the "best" rules are what chance produces.
❌ Rules best on 4 Nov lose −700…−860 on history; the best history rules (+290…+330, t 2.4–2.8) lose −50…−113 on 4 Nov
   single-leg estimate. 64 / 30,720 positive on both — mostly one 4 Nov trade.
Only consistent lessons: fewer trades lose less (cooldown 10, X ≥ 15 %, 5-min bars, grey = hold).
Real single-leg test needs full-day single-leg prints = the app recorder (v0.23.1 past-session download), not the replay
(4 Nov replay reached 13 % of volume).

## 12. 5 Nov 04:49 ET — PRE-REGISTRATION: lean candles on single-leg days (v0.24.0, core/lean.py LOCKED)
Written before any full single-leg day exists. Data: state/lean/YYYY-MM-DD.json (recorder prints, 100 % of the day).
Rules (traded at every colour change, grey holds, flat at 15:59, 0.5 SPX pt per round trip, single-leg flow):
   A  1-min · 0DTE · rolling 15 m · sticky 8 % · 2-bar break · cooldown 10      (user's 4 Nov screen)
   B  1-min · 0+1DTE · rolling 20 m · sticky 1 % · cooldown 5                    (best robust on 22 all-prints days)
   C  5-min · 0+1DTE · rolling 10 m · band 8 % · 2-bar break · cooldown 5
   D  1-min · 0DTE · per-bar lean 15 % · cooldown 10
PASS (each rule on its own): ≥ 15 days · total > 0 · both halves > 0 · total above the 95th percentile of 200 runs on
time-shifted flow · single-leg total better than the same rule on all prints. 4 rules → one lucky pass is possible;
a pass is "worth trading small", not proven. Anything else found later in the saved days = new hypothesis, tested on
days AFTER it was written down.

## 13. 9 Nov — first single-leg days (lean history zip): review, no changes (scratchpad l50/)
Usable: 5 Nov (09:30–15:42, SPX −314) and 9 Nov (to 15:26, +154) — both strong trend days. "6 Nov" file = 5 Nov replay
mislabelled (save-key bug after a post-close restart; 6 Nov itself not recorded — app not running). Fix parked (user).
Single-leg = 56–65 % of all-prints flow. Single-leg lean follows the PAST 15 m move (rank corr +0.6 vs +0.45 all prints);
forward corr ≈ 0 on 5 Nov, negative on 9 Nov (overlapping, ~12 independent obs).
Rule A single-leg +204 / +53 (2 + 4 trades); its PRICE-ONLY twin (same machine, 15-min SPX move ≥ k pts) +135…+195 /
−38…+81 → most of A's gain = trend capture. A's neighbourhood (windows 5–60 m, X 1–8 %) all +200…+400 on these 2 days but
mixed / negative on the 22 all-prints days. Multiway (7,680 rules): sticky > band, grey hold > flat, small X (≤ 5 %) >
large, 1-min > 5-min, skipping the first 10 min hurts, confirm / cooldown ~neutral; single-leg beats all prints in only 47 %
of rules. 1-min single-leg rules profitable 63 % vs 37 % time-shifted null — but on 2 trend days.
Opening lean (09:30–09:45, single-leg) had the day's direction both days (9 Nov: SL +3.2 % while all prints −0.4 %).
On 19 all-prints history days: sign right 68 %, +151 pts — same as "short every day" (+135): no information there.
NEW HYPOTHESIS (written 9 Nov, test only on days after this): H1 sign of single-leg 0DTE lean 09:30–09:45 → SPX
09:45→close direction; beat "short every day" and the all-prints version.

## 14. 11 Nov — VS3D guide + cheat sheet re-read in full; Terrain vs VS3D gradient (one screenshot, 11 Nov ~10:50 ET)
VS3D: exchange-signed participant volume (CBOE C1) built into positions from each contract's first trade; MM-vs-MM nets,
customer-vs-customer dropped; gradient ALWAYS whole book incl. Flex, spot ±2.5 %; foundation = t−1 9pm expiring OI; intraday
0DTE flow = "ghost". Ours: tape-inferred dsign (all prints, incl. spread legs) × (OI + today's volume), 0DTE only, power 0.4.
Screenshot: his γ at spot slightly NEGATIVE (−9 exp @7657 = +18 minis/$1 buy on rally), long-γ pocket 7560–7590, charm pin
(red over green) ≈ 7580–7590, split ≈ 7640. Ours: γ +59 minis/$1 all green, charm sell below ~7600 / buy 7620–7660 (flip 7599).
Disagree at spot. Candidate changes a–d queued; to be scored on more of his screenshots before any build.

## 15. 12 Nov — Terrain vs VS3D, day 2 (data zip 10:43 + his 10:30 Positions by Strike and gradients) (scratchpad l51/)
Our 0DTE dealer sign vs his 0DTE MM positions (15 strikes 7560–7630): all prints OI×dsign corr +0.55, 12/15 same sign;
single-leg +0.27…+0.32 (worse today; yesterday single-leg looked better). Our gamma field at 10:30 = green everywhere for
every 0DTE/1–3-expiry variant; his = red 7420–7640, green above 7650 = dealer short risk reversal from the WHOLE book.
Giving 1DTE/2DTE the naive risk-reversal sign turns ours red below ~7560–7580 / green above → his shape, flip too low.
→ v0.26.0 long-dated book layer (OI × risk-reversal prior × weight). To score on his later screenshots.

## 16. 16 Nov — lean locked test, 6 single-leg days (5, 9, 10, 11, 12, 16 Nov; 6 Nov file invalid) — scoring only, no changes
Pre-registered rules unchanged (≥ 15 days needed before any verdict). Single-leg total / per day / days up:
   A +247 / +41 / 4 of 6 (2nd half −23 per day) · B −40 · D +91.  All prints: A +181 · B +328 · D +242.
   Since 10 Nov (days after the L50 review): A single-leg −36 vs all prints +150 — single-leg is NOT beating all prints;
   A's total is still 5 Nov (+204). 16 Nov (SPX −97): single-leg A/B/D −41 / −36 / −33, all prints +74 / +24 / +52.
H1 (opening single-leg 0DTE lean 09:30–09:45 → 09:45→close), forward days only: 10 Nov ✓ +7 · 11 Nov ✗ −35 · 12 Nov ✗ −5
   · 16 Nov ✗ −94 → 1 of 4, −127 pts (short-every-day +97, all-prints sign −121). Leaning towards fail; keep counting.
Data note: 16 Nov chain snapshots / spot rows start 12:20 ET (recorder memory lost ~12:20; status: rss peak 2.3 GB,
   54 memory thins). Prints (TAS replay), SPX 1m and lean minutes cover the full day. Terrain at 10:00 / 12:00 for 16 Nov
   can only be approximated (prints + OI); 14:00 and 15:30 are complete.


## §17 · 0DTE edge model — prior-close VIX vs Yahoo VIX open (23 Nov 2026)
Yahoo daily via the Yahoo MCP (SPX + VIX since 1989). Yahoo's daily VIX "open" = the 03:15 ET overnight value (20 Nov:
28.63 at 03:00, 29.69 at 09:30); no 09:30 VIX history is available anywhere we can reach (Yahoo 30-min ≈ 60 days,
tastytrade intraday is shallow). Scale fit as edge_model (_fit_scale, 12-y half-life, refit every 63 days, earlier
days only), moves open→low / open→high, strikes at the in-sample 95/99/99.5 % standardized move. 2,486 test days 2017→.
Put misses at the 5 / 1 / 0.5 % strike — prior close 3.94 / 0.88 / 0.48 · VIX open 4.71 / 1.05 / 0.64 · higher 4.55 / 1.05 / 0.60.
VIX open ≥10 % above prior close (79 d): prior close 8.86 % misses at the 5 % put strike vs VIX open 3.80 / higher 6.33.
VIX open ≥10 % below prior close (15 d, like 23 Nov): put misses at 1 % — prior close 0 · VIX open 6.67 (1 day) · higher 0.
Calls: no material difference. Built as a toggle (SPX BB v0.48.0); default stays prior close.
Addendum (23 Nov 07:57): "pick whichever VIX is higher today, use that version's forecast" — put misses at 5 / 1 / 0.5 %:
4.26 / 0.93 / 0.44 (all days 2017→); VIX up ≥10 % overnight 3.80 at 5 %; VIX down ≥10 % overnight 0 at 1 %. Best of the
four; replaced the fitted-max version in SPX BB v0.48.2.

## §18 · 24 Nov — "zero" write-up checks on ALL saved days (12, 16, 18, 20*, 23** Nov; *20 Nov afternoon only after a
restart, **23 Nov to 14:00). RTH, 0DTE SPX prints from the GitHub day zips. Mid prints = 34–43 % of prints.
A) 5-min net options delta vs SPX: same-bar corr all prints +0.35 · single-leg +0.43 · single-leg without mid prints
   +0.44 · calls only +0.35 · puts only +0.44. Next bar ≈ 0 in every version (−0.05…+0.02).
   → single-leg helps; dropping mid prints adds nothing; SPX puts are NOT a worse read than calls here.
B) Biggest single-leg orders (one contract + side + second merged, top 1 % by delta $ per day), SPX 30 min later in
   their direction: at/through quote 50 % right, inside the spread 51 %. Splits (AM bought calls 68 %, 3/4 days; PM
   bearish flow right 5/5 days) follow the days' drift — 4 of 5 days sold off — so they can't be read as skill.
   AM bought calls going right against a falling tape is the one thing to keep counting (matches the write-up).
C) Straddle bought on a disconnect at real bid/ask: not testable yet — SPX BB keeps the straddle MID only, 2 days.

## §19 · 24 Nov — fade / follow at the day's extremes (core/extremes.py, settings fixed before scoring except the cut)
Cut first tried at a fixed |lean| 0.10 → no events (15-min single-leg lean std ≈ 0.04), changed to 0.5 × the lean's own
std so far today BEFORE looking at results. 10 saved lean days 5–23 Nov: fade 18 events · 39 % right · −4.1 pts at
30 min; follow 36 · 56 % · +2.4. Walk-forward verdict (last 15 of each kind from earlier days): FOLLOW on 9, 18, 20,
23 Nov → 14 trades −49 pts; SIT OUT on the rest. No edge yet; shipped as an off-by-default OrderFlow toggle to collect.
Write-up's own reported results: 1.1 trades/day 55 % won +5.2 % avg (median +12.5 %); 1.6/day 31 % won +9 % avg,
median −22 % (lottery-shaped). "drop mid" shipped as a toggle; on 5 days it did not tighten the read (§18).

## §20 · 24 Nov — daily research run #1 (scheduled; scoring only, nothing in the app changed)
Data: lean files 5–24 Nov on trishula-state (11 valid days: 6 Nov mislabelled; 5 Nov to 15:42, 17 Nov to 13:48, 23 Nov to
15:17). Day zips: 12, 16, 18, 20 (prints from ~12:00 only), 23 (14:00 copy — no close copy that day), 24 Nov close.
Scripts: research/daily/2026-11-24/. Cost 0.5 pt per round trip everywhere. Random baseline = same-day drift × direction.
**24 Nov data problems:** the recorder restarted ~14:13 ET (close status: uptime 119 min, seed replay 14:13, rss 1,800 MB,
peak 2,144 MB, 117 memory thins, 40 errors, book layer skipped "memory 1,778 MB"). Prints 09:30–14:00 are replay-thin
(14–42 k/h vs 218–331 k/h after); the lean file holds the full day. state/calls/ does NOT exist on trishula-state → the
option-priced call log could not be scored. dt2_scorecard / signals_card are only written when the tab is open (only in
the 23 Nov 14:00 zip) → DT v2 and Signals were recomputed offline from prints + 1-min/5-min candles (no dsign dot; GEX
from the day's first chain OI) — close to, not identical with, the app.

a) LEAN (single-leg, 0DTE unless noted; 11 days; null = 200 time-shifted-flow runs)
   rule  total   /day  days up  trades  all-prints  null p50/p95   pctile  24 Nov (all prints)
   A    +198.4  +18.0   5/11      20      −10.0     −177 / +214     94 %   −14.3 (−31.4)
   B    −141.0  −12.8   6/11     117      −13.9     −196 / +142     59 %   +88.3 (+61.1)
   D     −60.1   −5.5   6/11      75       −5.7     −192 / +141     74 %   +10.7 (−74.2)
   E    −333.0  −30.3   5/11      90     −237.5       +9 / +431      3 %   −94.9 (−52.7)
   A halves +57.6 / −15.0 per day → still fails the 2nd-half test; A's total is still 5 Nov (+204). No rule has 15 days.
   E = D + 2-bar break confirm (src "per bar" ignores the window, so window 20 is inert). E is set by the user on 24 Nov:
   only 24 Nov is out of sample (−94.9). E sits at the 3rd percentile of shifted-flow nulls (worse than random flow).
   E neighbourhood (11-day totals; X rows × cooldown 5/7/10/12/15):
     X 0.100: +180 +81 +145 +28 +304 · 0.125: −215 −176 −14 +70 +141 · 0.150: −252 −394 −333 −275 −190
     X 0.175: −423 −515 −180 −155 −197 · 0.200: −660 −610 −590 −498 −542
   → no plateau at E; the surface slopes steadily to lower X (more trades). Not refitted. Rolling-window variants (win
   10–30, X 0.10–0.20, band + confirm) almost never fire (0–15 trades in 11 days), all ≤ 0.
b) DT tab (6 zip days; edge20 = fw20 − random same-direction; t on edge20, signals overlap so t is optimistic)
   DT v2 follow 20 sig, fw20 +2.6, edge20 +6.0, 63 % right, 4/6 days + · follow & GEX>0 9 sig (2 days) edge20 +11.0
   DT v2 initiation 89 sig, fw20 −2.7, edge20 −2.8, 43 % right, 0/6 days +  (S5 = same signal, same numbers)
   S1 middle/more 148, edge20 +2.7, edge30 +4.6, 5/6 days + (t 2.0) · S1 fewer 93, −0.2
   S3 fewer/middle/more all ≤ 0 · S4 middle 21 edge20 +6.2 (5/6) · S6 fewer/middle/more edge20 +2.6/+2.8/+2.8, 4–5/6
   S7 more 40, edge20 +3.6 (4/6) · S7 middle 1 signal.
   24 Nov: S1 middle +4.5 (22 sig), S6 middle +6.8 (9), initiation −2.8 (13), S3 more −5.7 (19).
c) ORDERFLOW
   Extremes (11 lean days): fade 18 · 39 % · −4.1 at 30 min; follow 37 · 54 % · +1.1; with sess filter: fade 15 · 40 %
   · −4.6, follow 19 · 58 % · +1.7. Walk-forward verdict (earlier days only): sess off 15 trades −94.7 pts, sess on 12
   trades −31.1. 24 Nov: one event, FOLLOW the 10:00 high → −45.6 (verdict FOLLOW with sess off, SIT OUT with sess on).
   Unusual (SPX 0DTE, single-leg, drop mid + drop crosses, tab defaults; SPX 30 min later in the flag's direction):
     new positions 54 · 52 % · +4.4 · edge +4.6 · 4/6 days · bursts 50 · 50 % · edge +0.8 (2/6) · paying up 35 · 46 %
     · edge −0.1 · big 35 (same orders as paying up on these days) −0.1. 24 Nov: bursts +7.3, new −6.5.
   ES / SPY options single-leg net delta $ (5-min) vs SPX (3 days): same bar corr ES +0.36 · SPY +0.32; next bar ES 0.00
   · SPY −0.27 (20 Nov −0.48, 23 Nov −0.34, 24 Nov +0.03).
d) SPX BB disconnect z (23 + 24 Nov, 21 episodes |z|>2, 30-min per-sign cooldown): width/straddle ratio reverts in ~15
   min — z>2: width −5.6 % vs straddle −1.9 % (ratio −3.7 pts); z<−2: width −10.0 % vs straddle −15.7 % (+5.7). Gone by
   30 / 60 min (|diff| ≤ 2). All-minute drift −9 % width / −8 % straddle per 15 min (theta). 2 days only.
e) NEW IDEAS (pre-registered 16:55 ET in research/daily/2026-11-24/prereg.txt before testing)
   N1 Lean opens only 10:00–14:59: A +198 → −54 (better 2/11 days), D −60 → −197 (5/11), E −333 → −331 (4/11). FAIL.
   N2 'new positions' flags agreeing with session lean: 29 flags edge +6.0 (3/6 days) vs disagreeing 25 flags +3.0
      (3/6). No clear difference. Not a rule.
   N3 Prior-close VIX < 20 (5 d) vs ≥ 20 (6 d): A +168 / +30 · B −68 / −73 · D +115 / −175 · E −74 / −259. Every lean
      rule did worse with VIX ≥ 20 (all the recent days); descriptive only, regime and calendar are confounded.
Verdict: nothing has 15 days; nothing to APPROVE. Keep counting: DT v2 follow (+6 edge, 4/6 d), S1 middle (5/6 d),
S6, unusual "new positions" (4/6 d), BB disconnect 15-min reversion. Consistently negative: DT initiation / S5 (0/6 d)
and extremes FADE.

## §21 · 25 Nov — Terrain: EVERY coded setting scored against Dan's 24 Nov charts (12:47 and 14:04 ET)
Method: Dan's two gamma panels (user screenshots) digitized to a signed intensity on price × time (median-filtered to
remove candles / lines; calibration checked visually). Our field rebuilt from the 24 Nov 14:00 copy (full tape) at the
same moments. 3,200 settings per picture = 4 sign sources (naive · signed all-prints · signed single-leg · opening seed)
× 5 expiry sets (0DTE · 0+1DTE · 0DTE+book .35 · 0DTE+book 1 · 0+1DTE+book .35) × 4 weightings × volume weight
.05/.25/1 × 2 field modes × 4 colour scales (Dan ±250 · Percentile 95 · Percentile 99 · StdDev) × power .4 / 1.
Scores: sign agreement where Dan's colour is clear (|v| > .15), whole field and right of "now"; Spearman rank of the
shading (shape, pockets / dark band). Scripts: research/terrain/.
• The app's CURRENT settings (signed single-leg · book .35 · OI+Vol · vw .05 · Dan ±250): one flat colour — the Dan
  ±250 cap saturates every cell (shape undefined). 180 of 3,200 settings are fully saturated (Dan ±250 92, StdDev 88).
• BEST on both pictures: naive sign · 0DTE + long-dated book .35 (or 1.0) · "Vol else OI (legacy)" · volume weight .25 ·
  Aggregate · Percentile 95 (or 99): sign agreement 95 % / 92 % (86 % right of now), shape rho .81 / .77 — reproduces
  the green pocket appearing top-right and growing toward spot by 14:04 (picture: research/terrain render).
• Sign source: naive beats every signed version (best rho .77 vs .64–.67). Per-strike field mode is worse (.57).
  Colour scale doesn't change the sign; it decides whether pockets / blobs are visible — Dan ±250 and StdDev often
  flatten the whole picture, Percentile 95/99 keep them.
• Two pictures on ONE day: a fit, not proof. Score the same settings on the next screenshots before changing defaults.
Raw-data tests (pre-registered research/terrain/prereg.txt), 32 checkpoints every 30 min on 5 days with snapshots:
  H1 γ at spot → next-60-min range: rho +.28 (p .12), within-day +.09 → no. (Best setting is red at spot 31/32 times.)
  H2 magnet to the nearest zero boundary within 60 min: price moved TOWARD it only 29 % (n 14; control 33 %, n 9) →
     no magnet; if anything away — too few cases to call. Keep counting.
