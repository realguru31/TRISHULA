# TRISHULA — QUEUE (fresh, 2026-10-21 15:00 ET)

Deployed: **v0.17.0**. Nothing gets built until the user types **APPROVE**. Deploy after the 16:00 ET close.
Rules unchanged: whole zip every time (delete trishula/ → unzip → commit → Reboot app) · version on screen + CHANGELOG ·
secrets only in Streamlit · one repo, no GitHub tokens · Colab scripts outside the repo, both tokens prefilled.

## ✅ BUILT v0.19.1 (APPROVE 25 Oct 12:36) — L41
- L41 "0DTE / 0+1DTE" toggle everywhere it isn't already (user: "add option of 1dte across as toggle"):
  · Tetris A/E: 0+1DTE sums both expiries per strike, each leg with its OWN time to expiry; same no-repaint rules
  · Signals: one toggle for all signals (today S1/S7 already use 0+1DTE, S3–S6 0DTE only); walk-forward table shown for
    the chosen mode
  · DT v2: same toggle (squares / follow / initiation on 0+1DTE flow)
  · default stays 0DTE until the 0+1DTE walk-forward says otherwise
  · RESEARCH: rerun the L35 walk-forward unchanged in 0+1DTE mode on all 22 days — the 1DTE minute candles for 6–20 Oct
    are already on file (OI-history pull); 24 Sep–5 Oct and 21–23 Oct have them too

## ✅ BUILT — v0.19.0 (APPROVE 25 Oct 12:19 Doha) · trishula-v0.19.0.zip · NOT YET DEPLOYED
Scope: L33 (Tetris A default, readable palette removed) · L36 (no-repaint Tetris A/E + Terrain) · L37 (DT v2 one slider,
±% from control bar) · L38 refresh-now button · L39 status badge colours · L40 contract-pane labels · L34 + L35 research
· L35b Signals sensitivity slider from L35. No-edge signals: user did not answer → default = hidden on the chart, with a
"show unproven" toggle (hollow) — tell user.
Progress (L35 next): L33 ✓ · L38 ✓ · L39 ✓ · L40 ✓ · L37 ✓ · L34 ✓ RESULT: warm blocks at turns are HINDSIGHT (day-peak scaling);
  causal A/E has ~no warm blocks → 1 event on 12 OI days → no edge. Tetris scale toggle: no repaint (default) / hindsight.
  L36 ✓ (Tetris A/E running peak + causal colour edges + fixed strike set + IV/OI from snapshots;
  Terrain frozen past columns + snapshot backfill + dimmed projection; tests pass: past identical after chain change)

## ✅ BUILT — v0.18.1 (22 Oct 03:08): 1-min candles were dropped (dxfeed symbol {=m} vs code's "=1m") → backfill/sweep 0 since v0.16.1; fixed
## ✅ BUILT — v0.18.0 (APPROVE 21 Oct 15:00 + 22 Oct 02:16) · zip trishula-v0.18.0.zip (102 files, 0 tokens) · NOT YET DEPLOYED
A1 memory · A2 live stalls · A3 ridges (sweep + ridgeline default / 3D / map, RTH, ±60, 0+1DTE) · A4 Tetris G default ·
A5 Signals view (replaces DT classic) · A6 Book card · RESEARCH_LOG.md. Harness: every tab × 2 datasets, 0 errors.
Deploy after the close (delete trishula/ → unzip → commit → Reboot). AFTER DEPLOY CHECK: player stays 🔴 LIVE across tab
switches · ridge caption shows "candle sweep (0DTE+1DTE…): N/N" within ~2 min of a reboot · memory in diagnostics.
Untested here (needs the live API): the sweep itself — verify with the caption on the first day.
NEXT (waiting on data): ridge vs AG spike-by-spike on 21 Oct (trishula_21oct_dump.py) · 22 Oct 7720P bought/sold ·
history depth (trishula_history2_dump.py). Research thread status → RESEARCH_LOG.md.

## QUEUED 24 Oct (user review of Fri 23 Oct screens) — each needs APPROVE
- L33 Tetris default back to A (AG palette); G and all "readable" views judged useless by the user (G = flat bands;
  note the screen also ran G with "OI only" overlay). Keep G/E as options or drop G — user to decide.
- L34 (research first) "warm Tetris block at price = reversal" (user circles: E — warm at the overnight low ~7650 and at
  the day low ~7615 ~10:20; A — warm at the 04:30 high ~7670 and the 11:30–12:30 high). CAUTION: A/E scale each strike to
  its peak over the WHOLE window, so earlier colours REPAINT as the day goes on — an end-of-day screenshot can look
  prescient. Test causally: recompute A/E at each minute with data up to that minute only, flag "price enters a warm
  (red/orange/tan) block", score SPX 10/20/30 min later vs random, on all history days (20 + new).
- L35 (research first) Signals thresholds — walk-forward, NOT a single best fit: grid each signal's thresholds on days
  1…N, test on the next days, roll forward; report only out-of-sample results; ship a threshold only if it holds across
  folds (and say plainly if nothing does). Needs the history days + Thu 22 / Fri 23 (trishula_week_dump.py).
- User verdict 24 Oct: DT v2 · tested and Signals views "completely useless" as they stand.
- L33b remove the "readable" Tetris palette entirely (user 24 Oct) — AG palette only.
- L35b ONE simple slider (user 24 Oct 19:06): Signals tab gets a single "sensitivity: fewer ↔ more signals" slider
  (positions = the walk-forward-tested threshold sets, low → high), with a line under it: what that position did out of
  sample on the history days. No per-signal settings on screen (an "advanced" expander at most).
- L37 DT v2: replace the 6 sliders with the same single sensitivity slider; "± % of spot" comes from the control bar's
  strike window at the top (not its own slider); other settings fixed at the tested values (advanced expander).
- L38 player bar: a "⟳ refresh now" button next to "refresh N min".
- L39 status badge colour: 🟢 LIVE · RTH (09:30–16:00) green · ⚪ LIVE · GTH (overnight) bright grey · 🔴 CLOSED red
  (no session: weekend / after 16:15 until 20:15 / holidays); replay stays blue.
- L40 contract pane labels (user 24 Oct 19:10, C+P pinned 7650): both side axes are PRICES — left blue = call $, right
  orange = put $ — but nothing says so. Add axis titles in the line colours ("7650C $" left, "7650P $" right), a small
  legend, "contracts / min" title on the volume bars below, put each "low $x" label on its own side (they overlap),
  and keep the ridge strike axis visually separate from the pane's price axes.
- L36 NO-REPAINT rule for every map (user 24 Oct: "same approach of NOT repainting in VS3D terrains"):
  · Tetris A/E: each strike's peak = its peak SO FAR (running max up to that column), never the whole window → a column,
    once drawn, never changes colour.
  · VS3D Terrain: today the WHOLE 09:30–16:00 field is recomputed every frame from the CURRENT chain (OI/greeks now,
    projected back and forward) and scaled by percentiles of the whole grid → the past repaints by design.
    Proposed: left of "now" = frozen columns — each column computed once from the chain snapshot recorded at that minute
    and kept; right of "now" = the projection from the current chain (as today), visibly separated (dashed "now" line,
    projection dimmed); colour scale fixed per session (set at the first frame / manual cap), not re-percentiled each frame.
  · NOT Book (its dots already carry the history) and NOT GEX³ (a single-time snapshot by design) — user 24 Oct.
  · Terrain split CONFIRMED by user 24 Oct 18:39 (frozen past left, dimmed projection right). Colour: option 1 CONFIRMED 18:41 — each past column keeps the colours it was drawn with (locked at its minute);
    the projection right of "now" is recomputed and re-coloured every frame (e.g. a level pink at 10:00 may turn red at
    11:00 beyond the now line). Past never changes, future may.

---------------------------------------------------------------------------------------------------------------
## A. v0.18.0 "FIX RELEASE" — spec (BUILT, see above)
---------------------------------------------------------------------------------------------------------------
Each item has a pass test that runs in the harness before the zip ships.

A1. MEMORY (was L26) — the app was OOM-killed 13:04 ET 21 Oct (2,365 MB, 985k prints).
    · _all_prints keeps compact storage (no astype(str) of the 8 categoricals), returns only used columns
    · one cached per-expiry slice per print count, shared by tabs (no per-tab copies)
    · mem guard also folds 1DTE prints older than ~2 h into per-minute totals (0DTE tape untouched)
    · pin library versions (pandas 3.0.6; pyarrow as Streamlit forces)
    PASS: synthetic 1.5M-print day stays < 1.2 GB while switching all tabs.

A2. LIVE STALLS (was L32) — root cause known: the frame slider's stale value on a tab switch fires _scrub → REPLAY.
    · live mode: scrubber key changes with the frame count; _scrub ignores non-user changes
    · skip the live tick while a page run is still in progress (no stacked reruns)
    · clear "⏸ REPLAY — press 🔴 LIVE" banner when not live; per-tab run timings in Recorder diagnostics
    PASS: harness switches tabs 20× across new frames → never leaves LIVE.

A3. RIDGES AFTER REBOOT (user 21 Oct 14:56: "look like shit, after the reboot even more fucked up")
    Known so far: the 1m backfill came back empty on 20 Oct (fill5 from 5-min candles patched the gap in v0.16.4);
    today's reboot followed the OOM crash. Not yet diagnosed for today.
    · FIRST: diagnose from today's 📦 day zip (download after the close) + the caption under the ridges
      ("1-min backfill: f/n contracts") + a screenshot next to AG's 21 Oct ridges
    · then: after a reboot, rebuild the whole session from 1-min option candles only (same source as the Colab history,
      proven complete for every contract) — prints only for the live edge; no mixing of 1,000-print replay into the past
    · keep: AG height = contracts/min, one linear window scale, top-N spikes, non-linear time, 18 % right margin
    PASS: ridge rendered after a simulated reboot at 13:00 = ridge from an uninterrupted run (same picture, cell by cell).

A4. TETRIS "G · price-grid γ" as DEFAULT (was L27; A/E kept as options)
    · price grid, γ × (OI + traded since 20:15), live per-minute IV from 1-min candles, expiries 0DTE→Friday incl. 1DTE,
      each time column scaled to its peak
    · research/l25: 21 Oct 0.68 / 0.51 vs our A −0.04 / 0.20; top-3 on 20 Oct
    PASS: research/l25 score reproduced from the app's own matrix on the 21 Oct data.

A5. DT CLASSIC → "SIGNALS" VIEW (was L30; user 21 Oct 14:56: "replace DT classic with this visual")
    · clean price line + arrows only: shape = signal, size = tier, colour = direction, short caveat in the hover
    · signals: S1 aggressive block vs move (×5/×10/×20, 0DTE+1DTE) · S4 DT v2 follow · S5 initiation · S6 exhaustion
      · S3 near-spot flip (fires AT the turn, may be profit-taking). S2 caption setup DROPPED (negative out of sample).
    · side table per signal × tier: live count today, historical hit % and avg pts at 20 min, n, days
    · HONESTY RULE: tiers without proven edge drawn hollow/grey and labelled "unproven"; today only S1 ×10 is close
      (t 2.03 on 9 fresh days, not enough). The table fills from research/l28/l29_table.pkl shipped as data (no tokens).
    · DT v2 stays as is
    PASS: 21 Oct chart matches the research picture (arrows at the same minutes).

A6. VS3D Book KEY LEVELS + TAKEAWAYS card at ~40 % of its current size (was L31), still legible.

After deploy CHECK: player bar stays 🔴 LIVE across tab switches · ridge caption "1-min backfill: N/N" · memory in diagnostics.

---------------------------------------------------------------------------------------------------------------
## B. TONIGHT / TOMORROW — what the user does
---------------------------------------------------------------------------------------------------------------
B1. After 16:00 ET: 📦 day zip for 21 Oct → attach (needed for A3 diagnosis and A5 check).
B2. Colab: trishula_history2_dump.py (walks back from 23 Sep; if SPX 1-min is gone it uses SPX 5-min/daily for the
    strike range; a day counts as empty only when the OPTIONS have nothing) → tells us whether option history goes
    further back than 4 weeks. ~5 min/day. Attach trishula_history2.zip.

---------------------------------------------------------------------------------------------------------------
## C. EXPLORATORY / HALF-BAKED — kept on record (consolidated in RESEARCH_LOG.md, repo + project)
---------------------------------------------------------------------------------------------------------------
C1. Signal research (L29). Locked rules S1–S6 × tiers, script research/l28/l29.py — rerun UNCHANGED when fresh days arrive.
    · result #1 (6 fresh days): nothing significant; S2 negative
    · result #2 (9 fresh days 24 Sep–5 Oct + 21 Oct): S1 ×10 edge +1.42 pts/20 min, t 2.03, 54 % right, n 160, 6/9 days;
      S4 +1.81 (t 1.25, n 33); S3/S5/S6 faded; S2 rejected. 18 tests → one t≈2 by chance; want t≈3 before trusting.
    · goal ~25–30 fresh days. Routine: weekly Colab history pull (last 5 sessions) or the day zip each evening.
C2. History depth: run of 21 Oct stopped at 24 Sep because SPX 1-min candles ran out (24 Sep had 289/407 minutes),
    NOT proven that option candles stop there → B2 tests it. ES front-month (/ESZ26) gives only 1 row/day that far back.
C3. AG Tetris open questions: AG's vertical columns unexplained (global scaling fails; maybe 3-D occlusion);
    AG asymmetry (warm above spot after the open); AG uses 1DTE (22 Oct 7750C post). Price-grid vanna (L21) scored best
    on 20 Oct, γ on 21 Oct — one-day fits, could be curve fitting.
C4. 21 Oct caption ("they wanted some puts before the dip"): tape shows calls 7800–7815 sold ~2:1 while flat + puts
    7715–7735 net bought → dip 10:00–10:11 → puts sold at the low; 1DTE 22 Oct 7750C ~340 bought at the ask 10:05/10:08
    before the 10:11 low. As a rule (S2) it failed out of sample; S1 came from the 1DTE block.
C5. Persistent-strike lean / chain-wide lean gauge (research/l28): chain-wide average washes the signal out; z-score
    misses constant call selling. Not pursued.
C6. DT findings (research/l24): band "% of dot" was inert (floor always wins) → adaptive band; textbook GEX switch fails,
    follow only in +GEX works in-sample; filled/hollow squares carry no OI information (OI tests).
C7. TASTIER L19k (parked): rebuild history/surfaces without snapshots from OI + spot + imp_vol from 1-min candles
    (prototype scratchpad/l19k/proto.py); recorder c1m must also store imp_vol · L19l compare tiles vs Tastier live.
C9. AG post 21 Oct ~15:05 ET: ridges + contract pane for 22 Oct (1DTE) 7720P — $6.90, Δ −0.21, vol 3,383; one minute
    of ~1.5k+ contracts late in the session (after his "1pm" label = Central → ~14:00+ ET) while SPX sat flat near the
    highs after the 11:36 rally; the pinned ridge spikes to the top of his 0–1.2k scale.
    Confirms again: AG ridges include 1DTE · height = raw contracts/min (our AG mode) · he flags single big 1DTE blocks
    (same family as S1). OPEN: bought or sold? needs the 22 Oct 7720P tape after the close (rerun trishula_21oct_dump.py)
    → check bid/ask side, and what SPX did over the next 20/40 min → one more S1-type case (record, do not refit).
    User 15:07: AG's captions are always "someone positioned BEFORE the news" → his framing = informed size in short-dated
    (0/1DTE) options while price is calm, ahead of a move/news. Differs from S1 (S1 needs the block AGAINST the last
    15-min move). NEW HYPOTHESIS S7 "quiet big block": 1DTE (and 0DTE) single contract-minute ≥ k × own median AND
    ≥ ~1,000 contracts while the 30-min range is tight → direction = bought put / sold call = bearish (mirror bullish).
    Lock it now, test ONLY on days after 21 Oct (no fitting on 20/21 Oct cases). Also log news times next to each case.
C8. Ridges "unusual" mode (z vs own 30 min) is in v0.16.5 — keep, not default.

---------------------------------------------------------------------------------------------------------------
## D. ARCHIVE — full previous queue/handover below (facts, decisions, done releases)
---------------------------------------------------------------------------------------------------------------

# TRISHULA — build queue & handover (as of 2026-10-18)

Latest build: **v0.10.2** (all approved releases done; deployed version = whatever the user last uploaded) (GitHub repo `realguru31/trishula`, main module `trishula/app.py`, Streamlit Cloud, Python 3.12, secrets TT_CLIENT_SECRET / TT_REFRESH_TOKEN in Streamlit only).
Rules: build ONLY on user's "APPROVE" (caps). Semantic versioning in core/version.py + CHANGELOG.md, version visible on every screen. Colab test scripts always ship with both tastytrade tokens filled in. After every upload: Streamlit → ⋮ → Reboot app (recorder is a cached background thread).
Reference source: `vs3dgbt_0.9.79.py` in this project (port target for VS3D).

## Proven tastytrade facts (Colab 2026-10-17/18)
- DXLink Greeks/Quote/Summary/Trade on SPXW legs: OK. Spot from Trade (SPX quote bid/ask is junk).
- TimeAndSale replay via `fromTime`: WORKS on weekends. Every print has bid/ask at print, aggressorSide BUY/SELL (100% filled), spreadLeg (~42% true).
- Replay cap: **last 1,000 prints per contract** (busy ATM legs reach back only to ~10:30–13:00 Friday). ~4,600 prints/s; 60 contracts in 10 s. eventFlags: 0x01 TX_PENDING, 0x02 REMOVE_EVENT, 0x04 SNAPSHOT_BEGIN, 0x08 SNAPSHOT_END, 0x10 SNIP — completion detected by quiet time.
- Candle {=5m} carries bidVolume/askVolume (signed volume, uncapped, full session). {=1d} does not.
- DXLink quote token expires 24 h → recorder reconnects every 6 h (v0.1.4).
- Limits: 5 sessions, 25,000 subs/session, 100 Candle subs, 10,000 sub changes/min.

## User decisions (2026-10-18)
- Book opens FLOW-SIGNED (toggle clean / net flow / naive).
- Seed window: prior RTH + overnight for the expiry.
- MID prints: signed by aggressorSide (differs from GBT/vs3dgbt — caption it).
- Seed: re-fetched from tastytrade every start (no persistence).
- VS3D ports (Book, Terrain, combined, GEX³) in MATPLOTLIB (vs3dgbt code as-is, data inputs swapped). TASTIER + AG-REV stay Plotly.
- One APPROVE covers all releases v0.2.1 → v0.6.0, built in order, one zip per release.

## Progress tracker (updated after every release)
| Release | Status | Zip | Notes |
| --- | --- | --- | --- |
| v0.1.0–v0.1.4 | DONE | — | shell, recorder, tab refresh, weekend snapshots, 6 h token refresh |
| v0.2.0 | DONE · deployed | trishula-v0.2.0.zip | control bar, TASTIER 8 panels, naive VS3D |
| v0.2.1 | DONE | trishula-v0.2.1.zip | fixes + tab styling |
| v0.3.0 | DONE | trishula-v0.3.0.zip | TAS fromTime seed+backfill, 5m candle fill, dsign, Book flow lens (Plotly interim), AG-REV CVD |
| v0.4.0 | DONE | trishula-v0.4.0.zip | Book + combined + playback |
| v0.5.0 | DONE | trishula-v0.5.0.zip | Terrain |
| v0.6.0 | DONE | trishula-v0.6.0.zip | GEX³ |
| v0.7.0 | DONE | trishula-v0.7.0.zip | R1 refresh · R2 universal replay · R3 Book layout · R4 image scaling |
| v0.8.0 | DONE | (in v0.9.0 zip) | VS3D Interval · Market Read · DT |
| v0.9.0 | DONE | trishula-v0.9.0.zip | AG-REV signals Q1–Q5/W + V1–V5 (SPXFlow v2.10) · TASTIER Velocity/Absorb/Pressure · VRVP |
| v0.10.0 | DONE | trishula-v0.10.0.zip | GTH session on all tabs · spike filter (robust z + cross-section + floor, GTH/RTH baselines) · 3-D AG-REV ridges/surface |
| v0.10.1 | DONE | trishula-v0.10.1.zip | spike filter tuned on real tape (per-session defaults, single-leg, package merge) |
| v0.10.2 | DONE | trishula-v0.10.2.zip | stale-SPX-at-connect fix · /ES overnight price backfill · VIX from 03:15 |

## Queue (staged releases)
### v0.2.1 — fixes + look (small)
- 0  Expiry bar re-runs once recorder is ready (no stuck "loading…")
- 0b Status line: "recording 0DTE 10/19 · 1DTE 10/20 (seed)"
- 0c Weekly/Monthly "loading…" label + tab refresh until data arrives → "ready ✓"
- 1  Version-mismatch guard (new code vs running recorder → auto-restart or red "Reboot app" banner)
- 2  Silence "Task was destroyed / aclose()" shutdown noise
- 12 Tab styling: bordered tabs, faint dividers, active tab blue top border, hover, top-level larger than sub-tabs
### v0.3.0 — signed data foundation
- 4  Seed: Candle 5m bid/ask volume = net/total per contract (full session) + replayed prints (last 1,000) for spread-leg/clean-B, premium, CVD; SNAPSHOT_END check; batches of 100 candle subs
- 5  Gap backfill after restart/disconnect (replay; candles beyond cap)
- 6  Per-strike seed coverage on screen (prints-from time, candle coverage)
- 7  AG-REV + TASTIER CVD from seed
### v0.4.0 — VS3D Book + combined (port of vs3dgbt book_figure / signed_book_rows / _render_book)
- 8  Book: lenses flow-signed (green/red, sign×OI contracts, full mass, opacity=conf, unseeded naive faded at 0.2) · clean-signed (blue/magenta, single-leg only, no verdict=no bar) · net flow participant view (blue/yellow); controls Bars MM/naive, Show Total/Calls/Puts, zoom ±/full, comparison open dots, exhausted-extent sticks, 1× straddle, Δ ladder + ⚡ divergence, spot-path overlay with session time axis, card levels BALANCE/UP/DN with de-collision, 10-pt price ticks, KEY LEVELS card, THE STRIP, seed badge
- 11 VS3D combined (Book×spot 1.0 | Gamma+Charm terrain 1.5, bottoms aligned) + global controls: expiries to aggregate 1–5, price window ±%, live price layer 15/30/60/off, snapshot scrubber, playback ⏮▶⏸⏹ 1/2/4 s
### v0.5.0 — Terrain port (terrain_grid / scale / intensity / pockets / contours)
- 10 Forward-projected field 170 price × 84 time (09:30–16:00), BS greek at hypothetical spot/τ; Greek Delta Change/Gamma/Charm/|Γ|/Decay; field mode Aggregate/Per-strike; weighting OI+Vol/OI/Vol/legacy; range Manual cap (Calibrate/Reset, autopilot 1.5×/0.4×)/Percentile/StdDev; intensity Power 0.40/Sqrt/Arcsinh; opacity 0.38; saturation; smoothing 0.25; zoom; contours zero+ridges; negative-γ pockets top-N; straddle bounds; Pinak overlay; vol adj; simulated gamma/charm; stacked charm panel with charm flip; dsign drives field when signed
### v0.6.0 — GEX³ port (gex3_lens_rows / gex3_draw_profile / gex3_zone_shade / gex3_model / _render_gex3)
- 9  3 stacked panels (CONVENTION naive · FLOW-SIGNED · ΔOI overnight or live volume w/ dotted P2), candles across RTH, right-anchored density (buy green / sell red fills+lines, TOTAL orange, |net| white, ▲▼ peaks, HHI◆ top-5), γ fields, levels flip/CW/PW/PIN/CEIL/FLOOR/UHW/DHW with de-collided labels, scorecard, γ dial, colour readout + model-detail expander; sliders ±% room 0.5, density width 0.45, panel height 5.5; y auto-fit
### Later (needs recorded RTH / user input)
- Velocity/Absorb/Pressure overlays (definitions needed) · VRVP (SPY volume) · VS3D Interval, Market Read, DT · AG-REV signals Q1–Q5/W/B + V1–V5 panels

## Queued → APPROVED 2026-10-18 (R1–R4 built in v0.7.0)
- R2 Universal replay player (user 2026-10-18), placed ABOVE the three main tabs next to R1. Controls (final, user 2026-10-18): time scrubber · ⏮ first frame · ▶ play · ⏸ pause · ⏹ stop with a small 'LIVE' label next to it · speed 1 / 2 / 3 s per frame. No separate LIVE/Replay toggle — modes are implicit:
    · ⏸ while live = freeze at the latest frame → player mode (all tabs frozen there)
    · ▶ = advance one frame per 1/2/3 s from the current frame (from live: starts at first frame)
    · ⏮ = jump to first frame, paused (player mode) · dragging the scrubber = player mode at that frame
    · ⏹ LIVE = leave player mode, resume live data + refresh timer
    · A visible badge shows the mode: 🔴 LIVE or ⏸/▶ REPLAY hh:mm. Every tab (TASTIER, AG-REV, VS3D and its sub-tabs) renders "as of" the selected time: chain snapshot at t, prints ≤ t, candles/spot ≤ t, dsign as of t. Moves the existing player out of VS3D controls (where it lives today, collapsed).
- R3 Book tab layout (user 2026-10-18, screenshot: too much white space). Proposal:
    · Charts side by side, shared price axis: [1] FLOW-SIGNED (MM-inferred) · [2] CLEAN-B (single-leg tape) — both always on by default · [3] selectable third chart: Net flow / Naive / none.
    · REMOVE: Total/Calls/Puts radio (net view only), Bars MM/Naive radio and Book-signing radio (replaced by the fixed pair + third-chart selector).
    · KEEP (one compact row): zoom ➕➖↔ (grouped together, not spread across the page), comparison dots, 1× straddle, Δ ladder, spot path, card, strip.
    · KEY LEVELS card + STRIP sit beside the charts / above in a tight row instead of stacked with empty space.
    · Open: spot path on all charts or chart 1 only; card/strip always on or toggles.
- R4 Image sizing (user 2026-10-18): terrain/charm look right at normal browser zoom; gaps only appeared zoomed out (images stop at their pixel size). Book is the real problem: one huge tall chart (11×12 in) under a small card with empty space → fixed by R3 (charts side by side, height capped to fit the screen, card+strip in a tight row). Minor: let images scale with zoom.
- R1 Refresh interval control (user 2026-10-18): universal bar above the tabs (with R2), default 5 min, slider 1–10 min in 1-min steps.
  Scope DECIDED (user 2026-10-18): screen refresh only, for all tabs (replaces the VS3D 15/30/60 s live layer). Chain snapshots stay every 60 s, so replay/terrain/09:35 lock keep full detail.

## Status after v0.6.0 (2026-10-18)
- All approved releases are built: v0.2.1 → v0.6.0. Upload the latest zip only, then Reboot app.
- Verify live on Monday's RTH session:
  - seed replay + candle fill counts in the status bar
  - Book dots/bars
  - 09:35 lock
  - THE STRIP VIX chip
  - terrain candles
  - GEX³ panel 3 (ΔOI needs one overnight recorded first; falls back to volume)
- Known limits:
  - /tmp data (LocalRepo) is lost on redeploy, so ΔOI history and flushed sessions reset.
  - Replayed prints get a 1m-candle spot and no greeks; TASTIER CVD uses the current delta
    as a stand-in.
- Next (needs user input before APPROVE): Velocity/Absorb/Pressure definitions · VRVP (SPY) ·
  Interval · Market Read · DT · AG-REV signals Q1–Q5/W/B + V1–V5.

## Status 2026-10-19 (before Monday open)
- Everything queued is built (R1–R4 in v0.7.0; Interval/Read/DT; AG-REV signals from SPXFlow_v2.10.xlsm; TASTIER overlays). Upload trishula-v0.9.0 only, then Reboot app.
- "B" signal: not in SPXFlow v2.10 — nothing built. Velocity/Absorb/Pressure/VRVP formulas are TRISHULA definitions (see core/overlays.py docstring) — user to review.
- Next: watch the live session, then tune (ZThresh/MinPrem defaults are the workbook's).

## Status 2026-10-19 02:30 ET
- v0.10.0 built (GTH, spike filter, 3-D AG-REV). Tested on fake data only.
- Waiting on user's Colab real-data dump (trishula_sample_dump.py → trishula_sample.zip) to validate overnight prints arrive and to tune the spike filter on real tape.

## Real-data facts (Colab dump 2026-10-19 02:31 ET)
- Overnight SPXW prints stream via DXLink: 27.8k Sun 20:15→Mon 02:31, ~200/90 s live, median 1 lot, bid/ask on 100 %, aggressorSide 99.9 %.
- SPX/SPY 1m candles: RTH only (+16:00–16:20 for SPX). VIX 5m from 03:15. Overnight spot must be synthetic parity.
- eventFlags seen: 0, 1 (TX_PENDING), 4 (SNAPSHOT_BEGIN), 5. spreadLeg share 46 % (32 % overnight).
- Contract-minute volume Fri RTH: median 3, p99 159, p99.9 1,501. Overnight: median 2, p99 48.
- Open observation: Q5 can fire often in slow overnight drifts (workbook rule, 5-min cooldown) — watch live.

## Watch list after Mon 19 Oct RTH (decide with user)
- Q5 noise in slow overnight drifts → min price move / longer GTH cooldown?
- RTH spike count (defaults aim ~10–15/day).
- Session end 16:00 → 16:15 (non-expiring SPXW trades to 16:15; ~10k prints Fri).
- 19 Oct 14:37 crash = out of memory (per-print plotly charts) → fixed v0.11.1; watch 'mem' in the status bar on the next full day.
- Known limit: reboot/redeploy wipes the day's in-memory history (no external storage by user choice).
- "B" signal: not in SPXFlow v2.10 — needs a definition.

## Built in v0.11.0 (APPROVE 09:17): L1, L3, L4, L5 · still queued: L2

## Queued (user 2026-10-19 04:37)
- L1 Loading indicator: screens stay blank then appear all at once. Add a visible progress bar per tab/sub-tab while it computes
  (st.progress stepping through stages, e.g. "loading chain → signs → book → card → terrain → render", with % and stage label),
  plus a thin top-of-page bar during full-page refresh / replay steps. Also show placeholder frames immediately so layout doesn't jump.
- L2 GTH toggle per viewer: core/session.STATE is process-wide (shortcut) — two browsers with different settings flip it for each other. Move to st.session_state / pass session mode explicitly through bars_for/session_date/axes.
- L3 Interval: wasted space — y-axis spans ~7380–7930 while activity sits 7600–7740. Auto-fit y to top-N strikes + price path (vs3dgbt _intv_ylim) with small pad; x-axis end at "now" + margin instead of empty future to 16:00 (toggle).
- L4 DT legend on the chart + caption (user's 08-27 glyph grammar): blue = bullish, magenta = bearish; FILLED = extending (long building / fresh paper), HOLLOW = receding (short covering / long unwinding); near-zero dot (< floor) = fresh paper, always filled. Also: DT counts only from 09:30 — option to run from 20:15 when GTH is on.
- L5 Book layout (user 06:38): charts too tiny, card too wide. Card on TOP (full width, compact), remove "⬇ card" download button.
  Below: chart 1 (MM-inferred) + chart 2 (clean-B single-leg) side by side at half width each as default. Third chart only when a
  lens is picked in the selectbox → then all three across the full width. Spot path on ALL charts (twin time axis, like chart 1),
  checkbox renamed "Spot path".
- ✅ L6 built in v0.12.0 (APPROVE 08:09) — AG-REV ridges vs AG reference (user 20 Oct 07:48):
  a) Contract detail pane under the ridges for the pinned contract (AG style): header "Oct 20 7675 P $14.80 Δ-0.40 · vol 762",
     option price line through the session (last trade per minute, chain mid between prints), session-low dashed marker,
     spike minutes highlighted magenta, per-minute volume bars below. Default pin = latest spike contract.
  b) Top pane cleanup: clamp each ridge to the z range (ours draw out of the box top), fewer strikes around spot with wider
     spacing, more top-down camera, cyan low→high heat with a legend, pinned ridge red with its spike as a tall red line.

- Watch (v0.12): overnight spike count 26 on 19→20 Oct GTH (only top-1 bold) — consider higher GTH thresholds if the faint lines feel noisy.
- L7 Click-to-pin (user 20 Oct 09:38): clicking a ridge pins THAT strike in the contract pane (not auto). In C+P mode the
  pane shows the strike's call AND put (two price lines, volume split). Also: click a row in the ⚡ Spikes table to pin.
  Check first whether Streamlit 1.66 passes clicks on a 3-D plotly scene (on_select); fallback = a clickable 2-D strike strip
  beside the 3-D view. Auto (strongest spike) stays only as the initial pin until the user clicks.
- L8 Spike detection default → total volume (user prefers; currently single-leg default, session-only toggle).
- L9 Spike colours by direction (user 20 Oct 09:43): bearish = calls SOLD or puts BOUGHT → red; bullish = calls BOUGHT or
  puts SOLD → green; MID/unknown → grey. Same colour for the spike line (bold or faint), its 3-D label, the pane marker,
  its label and the spike stretch on the price line. Pinned ridge moves off red (amber) so red only ever means bearish.
  Same-minute shared labels: colour by the net premium direction of the legs.
  Label text (readability, user 09:44): bearish labels light pink (#ffb4c8-ish), bullish labels light green (#b6f5c8-ish);
  lines stay saturated red / green; grey for MID.
- L10a V4 "tetris" surface (user 09:47, AG ref of 16 Oct): replace smooth surface with voxel columns — one block per strike × time bucket (~10 min), height = normalised dealer γ (±1), quantised colour bands, white spot path on top, red price tag at the last price.
- L10b Tetris colour convention unknown → infer from the 16 Oct AG shot (tan/yellow · orange/red · dark blue · light blue · magenta/purple) by rebuilding 16 Oct from real data; confirm the mapping with user before shipping.
- L10c Tetris span = full futures session from 18:00 ET (AG axis 18:00 → 10:20) when GTH on; add the small top-down inset ("fixed" view) like AG.
- L10d Current V4 bugs seen 09:47: decay projection dominates (huge flat plateau right of now) → cap projection to ~60 min; white spot path floats outside the surface (axis mismatch); strike labels missing.
- L10e Data for 16 Oct rebuild: Colab dump of Fri 16 Oct full session (18:00 Thu → 16:15 Fri) prints + 1m candles, same script pattern as trishula_gth_dump.py.
- L10f "Ready for the sell" read (user 09:48, AG 16 Oct post): AG's circled cues = isolated RED blocks appearing inside the calm purple field ABOVE spot (top-left in the inset early; scattered red cubes near 10:00–10:20 just before the drop). Build a detector: block whose colour band differs sharply from its strike/time neighbourhood and sits above spot → mark + list as an early warning.
- L10g Verify L10f on the 16 Oct rebuild: do the red specks precede the drop to 7696, and by how many minutes? Only ship the warning if it shows up in the real data.
- L11a Ridges right margin (user 09:58): add empty space after "now" = min(60 min, 25% of window) on the 3-D ridges AND the price/volume pane, so the newest spikes/labels aren't jammed on the edge. (Replaces the L9 "pad backward only" note — the bug was a 30-min min window, not the margin.)
- L11b Labels at the right edge are clipped (7,680C 09:34 · 34…) → anchor labels to the left of the line when in the last 20% of the window; stack same-contract labels instead of overlapping.
- L11c Price path leaves the ridge grid (white line drawn below the lowest strike, 08:00–08:30) → clip it to the ridge strike range or widen the strike range to cover the path.
- L11d Ridge normalisation: RTH-open volume (09:30) sets the window p99, so the overnight ridges go flat when the window spans the open → normalise GTH and RTH minutes separately.
- L11e Window spanning the open shows 46 spikes (GTH + RTH thresholds mixed) — check counts per segment; consider top-N per segment for bold.
- L12 Spikes as RIDGE PEAKS, not poles (user 09:58): the AG "double red line" is the ridge itself shooting up and back down. Draw each spike as that strike's ridge rising to the spike height at the spike minute (sharp up/down peak, ±1 min), coloured by direction (L9); the rest of the ridge stays quiet. Drop the separate vertical poles; faint (non-top) spikes = shorter, thinner peaks on their ridge.
- L10 model FOUND (16 Oct rebuild, 10:20): tetris = dealer γ on positions = (OI from prior close × cp sign − cum intraday net bought) × γ(S,t) × S²·1%·100, recomputed every 10 min; global scale ±1 (per-strike/per-column scales don't match AG). Reproduces AG's purple far/late field, warm band above spot, cooler band below, colour collapsing onto price late.
- L10 palette (ours, AG-like): −1 dark blue · light blue · pink · 0 purple · red · orange · +1 tan; height = signed value. Exact AG band edges still unconfirmed — confirm by eye with user.
- L10f evidence: 7810C (OI 14,034, the day's largest) and 7820C were net SOLD every 10 min from 09:30 to 12:10 (−6.1k / −4.7k) → isolated red cells 60–110 pts above spot in the purple field = "calls sold" read is supported. Detector: positive (red+) cell above spot whose 5×5 neighbourhood is ~0, sustained ≥3 buckets.
- L10h Recorder needs prior-close OI per contract each morning (Summary OI already recorded in oi_log) — confirm it is captured before 20:15 for the next day's 0DTE.
- L13 "Download today's data" button in Recorder diagnostics: zip of the day's prints (with spreadLeg flag), chain snapshots, OI and price path, so a full session can be analysed offline (Colab replay caps at 1,000 prints/contract).

## Built in v0.13.0 (APPROVE NEXT BUILD 10:25): L7, L8, L9, L11a–e, L12, L13, L10d.  Still open: L2, L10a–c/f–h (tetris — research), L10h.
- L10 research (10:41, 2nd AG V4 shot): colour band RIDES WITH PRICE (warm red/orange around spot, blue at the band edges, purple far) → value is a per-time profile centred on spot, magnitude palette (purple 0 → light blue → dark blue → red → orange → tan peak). Per-strike-OI stripes don't match; try gamma-weighted activity per column and price-grid γ magnitude, rendered as 3-D voxels.
- L14 Rename "V4 view" → "Tetris" in AG-REV (user 11:16): section header + toggle labels ("Tetris · 3-D" / "2-D heatmap"); the AG-style voxel tetris (L10) replaces the 3-D surface under this name once it matches.
- Note (11:16): AG's 20 Oct 7750P screenshot is the RIDGES view, not Tetris — use it to validate ridges (heat colouring cyan→green/yellow/orange, z-axis in $k premium?, red price stretch while puts sold).
- L15a (20 Oct today-tape check) Spike flood at the open: 138 spikes 06:45–10:40, most at 09:30–10:00 with no z (RTH baseline warm-up = 15 min of size-only firing). Fix: carry the overnight baseline into the RTH warm-up (scale it) or require z ≥ thr from 09:30; cap bold per 15 min.
- L15b Contract pane price colouring like AG: falling stretch red, rising stretch magenta (AG 7750P: red from the $80 peak to the $17 low; 7675P: magenta run-up), not only ±8 min around spikes.
- L15c Ridge colour like AG: each ridge tinted by its activity (cyan → green → yellow → orange), not a single cyan scale; busy strikes read warm at a glance.
- Validation 20 Oct: our 7750P pane = AG's (flat $65–78 pre-open, $80 peak ~09:45, $17.00 low, vol 4,136 vs AG 4,081 at post time).

## Built in v0.13.1 (APPROVE 11:48): L15a–c, L14. Open: L2 (per-viewer GTH), L10 Tetris research (AG block view), L10h.
- L16a Ridges strike range must follow the control bar (Strikes each side / % move) — today it only uses SPXFlow RidgeEachSide, so widening strikes did nothing (user 12:02).
- L16b Ridges strike range must also cover the price path inside the window — L11c clipping hid the 07:00–09:45 path (SPX 7670 open was below the lowest ridge 7690).
- L16c Ridges "GTH on" ≠ ridge window: window buttons (2h/4h/8h/session) decide the span; make the default follow GTH (session when GTH on?) or explain on the control.
- L16d After a reboot the replay gives only the last 1,000 prints per contract → busy strikes have empty mornings. Backfill ridge/pane minute volume from 1-minute option candles (≤90 near-ATM contracts, bid/ask volume) at start-up.
- L10 Tetris status (12:02): magnitude palette on |OI·γ| per strike still gives thin stripes; AG's zones are broad and smooth (look like a price-grid field). Next: sample AG's 16 Oct top-down inset pixels into a colour matrix and fit candidate quantities (γ/Δ/charm/vanna, per-strike vs price-grid, OI vs OI+flow) by correlation instead of eyeballing.
- L17a Strike strip: replace ⚡ stars with RANK NUMBERS (1, 2, 3 … by spike strength premium×z in the window), number coloured by direction (green bullish / red bearish); clicking the number pins that contract (user 12:06).
- L17b C+P pane: call ($25) and put ($3.8) share one y-axis → put line squashed at the bottom. Give each its own axis (call left / put right) or two stacked rows.
- L17c C+P pane: AG swing colours (magenta/red) hide which line is the call and which the put → keep call blue / put orange as the line, draw swings as a thin coloured underlay or markers.
- L17d Ridge labels pile up when several spikes hit the same strikes within minutes (11:53–12:00) → merge labels within ±3 min per strike ("7,700P ×3 · 860c · $310k") and show the rest on hover.
- Note: 3-D ridge clicks can't reach Streamlit (Plotly 3-D limitation) — the strike strip on the right is the click target; user OK with that.

## Built in v0.14.0 (APPROVE 12:07): L16a–d, L17a–d. Open: L2, L10 Tetris (colour-matching research now).
- L18 Tetris (user 20:12 "have both A and E"): AG-REV Tetris view with model A = OI·γ (live price) and E = OI·vega, each strike scaled to its own peak over the window, 3-D blocks (height + 7-band colour), white price line on the blocks, red last-price tag; palette switch "readable + legend" / "AG palette"; options: fixed-at-open layer, RTH overlay, smoothing. Keep current flow surface as a third choice. Decide A vs E over time / with more AG screenshots.
- L18 update (20:14): "AG palette" = bands calibrated to AG's measured colour shares (purple 37 % · pink 5 % · light blue 20 % · dark blue 33 % · red 3 % · orange 1.5 % · tan 0.5 %) → 16 Oct A/E then look like AG (blue-dominant, purple late, warm front-left wall, red specks above price + at the drop).

## FINAL OPEN QUEUE (2026-10-20 20:14 Doha) — each needs APPROVE
- DEPLOY v0.14.0 after the 16:00 ET close (built, tested; includes v0.13.x).
- L18 Tetris view: models A (OI·γ) + E (OI·vega), per-strike peak scaling, 3-D blocks, AG-calibrated palette + readable palette with legend, fixed-at-open layer / RTH overlay / smoothing toggles, today & live data.
- L10f/g "Ready for the sell" detector: isolated red blocks above spot in the purple field (sustained ≥3 buckets) → marker + list; ship only after verifying lead time on 16 Oct.
- L10h Check the recorder captures prior-close OI for the next day's 0DTE before 20:15 ET.
- L2 Per-viewer GTH switch (process-wide today).
- Watch (decide with data): Q5 overnight noise · session end 16:00 vs 16:15 · "B" signal definition · spike counts per session part.

## IN PROGRESS — v0.15.0 (APPROVE 2026-10-20 20:20 Doha: "do it all together") — resume here if interrupted
Scope: L18 Tetris (A γ + E vega, per-strike peak, 3-D blocks, AG-calibrated + readable palettes, overlay/smoothing toggles, top-down inset) ·
L10f/g speck detector (verify lead time on 16 Oct first) · L10h prior-close OI check · L2 per-viewer GTH. Deploy v0.15.0 (includes v0.14.0) after the close.
Prototype code to port: scratchpad tet/rowvar.py (models), tet/voxc.py (voxels + calibrated bands), tet/oi_model.py (16 Oct loader).
Steps: [x] core/tetris.py written  [x] AG-REV wiring  [x] detector checked on 16 Oct → NOT shipped: speck runs fire overnight (00:20–06:40 ET), 4–10 h before the 11:00 break; nothing in a quiet field 10:00–11:20 — kept as research (core/tetris.specks)  [x] L10h (OI coverage in status + Tetris caption; Summary OI arrives at the 16:15 roll and refreshes when OCC publishes)  [x] L2 (gth() reads this viewer session_state; shared caches keyed on gth)  [x] tests (today/gth/real/big)  [x] zip + changelog — v0.15.0 DONE 20:4x Doha

## Built in v0.15.0 (APPROVE 20:20 Doha): L18 Tetris A/E, L2, L10h; L10f/g checked and NOT shipped (no lead before the break).
Still open: deploy v0.15.0 after the close · decide A vs E with more AG screenshots · watch list (Q5 overnight, 16:15 end, B signal, spike counts).

## L19 TASTIER → match the original "Tastier" GEX page (user 13:31 ET, screenshot of Tastier replay 2026-10-19 08:35)
- L19a Header: SPX price + replay badge + regime chip "Positive/Negative GEX <score 0–100>" + "β dealer" toggle (flow-signed vs naive everywhere).
- L19b Metric row 1: Total net GEX · Net bias · Call GEX · Put GEX · Zero gamma · Call wall · Put wall.
- L19c Metric row 2 (β dealer, flow-signed vs naive shown side by side): Flow GEX (vs naive) · Flow γ-flip (vs naive) · Dealer Δ $ · Hedge → close $ (buy/sell) · Vanna −1 vol $ · Customer calls/puts net bought · Spreads · blocks (count, block calls/puts) · "recording" badge.
- L19d Price panel: timeframe buttons 1m/1h/4h/12h + 1D/5D/1M/YTD, MACD/RSI/VRVP toggles, Velocity/Absorb/Pressure, VRVP profile on the LEFT (stacked buy/sell), MA9/MA21, last-price tag, velocity spikes as bars along the top, per-bar delta sub-panel (±kΔ).
- L19e Dealer GEX by strike: flow-adjusted bars coloured (green +, red −) with naive as grey bars behind; spot + zero-gamma dashed lines.
- L19f Dealer hedging panel: three tiles (Into the close $ buy/sell · If IV −1 pt $ · Dealer Δ now $) + time series of dealer Δ (dashed) and hedge-into-close (solid) through the session.
- L19g Customer flow by strike: calls (green) / puts (red) net contracts bought, horizontal bars, spot line.
- L19h Dealer delta & vanna by strike: Δ $ bars (blue) + vanna $ per +1 vol (yellow).
- L19i SPX vanna surface (dealer Δ per +1 vol by price × time, β): orange/blue heatmap with candles + 0γ flip dashed overlay.
- L19j SPX flow-adjusted gamma surface (dealer γ from the tape, β): red/blue heatmap with candles, flip lines, bright bands at big strikes.
- TASTIER becomes a 1:1 of the Tastier page (user 13:33): our old panels are covered by it and are dropped, not moved — GEX by strike → L19e · cumulative net γ → zero-gamma metric · GEX regime → regime chip · imbalance/CVD → per-bar delta + customer flow · 0DTE GEX flow + gamma surface → L19j · charm → 'Hedge → close' (charm-driven).

## DONE — v0.16.0 = L19 TASTIER 1:1 Tastier page (APPROVE 13:34 ET) · built 2026-10-20, zip trishula-v0.16.0.zip
[x] core/dealer.py  [x] tabs/tastier.py rewrite  [x] tests (today/gth/real/empty, all tabs, mem peak 1.37 GB)  [x] zip · deploy after 16:00 ET close
## DONE — v0.16.1 = L20 ridges after reboot (APPROVE 13:51 ET): backfill waits for spot/legs + 30 s first-row wait + retry, status caption under ridges, premium height on one window scale, one colour per ridge (contracts), right margin 18 %, Tetris overlay labels 20:15 vs 09:30
## DONE — v0.16.2 = L20e–g "now" readable: linear max scale, only top-N spikes drawn, AG non-linear time axis (night ¼)
## L21 Tetris brute force — RESULT (research/l21): best = PRICE-GRID Σ OI·|vanna(P,K)| (overall 0.81 / temporal 0.38 vs our model A 0.46); AG labels are Central time. NOT WANTED — user is happy with Tetris as in v0.16.0 (research kept only). Open: AG asymmetric (warm above spot after open)
## DONE — v0.16.3 = L22 ridges matched to AG 20 Oct side by side: height = contracts/min, unsmoothed, one linear scale (premium/smoothing/z-scores rejected). research/l22
## L23 (research done, build needs APPROVE) — spotting turns (research/l23, 16 Oct + 20 Oct, 39 zig-zag turns)
- timing: B contracts near spot lift 1.3–1.9; E breadth (# strikes ±50 with z>4 vs own 30 min) lift 1.5–2.4; single-strike max z / z60 / z120 ≈ noise
- direction: raw net bull−bear flow is CONTRARIAN at turns (right only 21–43%); DT band-crossing squares point the right way 71–80% ([3%/100/±1%/14])
- proposal: ridge height toggle AG/unusual(z30, unsmoothed) + breadth strip under ridges + DT squares on the ridge price path; confirm on ~10 more days first (Colab dump of past sessions: candles stay served for expired contracts)
- volume vs single-leg settled: AG 7750P pane 4,081 = our total at ~10:38 (single-leg would be ~3,100; spread share 24 %)
## DONE — v0.16.4 = L22b noisy ridge edge: cause = 1m backfill empty after restart → past from 1,000-print replay only (near-spot reaches back 30–90 min); fix = fill pre-first-print minutes from 5-min candles (proven loaded in prod). Proven on live day zip 20 Oct 16:30 + reboot harness (65→11 spikes)
OPEN: why 1m backfill returned 0 in v0.16.0 (6-s early break suspected; v0.16.1 waits 30 s) — confirm via status line after deploy
## DONE — v0.16.5 = L23 ridge height toggle AG (default) / unusual vs own 30 min (APPROVE 23:54 Doha). Breadth strip + DT on ridges NOT wanted (DT improvement = separate future item)
## L24 (research done on 11 days, build needs APPROVE) — research/l24
- L24a DT v2 (tested, research/l24 dtgrid2): ADAPTIVE BAND = max(floor, α·strike's own last-30-min volume) α 0.25–0.5 (squares 150→12/h; robust settings 2–3× more), optional delta weighting + 2–3-strike agreement within 3 min; keep user sliders, add "band mode: dot / adaptive". THEN classify by price response: classify squares by price response — "confirmed" (net ≥20 squares/10 min + price ≥6 pts) = follow ▲, "absorbed" (net ≥40/5 min + price ≤1 pt) = fade ■; plain DT follow loses out of sample
- L24a+ (idea3): v2 follow ≥2 net strikes/3 min + per-strike cooldown 10 min (+1.76/+2.69); classic DT kept as "absorbed→fade" reading at ≥3 net strikes; OI tests done: GEX as FILTER (trust/follow DT only when GEX>0 at current spot; stand aside in −GEX) — textbook switch fails; filled/hollow labels carry no info vs next-morning OI (consider dropping hollow or relabel)
- L24b ridge price-path markers (optional): initiation (10-min net flow + 4 pts) ● and exhaustion+breadth (15-min 8 pts, ≥5 unusual strikes) ◆
- caveat: hit 47–60 %, edge 1–2 pts/20 min, regime-dependent; re-test as days accumulate
## DONE — v0.17.0 = L24 DT v2 as default (adaptive band α0.25/floor200/±0.30%/watch15/cooldown10, follow ≥2 strikes/3 min, GEX>0 gate, initiation ●) + live scorecard (also in 📦 day zip) (APPROVE 18:09 ET). core/dtv2.py reproduces research exactly.
NEXT: collect day zips (dt2_scorecard.parquet) for 2–3 weeks → re-score; L24b ridge markers not built (DT tab only)
## QUEUED (21 Oct, user "queue them") — each needs APPROVE
- L26 v0.17.1 MEMORY FIX (urgent — app OOM-killed 13:04 ET 21 Oct at 2,365 MB, 985k prints, no traceback = platform kill):
  _all_prints converts 8 categorical cols back to str for ~1M rows and stores that as the chunk → keep compact storage
  (arrow strings / categories), return only used columns, cache per-expiry slice per n_prints (tabs share, no copies),
  mem guard also folds 1DTE prints older than ~2 h into per-minute totals (0DTE tape untouched), pin library versions
  (prod: pandas 3.0.6, pyarrow forced to 24 by Streamlit), load test with a synthetic 1.5M-print day
- L27 Tetris mode "G · price-grid γ" as DEFAULT (A/E kept): price grid, γ × (OI + traded since 20:15), live per-minute IV,
  expiries 0DTE→Friday, each time column scaled to its peak (research/l25: 21 Oct 0.68/0.51 vs our A −0.04/0.20; top-3 on 20 Oct).
  Open: AG's vertical columns still unexplained (global scaling fails; maybe 3-D occlusion)
- L28 test the 21 Oct caption pattern on the 11 sessions: calls sold above + puts bought below while price flat (09:40–10:00
  21 Oct: 7800–7815 C sold ~2:1, 7715–7735 P net bought, dip 10:00–10:11) → bearish warning; score forward 10/20/30 min
- Colab scripts: drop "--upgrade pyarrow" from the pip line (21 Oct dump crashed on save from a pyarrow clash)
- L29 (research first) SIGNAL FROM NOISE on history: every swing ≥0.3 % (~23 pts) on all available sessions (history dump);
  test per-strike features BEFORE the swing vs random times: persistent strikes (same side ≥3 of 4 five-min bins, ≥1.5:1),
  delta-weighted lean of persistent strikes, call-wing vs put-wing selling asymmetry, near-spot put/call buying, price-flat
  filter; 21 Oct prototype (research/l28): bearish lean 09:45–09:50 before the 10:00 dip (modest), strong bullish lean at the
  10:11 low (reversal). Far-OTM put-selling wing = background (filter). Only then pick the visual.
- HISTORY LIMIT: tastytrade serves expired SPXW candles only ~4 weeks back (history run 21 Oct stopped at 24 Sep).
  ROUTINE: weekly Colab run of trishula_history_dump.py for the last 5 sessions (START = last trading day, OLDEST = that
  Monday, ~25 min) or the 📦 day zip each evening → rerun research/l28/l29.py unchanged at ~25–30 fresh days.
- L29 RESULT #2 (9 FRESH days: 24–30 Sep, 1/2/5 Oct, 21 Oct; same script): only S1 aggressive block ×10 near significance:
  edge +1.42 pts/20 min, t 2.03, 54 % right, n 160, 6/9 days positive (but 18 tests → one t≈2 expected by chance; need t≈3)
  S4 DT v2 follow 2 strikes +1.81 (t 1.25, n 33); S5/S6/S3 faded toward 0; S2 setup still negative → rejected
  → keep collecting history; rerun unchanged at ~25+ fresh days; candidates to watch: S1 ×10, S4
- L29 RESULT #1 (21 Oct 14:40 ET, 17 sessions; 6 FRESH = 29 Sep–5 Oct + 21 Oct; research/l28/l29.py), edge = pts at 20 min
  vs 200 random same-day same-direction entries. On the 6 fresh days NOTHING is significant (all t < 1.4):
  S2 loading setup (the 21 Oct caption pattern) NEGATIVE fresh (−1.5 / −3.0 at 1.6 / 2.2:1) → rejected
  S4 DT v2 follow: +3.4 on the 11 design days but +0.2 fresh (n 15) → its edge was in-sample
  weak positives fresh: S6 exhaustion 8 pts +1.5 (61 %, n 36), S3 flip 2000 +1.8 (n 33), S1 block ×10 +1.0 (n 113), S5 init 5 % +0.9 (n 80)
  → do NOT build L30 yet; rerun the SAME script when the history run finishes (more fresh days)
- L29/L30 SIGNAL SET (agreed 21 Oct 14:06) — tiers by intensity, probabilities from history (per signal × tier vs random, both halves):
  S1 aggressive block against the move (leading) · tiers 5× / 10× / 20× own median minute, ≥90 % at ask/bid, 0DTE+1DTE
  S2 loading setup (wing sold + near puts bought, price flat) · tiers 1.4 / 1.6 / 2.2 : 1
  S3 near-spot flip (turn confirm; caveat: may be profit-taking, fires AT the turn) · tiers 500 / 1,000 / 2,000 net
  S4 DT v2 follow (trend) · 2 / 3 / 4+ strikes, brighter when GEX > 0
  S5 initiation (trend) · 5 % / 10 % / 15 % share
  S6 exhaustion + breadth (fade) · 8 / 12 / 16 pts with ≥5 unusual strikes
  Display (L30, replaces DT classic): price line + arrows only — shape = signal, size = tier, colour = direction, caveat in
  label; side table: live signal, tier, historical hit % and avg pts at 20 min; tiers without edge greyed "no edge".
- L29 LOCKED RULES (written 21 Oct 14:05 ET, BEFORE the history; test once, no new variants after):
  R1 setup (research/l28/setup.py as is) · R2 DT v2 follow · R3 initiation · R4 persistent-strike lean z ≥2.5
  R5 near-spot flip: puts+calls within ±25 of spot change side, ≥500 contracts / 5 min (wings = background)
  R6 AGGRESSIVE BLOCK AGAINST THE MOVE (from the 21 Oct tape: 22 Oct 7750C ~340 bought at the ask 10:05/10:08 while SPX fell,
     3–7 min before the 10:11 low): one contract, one minute, size ≥ 5× its own median minute and ≥100 contracts,
     ≥90 % at ask (or bid), against the last 15-min move → fade the move; 0DTE AND 1DTE
  Each vs random alerts at the same frequency; trust only what holds in both halves; swings ≥0.3 % as the turn set.
- L29a SETUP detector (research/l28/setup.py): bearish = call wing (spot+30…+90) net SOLD ≥1.4:1 in ≥3 of 4 five-min bins
  + puts near spot (−25…+5) net bought over 15 min + 15-min range ≤15 pts (bull = mirror). 21 Oct: fired 09:45 & 10:00
  (+17 pts each at 20 min), 10:35 wrong. 11 sessions: BEAR 52 alerts avg +0.5 pts/20 min, 60 % right — but week 14–20 Oct
  +1.6 (69 %) vs 6–13 Oct −1.2 (45 %) → regime-dependent; BULL mirror fails (24 % right). Needs history (L29) before building.
- L30 (after L29) replace DT classic with a "LEAN" layout: strike ladder (delta-weighted bearish/bullish flow per 5 min,
  persistent-strike boxes) + lean bar + alerts on the confirmed features; v2 stays
- Colab: trishula_history_dump.py (walks back from 5 Oct, stops after 5 empty trading days, zip after every day)
- L31 VS3D Book: KEY LEVELS + TAKEAWAYS card is far too big → render at ~40 % of its current size (smaller figure/font in
  core/book.py key-levels card, or display width ~40 %); keep it legible (user 21 Oct 14:09)
- L32 LIVE STALLS — ROOT CAUSE FOUND (user screenshot 14:11: bar showed "⏸ REPLAY Wed 14:09"): core/player.py sets
  ss["pl_scrub"] = latest frame every live run; a new snapshot frame arrives (every 60 s); on a tab switch the browser sends
  the stale slider value back → Streamlit fires on_change=_scrub → pl_mode="replay", paused on the old frame.
  FIX: in live mode render the scrubber with a key that changes with the frame count (fresh widget, no stale value) and
  ignore _scrub unless the value differs from the latest frame by a real user move. Also: (a) long full-page reruns under memory
  pressure look frozen (fixed mostly by L26) — skip the live tick while a page run is still in progress (no stacked reruns);
  (b) the frame scrubber (pl_scrub, value pushed every run) must only switch to replay on a real user change; (c) clear
  "REPLAY — press ⏹ LIVE" banner when not live; (d) last full-run duration + per-tab timings in Recorder diagnostics.
  Ask user next time: player bar says 🔴 LIVE or ⏸ REPLAY? "Running…" spinning?
After deploy CHECK: caption under ridges must read "1-min backfill: N/N contracts" — if ⚠ or pending, tell Claude
Follow-ups: L19k (PARKED by user 13:48) rebuild TASTIER history/surfaces without snapshots: OI + spot (ES − parity basis) + imp_vol from 1m option candles + per-time signs from candle bid/ask vol; prototype scratchpad/l19k/proto.py works on 20 Oct (9 s, GTH→11:25); recorder c1m must also store imp_vol · L19l compare tiles vs Tastier live after deploy
