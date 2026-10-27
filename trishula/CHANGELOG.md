# TRISHULA changelog

Semantic versioning: MAJOR.MINOR.PATCH. The running version is shown in the app's
status bar, every tab footer, and the Recorder diagnostics panel.

## v0.20.3 — 2026-10-27 · feed no longer repaints
- The feed recomputes the whole session every minute; late data (the 5-min candle sweep tops up the last 20 min, a restart
  rebuilds the morning, 10-min cooldowns chain from earlier marks) could move or remove marks already sent — after every
  NinjaTrader reload the arrows sat in different places. Now a mark ≥ 3 min old is LOCKED (final=true) and re-sent
  unchanged for the rest of the session; marks that would appear later for an already-locked time are dropped; marks
  younger than 3 min are sent with final=false. `locked_until` in the payload. (A reboot rebuilds from candles.)

## v0.20.2 — 2026-10-27 · overnight marks in the NinjaTrader feed
- Feed now also computes the OVERNIGHT session (Cboe GTH 20:15 → 09:30) with the same rules and settings; overnight marks
  carry session="GTH", tested=false, passed=false, rth_passed = whether that signal × setting passed the RTH test.
  ES level overnight = the ES price of that minute (overnight SPX is derived from ES); RTH = SPX × ES/SPX. The feed thread
  runs whenever the market is in RTH or GTH (+ a final write after the close).
- NinjaTrader indicator v2: "Include overnight (GTH, untested)" switch (with "only passed" ON, overnight marks show only
  for signals that passed in RTH), own overnight colours, "S6 ON" label · chart label shows just "TRISHULA" (never the
  URL) · redraws only when the feed or a setting changes, only NEW marks are drawn (no full redraw / refresh every poll).

## v0.20.1 — 2026-10-27 · fix: dark theme restored
- v0.20.0 overwrote `.streamlit/config.toml` (dark theme) when adding static serving → the whole app turned white.
  Theme restored; `enableStaticServing = true` kept.

## v0.20.0 — 2026-10-27 · password + NinjaTrader signals feed
- **Password:** the app asks for `APP_PASSWORD` (Streamlit secrets) before showing anything; wrong password → nothing.
  The recorder and the feed keep running behind the login.
- **Signals feed:** a background thread recomputes the Signals-view marks (S1, S3–S7; no DT v2 marks) every 60 s during
  RTH for every sensitivity × tape and writes `static/dtsignals_<SIGNALS_KEY>.json`, served at
  `https://trishula.streamlit.app/~/+/app/static/dtsignals_<SIGNALS_KEY>.json` (static files can't sit behind the app
  password, so the long random key in the name is the protection). Each mark: time (ET), signal, direction, mode,
  sensitivity, passed-the-test flag, SPX level and **ES level = SPX × ES/SPX of that minute** (ratio, rounded to the
  0.25 tick). Status / last write in Recorder diagnostics; a `[feed]` line in the log each minute.
- **NinjaTrader 8 indicator** `ninja/TrishulaSignals.cs` (+ README): polls the feed, draws ▲/▼ at the ES level (or bar
  high/low), filters by sensitivity, tape, each signal, only-passed; status text with STALE warning.
- `.streamlit/config.toml` (static serving) added.

## v0.19.3 — 2026-10-26 · crash hardening + TASTIER surfaces that survive a reboot (L45)
- **Memory / crash (app died 26 Oct ~12:43 ET, no traceback, while a whole extra expiry — Wed 28 Oct — was being
  added):** a `[mem]` line in the Streamlit log every 5 min (memory, prints, 1-min candles, snapshots, legs, subscribed
  expiries, cache sizes) so the next kill shows what grew · extra expiries replay only the last 2 h and are REFUSED with
  a warning above 1,400 MB · the 1-min candle table is built once per data update and shared by every tab (was rebuilt
  by ridges, Signals, DT, Tastier separately) · a subscribe on a closing connection is caught and retried instead of
  killing the recorder task.
- **TASTIER flow-adjusted gamma + vanna surfaces (L45):** rebuilt from the 1-min option candles instead of chain
  snapshots, so a reboot no longer leaves a single column of flat bands. Every 5 min: dealer position = morning OI ×
  sign − contracts customers bought net since the open (ask − bid volume), γ and vanna at every price level with that
  minute's IV, causal. Each time column scaled to its own peak (gamma grows ~10× into the close). 0γ flip line and
  candles on top. New **"Δ today"** view: γ ADDED (green) / REMOVED (purple) for dealers by today's flow — where new
  positioning goes in (21 Oct test: green above = calls sold, purple below = puts bought — the morning caption pattern).
  Falls back to snapshots only if no candles. Recorder now stores each 1-min candle's IV.

## v0.19.2 — 2026-10-25 · Tetris default = AG scale (window up to now) (L42)
- Tetris scale switch: **AG · to now** (default) = each strike scaled to its peak in the window up to now, as AG's
  screenshots are — no future data, past colours re-rank as the day goes on · **frozen** = peak so far, never changes.
  (v0.19.0's "hindsight" label was wrong: it never used future data.)
- L43 (research/l43, pre-registered, 12 days with OI, chart rebuilt every 10 min with data up to that moment):
  A "price into heat → fade" −0.78 pts/20 min (t −0.8, 36 % of days +); A "turn confirmed" −3.8 (n 10); E "price into
  heat → fade" +5.3 (t 2.1) but only 10 trades on 7 days. Rule needed A and E → FAIL. No tradeable Tetris rule yet.

## v0.19.1 — 2026-10-25 · 0DTE / 0+1DTE toggle everywhere (L41)
- **Tetris A/E:** "0DTE / 0+1DTE" switch — 0+1DTE sums both expiries per strike, each leg with its own time to expiry;
  no-repaint rules unchanged. Default 0DTE (how A/E were matched to AG).
- **Signals:** "tape" switch — every signal on 0DTE only, or every signal on 0DTE + 1DTE. Each mode has its OWN
  walk-forward record (research/l35, 22 days, all with 1DTE now — the 6–20 Oct 1DTE candles were in the OI pull):
  · 0DTE: S6 exhaustion + breadth "middle" passes (+2.74 pts at 20 min vs random, t 2.05, 3/4 blocks)
  · 0+1DTE: S6 "more" passes (+2.70, t 2.66, **4/4** test blocks, ~8.8 marks/day) — the strongest result so far
  · S6 is positive in every position in both modes; S1 small positive; S7 ≈ 0 with 1DTE, negative 0DTE-only
- **DT v2:** "DT tape" switch (0+1DTE untested).

## v0.19.0 — 2026-10-25 · no-repaint maps, one-slider Signals (walk-forward), simpler DT, status badge
- **Tetris (L33/L36):** opens on **A**; G and the "readable" palette removed. New **scale** switch: **no repaint**
  (default) = each strike scaled to its peak SO FAR, colour bands from the values so far (mid-rank, so ties at a
  strike's running peak band correctly), a FIXED strike set for the session (±200 pts around its first price, display
  cropped), and IV / OI per bucket from the RECORDED chain snapshots → a drawn column never changes. **hindsight** =
  the v0.18 look (scaled to the day's peak, repaints) with a warning in the title.
  L34 finding (research/l34): the warm blocks at highs/lows in the old view are HINDSIGHT — a strike hits its day peak
  when price comes closest to it. Causally (12 days with OI) there are almost no warm blocks: 1 event, lost → no edge.
- **Terrain (L36):** columns left of "now" are FROZEN the first time they fall behind now (values and colours as drawn;
  after a restart rebuilt from the chain snapshot recorded at that minute, ≤ 10 min old); right of "now" = projection
  from the current chain, recomputed every frame and dimmed, dashed "now" line with "← frozen past · projection →".
  Same for the charm panel. Shared by every viewer for the day + field settings. Test: past identical after a large
  chain change, future changes. Book and GEX³ unchanged (by design).
- **Signals (L35/L35b):** ONE "Signal sensitivity" slider (fewer / middle / more) + "show unproven" toggle. Each position
  uses the thresholds a WALK-FORWARD test picked (research/l35, 22 sessions: chosen on earlier days, scored only on the
  next 3, rolled 4 times, 12 test days). Result: only **S6 exhaustion + breadth at "middle"** passed (+2.74 pts at 20 min
  vs random, t 2.05, 3/4 test blocks, ~5.5 marks/day) — with 18 tests one pass is expected by luck, so "worth watching".
  S1 positive in all 4 test blocks but small (t 1.2–1.4); S7 quiet big block NEGATIVE; S3/S4/S5 ≈ 0. Unproven marks are
  hidden by default. Table = each signal's out-of-sample record at the chosen sensitivity.
- **DT v2 (L37):** one "DT sensitivity" slider (fewer / tested / more); ± range comes from the control bar's strike
  window; watch strikes / cooldown in an "advanced" expander.
- **Player bar (L38/L39):** "⟳" refresh-now button next to "refresh N min"; badge 🟢 LIVE · RTH / ⚪ LIVE · GTH /
  🔴 CLOSED (weekends, holidays, 16:00–20:15) instead of an always-red LIVE.
- **Contract pane (L40):** axis titles "7650C price $" (left, blue) / "7650P price $" (right, orange), legend,
  "contracts / min" on the volume bars, each "low" label on its own side, ridge axis titled "strike".

## v0.18.1 — 2026-10-22 · FIX: 1-minute option candles were thrown away (backfill + sweep showed 0/182, 0/116)
- Root cause (live caption 22 Oct 03:05 + the Colab pull): dxfeed returns 1-minute candles under the symbol
  `…{=m}`, not `…{=1m}`. The recorder only kept events whose spec contained "=1m", so EVERY 1-minute option candle
  was dropped — since v0.16.1. This is why the 20 Oct and 21 Oct ridges lost their morning after a reboot even with the
  backfill (and why v0.16.4 had to patch the past from 5-minute candles). Now `{=m…}` and `{=1m…}` are both kept.
- Nothing else changed. Expect the caption under the ridges to read "1-min backfill: ~180/182" and
  "candle sweep … ~116/116" within a few minutes of the reboot.

## v0.18.0 — 2026-10-22 · FIX RELEASE: memory, live stalls, ridges after reboot, Tetris G, Signals view, smaller card
- **Memory (L26, app was OOM-killed 21 Oct 13:04 at 2,365 MB):** the print store stays categorical (it was converted to
  strings and kept that way), chunks merge with unified categories, ONE cached slice per expiry shared by every tab and
  browser session (no per-tab copies). Guard: thin old snapshots above 1,400 MB (was 1,800); above 1,800 MB also fold
  prints of later expiries older than 2 h into per-minute rows (volume and bought/sold split kept). pandas pinned 3.0.6.
  Test: 1.5M prints + 900 snapshots, every tab → peak 1.29 GB (v0.17: higher at 1.0M).
- **Live stalls (L32):** the frame slider kept one key whose value was pushed every run; after a tab switch the browser
  sent the stale value back and the app dropped into ⏸ REPLAY on an old frame. Now each frame gets a fresh slider key and
  a "change" equal to the frame on screen is ignored. Blue banner while frozen in replay. Recorder diagnostics: seconds,
  time and memory of the last run per tab. Test: 20 tab switches while new frames arrive → stays 🔴 LIVE.
- **Ridges after a reboot (L20h):** new recorder candle SWEEP every 5 min — 0DTE AND 1DTE contracts within ±14 strikes:
  contracts without candles are fetched from 20:15 the evening before (rebuilds the whole session after any restart),
  the rest topped up for the last 20 min. The ridges' past now comes from candles; prints only for the newest minutes.
  Caption under the ridges shows the sweep. Test: simulated 21 Oct reboot at 12:55 → full morning on the ridges.
- **Ridges look (user pick 22 Oct):** default view **ridgeline** — flat AG-style ridges, each sitting AT its strike on the
  price axis with SPX drawn through them, nearer ridges hide the ones behind (no crossing lines), one colour, pinned
  strike red, top spikes as ▲ green / ▼ pink marks, contract pane underneath on the same time axis. **3D** kept (AG camera:
  front, high, orthographic, one colour) and the old 2-D view as **map**. Defaults: window **RTH** (from 09:30; overnight
  squeezed RTH into the right edge), strikes ±60 pts (widened to cover the price path), expiries **0+1DTE** summed per
  strike (AG's ridges include tomorrow's contracts). Bearish spike colour moved to pink (red = pinned).
- **Tetris G · price-grid γ (default, L27):** for every price level, the gamma all open positions (0DTE→Friday held by the
  recorder; OI + contracts traded since 20:15) would carry if SPX stood there; live IV from the recorded chain snapshots;
  each time column scaled to its peak, on a ±130-pt price grid with colour shares measured on AG's 21 Oct chart (as in
  the research render). Best match to AG's 21 Oct chart (research/l25: 0.68 / 0.51 vs model A −0.04 / 0.20) — it
  reproduces his LAYERING (warm core above price, blue, purple), NOT his vertical column flicker. A and E kept.
- **Signals view (L30, replaces DT classic):** VS3D → DT → "signals": clean price line + arrows, shape = signal
  (S1 block vs move ▲ · S3 near-spot flip ◆ · S4 DT v2 follow ↑ · S5 initiation ● · S6 exhaustion ★ · S7 quiet big
  block ■), size = tier, hollow = no proven edge. Rules = the locked research versions (research/l28/l29.py), 0DTE+1DTE
  tape. Side table: each signal × tier's record (20 days, 9 fresh) and verdict; today's marks with SPX 10/20/30 min
  later (also in the 📦 day zip: signals_card.parquet). S2 dropped (negative out of sample). DT v2 unchanged (default).
- **Book card (L31):** KEY LEVELS + TAKEAWAYS card ≈ 40 % of its old area.
- New **RESEARCH_LOG.md**: everything explored — cracked, open, next step and the data it needs.

## v0.17.0 — 2026-10-20 · DT v2: the tested settings as defaults + live scorecard (L24)
- VS3D → DT opens in **v2 · tested** (classic DT one click away, unchanged, with its tested reading in the caption).
  Defaults are the settings that held up out of sample on 11 sessions (6–20 Oct, research/l24), core/dtv2.py:
  · squares: ADAPTIVE band = max(floor 200, α 0.25 × the strike's own last-30-min volume), ±0.30 % of spot, 15 watch
    strikes, 10-min per-strike cooldown, counted from 09:30 (classic "5 % of dot" band was inert: ~150 squares/h)
  · ▲▼ follow = ≥ 2 net strikes the same colour within 3 min; bright when dealer GEX > 0 (naive, morning OI at the
    minute's spot), grey = stand aside (in −GEX following lost 2–5 pts per signal; the textbook switch failed)
  · ● initiation = 10-min net flow ≥ 5 % of volume (±50 of spot) and price ≥ 4 pts the same way → follow
  · first signal 09:40, 10-min cooldown between signals; GEX strip under the tape; sliders for every setting
  · research per signal at 20 min (week 6–13 / 14–20 Oct): follow +1.76 / +2.69 (31 / 24), initiation +1.08 / +2.59
    (75 / 65) — reproduced exactly by core/dtv2.py
- **Scorecard** under the tape: every signal today with the SPX move 10 / 20 / 30 min later, hit rate and average per
  signal type (and follow with GEX > 0 only). Kept per session until a reboot and added to the 📦 day zip
  (dt2_scorecard.parquet) so results can be collected across days.
- Tested and NOT used: textbook GEX switch, filled/hollow vs next-morning OI (no information), off-pattern squares,
  price-regime switch, one-label-per-burst on v2.

## v0.16.5 — 2026-10-20 · ridge height toggle: AG / unusual (L23)
- New control above the ridges: **AG** (default) = contracts per minute on one scale, AG's view (where the volume is);
  **unusual** = each strike vs its OWN last 30 min (robust z: median / MAD, current minute excluded, ≥ 0, unsmoothed,
  10-min warm-up; the 30 min before the window are used as history). Steady heavy volume fades, what is new for
  that strike stands up. Picked from the turn test (research/l23): breadth of z>4 vs own 30 min was the best
  timing signal (lift 1.5–2.4 on 16 + 20 Oct); 60-min smoothed was weaker.
- Same colours (one per ridge = contracts traded), spikes, time axis and right margin in both modes; the pinned
  contract follows the mode; the title says which one is on.

## v0.16.4 — 2026-10-20 · the noisy ridge edge, found and fixed (L22b)
- Cause (from the live 📦 day zip, v0.16.0): after a restart the 1-minute backfill returned nothing, so the past came
  only from the TimeAndSale replay, capped at the last 1,000 prints per contract — for strikes near spot that reaches
  back only ~30–90 min. Near-spot ridges were empty for most of the session ("past looks beautiful") and full
  only since the restart ("noisy edge"); the spike detector also fired on the newest minutes (65 vs 11 spikes).
- Fix: minutes before a contract's first recorded print, with no 1-minute candle, are filled from the uncapped
  5-minute candles (volume ÷ 5 per minute) — these DID load in production (398 contracts, 09:30–16:15).
  1-minute candles still win when the backfill lands (v0.16.1+: waits, 30 s first-row wait, retry, status line).

## v0.16.3 — 2026-10-20 · ridges = contracts per minute, like AG (L22)
- 📦 Today's data zip now also holds opt1m_backfill.parquet (the 1-minute option candles the ridges use before a restart).
- L22 brute-force comparison with AG's 20 Oct 7750P ridge chart (07:00–10:36 ET, strikes 7650–7790), rendered
  side by side: premium $ (v0.16.2), contracts, √contracts, log ratio to own median, robust z vs own last
  30 / 60 min. AG matches CONTRACTS PER MINUTE, UNSMOOTHED, ONE LINEAR SCALE: flat pre-open with small blips,
  the floor steps up at 09:30, sharp single-minute spikes (the circled 7750 spikes 09:38–09:47), upper strikes
  busy at the end. Premium over-weighted the in-the-money strikes and the 3-min smoothing removed the spikes;
  z-scores erased the open step. Ridge height now = contracts / min, no smoothing (v0.16.2's one-scale,
  top-N spikes, non-linear time and right margin stay). Tetris unchanged.

## v0.16.2 — 2026-10-20 · "now" is readable on the ridges (L20e–g)
- L20e ridge height on ONE linear scale set by the window's biggest minute (was: 99.5th percentile, clipped at
  1.6×) — RTH trades ~100× the overnight premium, so the old cap saturated the newest hours into a loud wall;
  now a typical RTH minute is ~3 % high and only real bursts stand up.
- L20f only the top-N spikes (and the pinned strike's) are drawn as peaks; the other spikes stay in the table and
  the strip (89 faint peaks crowded the newest hours).
- L20g AG-style non-linear time axis on the 3-D ridges: overnight ¼ width, the hour before the open 0.6, regular
  hours full width (labelled ticks), so the current session is not squeezed into the last 13 % of the chart.

## v0.16.1 — 2026-10-20 · ridges read like AG again after a reboot (L20)
- L20a 1-minute backfill no longer skips silently right after a restart: it waits up to 120 s for spot / legs
  (falls back to the middle strike), each batch waits up to 30 s for the first candles (was: gave up after 6 s),
  and a thin result retries the missing contracts once. Without it the morning came only from the 1,000-print
  replay, so everything after the reboot looked loud and the spike detector fired on the newest minutes.
- L20b the backfill result is shown under the ridges ("1-min backfill: 180/182 contracts …", ⚠ when thin).
- L20c ridge height = premium $ per minute on ONE scale for the whole window (AG's axis is in $k; AG's overnight
  reads flat next to the open). Each ridge keeps one colour along its length = contracts traded at that strike.
- L20d right margin 18 % of the window (20 min – 4 h) and forced in the 3-D view (it was ≤ 60 min, too small to see).
- Tetris overlay labels: "+ traded since 20:15 (overnight)" vs "+ traded since 09:30"; with GTH off only 09:30 shows.

## v0.16.0 — 2026-10-20 · TASTIER = 1:1 Tastier GEX page (L19)
- L19 TASTIER rebuilt to the original Tastier page layout; the old regime / imbalance / 0DTE flow /
  charm surface / cumulative-γ panels are dropped (the page covers gamma, delta and vanna).
  · header: SPX price · live/replay badge · "Positive/Negative GEX <score>" chip · β dealer switch
  · row 1 (open interest, naive): Total net GEX · Net bias · Call GEX · Put GEX · Zero gamma · Call wall · Put wall
  · row 2 (β = flow-signed from the tape, naive alongside): Flow GEX · Flow γ-flip · Dealer Δ · Hedge → close ·
    Vanna −1 vol · Customer calls/puts net bought · Spreads · blocks
  · SPX price: 1m/5m/15m/1h, MACD/RSI/VRVP (buy/sell split, on the left, POC), Velocity spikes along the top,
    Absorb / Pressure markers, MA9/MA21, last-price tag, per-bar delta ($M) sub-panel
  · Dealer GEX by strike (flow-adjusted colour bars, naive grey behind, spot + 0γ)
  · Dealer hedging: Into the close · If IV −1 pt · Dealer Δ now, plus dealer Δ / hedge-into-close lines
  · Customer flow by strike (calls / puts net bought, contracts) · Dealer delta & vanna by strike
  · SPX vanna surface and flow-adjusted gamma surface (price × time, 5-min snapshots, candles, 0γ flip)
- core/dealer.py: the maths (BS greeks, r=q=0). Checked on the 20 Oct chain vs Tastier: call 22.25B / put −19.8B
  vs 24.31 / −21.21, score 53 vs 53, zero γ 7,714.7 vs 7,712.5.
- Seeded (replayed) prints get their delta from the chain, so per-bar delta works after a restart.
- Note: history lines and surfaces apply today's tape signs to earlier snapshots (β mode).

## v0.15.0 — 2026-10-20 · Tetris (L18), per-viewer GTH (L2), OI check (L10h)
- L18 AG-REV **Tetris** (AG-style 3-D blocks), reverse-engineered on the real 16 Oct tape against AG's
  16 Oct chart: per strike, weight × greek through the session, EACH STRIKE SCALED TO ITS OWN PEAK.
  · model A = open interest × γ, model E = open interest × vega (keep both until more AG screenshots)
  · weight: OI fixed at open, or + contracts traded since the session open / since 09:30
  · palette "AG" (band edges matched to AG's colour shares — warm = rare extremes) or "readable" + legend
  · price path drawn on the blocks, red last-price tag, top-down view beside it, optional smoothing
  · the earlier flow surface and 2-D heatmap stay as choices. A visual match, not AG's confirmed formula.
- L10f/g "ready for the sell" speck detector checked on 16 Oct: isolated warm blocks above spot fired
  overnight (00:20–06:40 ET), 4–10 h before the 11:00 break, none in a quiet field 10:00–11:20 → NOT shipped
  (kept in core/tetris.specks for research).
- L10h prior-close OI coverage shown in the recorder status ("oi_0dte_legs") and under the Tetris
  (e.g. 227/262). OI arrives with the session subscription at the 16:15 roll and refreshes when OCC publishes.
- L2 the 🌙 GTH switch is now per viewer (two browsers no longer flip each other); shared caches keyed on it.
- research/ holds the tetris prototypes (no tokens; Colab dumps stay off GitHub).

## v0.14.0 — 2026-10-20 · restart-proof ridges (L16), strip ranks & pane (L17)
- L16d After a restart the recorder backfills 1-minute option candles (uncapped: volume, bought/sold,
  close) for 0DTE contracts within 45 strikes of spot from 20:15 ET the evening before, in batches of
  90 (tastytrade candle cap), once, then unsubscribes (~15–25 MB). Ridges, spikes and the contract pane
  merge them with the recorded prints, so a mid-session reboot no longer empties the morning.
- L16a ridge strikes follow the control bar (Strikes each side / % move; RidgeEachSide is the minimum).
- L16b ridge strikes always cover the price path in the window (the 7,670 open was below the grid).
- L16c ridge window defaults to "session" when 🌙 GTH is on (4h when off).
- L17a strike strip shows rank numbers (1 = strongest spike in the window) coloured by direction;
  click a number = that contract, click a bar = the strike (C+P). Strip toolbar hidden.
- L17b/c C+P pane: call and put each on their own price axis (call left/blue, put right/orange); the
  rising/falling stretches are a translucent underlay so the lines keep their identity.
- L17d ridge labels merged per strike for spikes within 3 min ("7,700P ×3 11:53–11:59 · 860c · $310k").

## v0.13.1 — 2026-10-20 · validated on today's tape (L15, L14)
- Checked against AG's 20 Oct 7750P screenshot on the real tape: pane matches (flat $65–78 pre-open,
  $80 peak ~09:45, $17.00 low, volume 4,136 vs AG's 4,081 at his post).
- L15a no spike flood at the open: while a contract has no regular-hours history yet (first ~30 min
  after 09:30) it must take ≥3× its overnight share of chain volume, instead of firing on size alone.
  Today 06:45–10:40: 138 → 54 spikes; 09:30–09:45: ~100 → 6.
- L15b contract pane coloured like AG: zig-zag stretches of ≥20 % — rising magenta, falling red
  (7750P: red from the $80 peak to the $17 low).
- L15c ridges tinted by activity like AG (cyan → green → yellow → orange): busy strikes read warm.
- L14 "V4 view" renamed Tetris ("Tetris · 3-D" / "2-D heatmap"); the AG block view replaces it once it matches.

## v0.13.0 — 2026-10-20 · ridges debug round (L7–L9, L11–L13, L10d)
- L7 click-to-pin: a clickable strike strip beside the 3-D ridges (3-D clicks don't reach Streamlit —
  tested) — click a strike bar = that strike's call AND put in the pane (C+P), click a ⚡ star = that
  contract; click a row in the ⚡ Spikes table = that contract; "↺ auto" returns to the strongest spike.
- L8 spike detection on TOTAL volume by default (single-leg is a toggle in ⚡ spike filter).
- L9 direction colours everywhere: calls sold / puts bought = red (labels light pink), calls bought /
  puts sold = green (labels light green), mid = grey; pinned ridge amber; Spikes table gets ▲/▼ column.
- L12 spikes are the ridge itself peaking up and back down (no poles); top-N bold, the rest lower/thinner.
- L11 right margin after now (min 60 min, 25 % of window) on ridges and pane; edge labels flip left and
  stack; price path clipped to the strike grid; overnight and RTH ridges scaled separately; bold top-N
  chosen per session part; early-session window extends backward, never into the future.
- L13 "📦 Today's data" expander: zip of prints (with spreadLeg), chain snapshots, OI log, spot, /ES,
  SPX, 5-min option candles — for offline analysis.
- L10d V4 surface: decay projection capped at 60 min; spot path clipped to the surface; strike ticks.

## v0.12.0 — 2026-10-20 · AG-style ridges (L6)
- AG-REV V5 ridges redrawn to match the AG reference (tuned on the real 19→20 Oct overnight tape,
  7675P 05:13 ET = AG's 04:13 CT):
  · quiet ridges — minute volume vs the window's busiest minutes (p99), 3-min smoothing, kept low
    in the box, so routine flow sits near the floor; nothing draws outside the box
  · spikes are their own marks: a vertical line, tallest = strongest (premium × z); the top 1/3/5
    are bold red with a label (same-minute legs share one label), the rest thin and faint
  · pin: "auto" = the strongest spike in the window (default), or any contract; its ridge is red
  · contract pane under the ridges: "Oct 20 7,675 P $19.70 Δ-0.51 · vol 1,109 · ⚡ 2 spikes",
    option price (last trade per minute, stepped), spike stretch magenta with a dotted marker and
    label (size, side, premium, z), session-low dashed, per-minute volume bars
  · window: 2h / 4h (default) / 8h / session, ending now or at the replay frame; AG-like camera
- 2-D ridges unchanged (2D toggle). RidgeEachSide default 12 → 9 (≈19 ridges, AG-like density).

## v0.11.1 — 2026-10-19 · memory fix (14:37 crash)
- Root cause of the Mon 19 Oct 14:37 ET crash (process killed, no traceback = out of memory):
  two charts drew ONE POINT PER PRINT — TASTIER "Imbalance · CVD" and AG-REV diagnostics
  "Bullish premium / CVD". On a full day (~600k prints) plotly deep-copied and serialised
  ~1M datetimes per chart: +1.3 GB per render and 60–100 s per page, per open browser.
  Both now plot one point per minute. Measured on a scaled full day (626k prints, 533k chain
  rows): TASTIER 97 s → 8 s, AG-REV 74 s → 7 s; resident memory steady at ~650–770 MB across
  repeated renders.
- Charm per snapshot row vectorised (was a Python loop over every stored row; identical results).
- Safety net: freed memory is handed back to the OS after every page run and every snapshot;
  above 1,800 MB the recorder thins chain snapshots older than 90 min to one per 5 min (logged in
  diagnostics as "mem-guard"). Memory (current and peak) shown in the status bar and diagnostics.

## v0.11.0 — 2026-10-19 · Book layout, loading bar, Interval fit, DT legend
- L5 Book: the key-levels card sits on top (compact); the download-card button is gone.
  Charts 1 (MM-inferred) and 2 (clean-B single-leg) are the default, side by side at half
  width. Picking a third lens puts all three across the full width. The spot path (white,
  session time on top) is now drawn on every chart.
- L1 Loading bar: a progress bar with a stage label ("loading chain → dealer signs →
  chart 1 → …", elapsed seconds) at the top of the open tab while it computes, on every
  tab and replay step.
- L3 Interval: y-axis fits the top-N strikes plus the price path (no more 7380–7930 for
  activity at 7600–7740); the time axis ends at the latest data + 20 min instead of empty
  future to 16:00. Toggles: "Fit y", "End at now".
- L4 DT: legend on the chart and above it (blue/magenta · filled = extending, hollow =
  receding · no prior position → always filled). New "From 20:15 (GTH)" (default on with
  🌙 GTH): the dot is the book as of 20:15 and overnight prints count as moves; off = 09:30
  only. DT y-axis fits price + events; prints now respect the replay frame.

## v0.10.2 — 2026-10-19 · overnight price fixes
- Fix: false price jump at startup (e.g. 7660 → 7710 at 03:10). On connect DXLink re-sends
  the last SPX trade (Friday's close overnight), which the recorder stamped with the
  receipt time and so treated as live for 60 s. It now uses the trade's own time, so a stale
  print hands over to synthetic parity at once.
- Stale SPX spot rows already stored overnight are dropped from every chart, since the index
  doesn't print outside 09:30–16:15.
- Overnight price backfill from /ES: the recorder streams front-month /ES 1-minute candles
  (4 days, extended hours). Any session minute without an SPX candle or recorded spot (e.g.
  overnight before a restart) gets the /ES bar shifted onto SPX by the measured ES − SPX
  basis (median of the latest 60 overlapping minutes).
  - Result: the overnight path runs from 20:15 even after a reboot.
  - It feeds the price chart, AG-REV V1/V2 (and its overnight Q5/W rules), the ridges and
    surface spot line, Terrain/GEX³ candles, Interval and DT.
  - Each bar's source is recorded (candle / spot / es).
- THE STRIP VIX chip uses VIX from its 03:15 ET start instead of showing n/a until 09:30.

## v0.10.1 — 2026-10-19 · spike filter tuned on real tape
- Tested on a real tastytrade sample (Colab dump at 02:31 ET):
  - 125k SPXW prints, Fri 09:30 → Mon 02:31.
  - Overnight prints DO stream: 27.8k since Sunday 20:15 ET, ~200 per 90 s live, median
    size 1 lot. Bid/ask is on every print, and aggressorSide is set on 99.9 %.
- Spike defaults are now per session. All-legs z3 / top 5 % / 50 lots gave 486 "spikes" on
  Friday, which is noise.
  - RTH: z ≥ 4 · top 2 % · ≥ 200 lots · ≥ $50k → 12 events on Friday.
  - GTH: z ≥ 3 · top 5 % · ≥ 50 lots · ≥ $25k → 30 overnight (≈ 1 per 12 min).
  - Overnight hits include 22:31 7750C 249 lots sold — the contract in your reference shot.
- Single-leg tape is the default for spikes. Package legs printed without the spreadLeg
  flag (same minute, same size) merge into one event with a "package" column, e.g.
  7540P + 7550P 5,301 lots.
- The spike popover now has separate GTH and RTH settings.
- Ridges still draw ALL volume; only spike detection uses single-leg.

## v0.10.0 — 2026-10-19 · overnight session (GTH), spike filter, 3-D AG-REV views
- 🌙 GTH toggle in the universal bar (on by default):
  - Every screen spans the overnight session (Cboe GTH, from 20:15 ET the evening
    before) through 16:00, with a dashed line at the 09:30 open.
  - Overnight bars come from the recorder's 5-s spot (synthetic parity, since the index
    doesn't print). From 20:15 the next session is live.
  - Off = 09:30–16:00 only, as before.
- Covered: AG-REV buckets/signals and all panels, TASTIER price + overlays, VS3D Book spot
  path, Terrain/GEX³ axes, Interval, DT. The 09:30 anchors (true open, opening straddle,
  09:35 lock, strip) are unchanged.
- Interval bursts use separate overnight and RTH baselines.
- ⚡ Spike filter (core/spikes.py) — a minute counts only when all three hold:
  - (1) Unusual for that contract: robust z ≥ 3 on its own trailing 60 minutes, using
    median/MAD with the current minute excluded.
  - (2) Big for the chain: top 5 % of all contracts that minute.
  - (3) Size floor: ≥ 50 contracts and ≥ $25k premium.
  - Overnight and RTH baselines are separate; RTH restarts at 09:30 with a 15-min warm-up,
    during which only (2)+(3) fire.
  - Every threshold is adjustable in the "⚡ spike filter" popover.
- AG-REV V5 ridges are now one interactive, rotatable Plotly view:
  - One line per strike, height = contracts/min, colour low → high.
  - White SPX path, ⚡ spikes ringed in magenta.
  - Toolbar: C / P / C+P · 3D / 2D · trim · heat · cap (250c–10kc, default 4kc).
  - "Pin a contract" highlights one line in orange; spike contracts are listed first,
    latest first.
  - A ⚡ Spikes table alongside shows time, contract, size, premium, bought/sold and z.
- AG-REV V4: rotatable 3-D surface of cumulative dealer γ from flow, with the spot path and
  the decay projection. The 2-D heatmap is still available as an option.
- Real-data sample script for Colab: trishula_sample_dump.py (not part of the app).

## v0.9.0 — 2026-10-19 · AG-REV signals (SPXFlow v2.10) + TASTIER overlays
- AG-REV now runs the SPXFlow v2.10 rules from your workbook (SPXFlow.bas), line for line,
  on the tastytrade tape:
  - Q1 call sweep · Q3 put sweep: net premium bought ≥ MinPrem and z ≥ ZThresh.
  - Q2 puts sold into a dip · Q4 calls sold into strength (close vs the 30-bucket mean).
  - Q5 divergence: new low with a higher low in cumulative delta-notional (or the mirror).
  - W: price within WallTol of the max-OI put/call wall with flow in the bounce direction.
  - Z-scores over the last 30 buckets (10 needed), no signals in the first SkipOpenMin minutes,
    per-family cooldown, target/stop harness, and the stats line per family.
- Better inputs than the workbook: each print's own bid/ask and aggressorSide replace
  the RTD 5-second volume-delta guess. The formulas for prem, dn and bull are unchanged.
- Workbook dashboard as panels:
  - V1 cumulative delta-notional ±$B with close, walls and markers
  - V2 SPX candles with walls and signal markers
  - V3 strike profile: today's flow (dealer γ) vs naive OI GEX
  - V4 positioning heatmap, with the decay projection to the right of now
  - V5 call/put volume ridges
- Every Config setting is editable in-app (BucketMin, ZThresh, MinPrem, WallTol, cooldown,
  targets/stops), and the whole day re-scores immediately (the workbook's REPLAY button).
- There is no "B" signal in v2.10, so none is built.
- TASTIER overlays on the price panel (my definitions; your screenshots named them without formulas):
  - VELOCITY: EMA₃ of signed delta-notional per minute ($M/min), with |z| ≥ 2 spikes flagged.
  - ABSORB: an extreme-flow minute (|z| ≥ 2) where price barely moves (≤ 0.25 × ATR₁₄).
    ▼ means buyers were absorbed, ▲ means sellers were absorbed.
  - PRESSURE: rolling 15-min delta-notional ÷ session σ, clipped ±3, drawn as a green/red tint.
  - VRVP: volume profile from SPY 1-minute volume mapped to SPX points, with POC, VAH and VAL.
    The recorder now streams SPY 1-minute candles.

## v0.8.0 — 2026-10-19 · VS3D Interval, Market Read, DT (ports of vs3dgbt 0.9.79)
- Interval (bubbles): cumulative GEX and DEX of traded volume per strike in 5-minute buckets
  (calls +, puts −, or dealer dsign), single-leg premium bursts (log-z), and top-N strikes,
  with the SPX path drawn over them.
- Market Read: vs3dgbt's read_verdict engine.
  - Verdict banner (lean, size, wait or stand down) with confidence and reasons.
  - Straddle decay check, fishbone, γ regime, charm clock and gate, absorption up/down.
  - PIN/FLIP/walls/K*, the KEY LEVELS card, and the legacy signals board.
  - Trailing inputs are rebuilt from snapshots, so a replayed frame reads exactly as it
    did live.
- DT (repositioning tape): marks the minute a strike's net paper crosses a new band versus
  its yesterday-final dot. It replays minute by minute, so the event log is the same live
  or in replay.

## v0.7.0 — 2026-10-18 · universal player + refresh, Book layout (R1–R4)
- Universal bar above the three tabs:
  - Refresh slider, 1–10 min (default 5): how often the screens redraw while LIVE.
    Chain snapshots are still recorded every 60 s.
  - Replay player: ⏮ first frame · ▶ play · ⏸ pause (pausing while live freezes on the
    latest frame) · ⏹ LIVE (back to live data) · speed 1 / 2 / 3 s per frame · a
    scrubber over every stored snapshot · a mode badge (🔴 LIVE / ⏸ ▶ REPLAY hh:mm).
- Every tab and VS3D sub-tab replays. Each frame uses only data up to that moment: the
  chain snapshot, prints, candles, spot, dealer signs and VIX. The 09:35 lock and the
  peak-γ line only show once they had formed.
- Tabs are lazy: only the open tab and sub-tab compute, so playback and refresh are faster.
- Book layout:
  - Charts side by side: 1 FLOW-SIGNED (MM-inferred, with the spot path) · 2 CLEAN-B
    (single-leg tape) · 3 your pick of Net flow, Naive or none.
  - The KEY LEVELS card and THE STRIP are always on, beside and above the charts.
  - Removed: Total/Calls/Puts, the Bars radio and the Book-signing radio.
  - One compact control row: third chart · zoom ➕➖↔ · dots · straddle · Δ ladder · spot path.
- The old VS3D-only player and its 15/30/60 s live layer are gone (replaced by the universal bar).
- Images use st.image again, so they scale with browser zoom. The card has a download button.

## v0.6.0 — 2026-10-18 · VS3D GEX³ (matplotlib port of vs3dgbt 0.9.79)
- GEX³ is vs3dgbt's three-lens NIFTY GEX model on tastytrade data:
  - P1 CONVENTION (naive, assumed dealer sign)
  - P2 FLOW-SIGNED (tape dsign)
  - P3 Δ-OI overnight or live volume, with its own sign choice and dotted P2 comparison
    curves
- Each panel: candles across RTH, right-anchored γ density (buy green / sell red fills
  and lines, TOTAL orange, |net| white, ▲▼ peaks, HHI◆ top-5 with shares), and
  positive/negative γ fields.
- Levels per panel: flip, CW, PW, PIN, CEIL, FLOOR, UHW/DHW (·T/·N/·W), with
  de-collided labels.
- Also per panel: a scorecard (pin raw → HHI-adjusted, floor/ceil, HHI regime, local γ)
  and the γ dial. The locked 09:35 ladder is drawn faint on every panel.
- Colour-coded readout per lens, plus a model-detail expander (gravity trio, pin
  scoring, HHI top-5, dials).
- Controls: panel height 5.5, ± % room 0.5, density width 0.45, panel-3 weight and sign.
  Y auto-fits to where the mass and candles are.
- ΔOI: the recorder now logs settled OI per day (last 6 days, saved with the flush).
  Panel 3 Δ-OI = today − prior session. Until one prior session is recorded, it falls
  back to live volume and says so.
- VS3D no longer uses Plotly. Book, Terrain and GEX³ are all matplotlib ports.

## v0.5.0 — 2026-10-18 · VS3D Terrain (matplotlib port of vs3dgbt 0.9.79)
- Terrain (gradient) is vs3dgbt's terrain_grid + _render_terrain, drawn on tastytrade data:
  - Forward-projected field, 170 prices × 84 times across 09:30–16:00. Each expiry decays
    on its own clock, and the field covers every aggregated expiry.
  - Greeks: Delta Change · Gamma · Charm · Gamma |Γ| (heaviness) · Gamma Decay (color).
  - Field mode: Aggregate or Per-strike ladder.
  - Weighting: OI+Volume, OI, Volume, or Vol-else-OI.
  - Range: Manual fixed cap (Calibrate / Reset, with the cap autopilot at 1.5× / 0.4×),
    Percentile, or StdDev.
  - Intensity: Power 0.40 · Sqrt · Arcsinh. Opacity 0.38, saturation, and zoom.
  - Contours (zero boundary plus orange ridges/troughs) and negative-γ pockets (top N).
  - Straddle bounds, Pinak levels (PIN/FLIP/CW/PW/K*), vol adjust ±1%, and simulated
    gamma/charm.
  - Side profile at the current time column, peak-γ magenta rail from the stored
    snapshots, and the minis/$1 readout.
  - Stacked CHARM panel with the charm flip and minis/5min.
- Signed field (new, default ON): per-leg dealer dsign drives the field, the same signs as
  the Book (unseeded legs = naive × 0.2). Turn it OFF to get vs3dgbt's naive calls+/puts−.
- Off-hours and weekends: the field is projected across the next session (e.g. Monday
  09:30–16:00) from the current chain.
- VS3D (combined): Book × spot | the canonical Gamma + Charm pair (overlay-free), as in vs3dgbt.
- Fix: the KEY LEVELS card and some charts showed as broken images (their media files
  were dropped on fragment reruns). VS3D images are now embedded inline.
- Terrain renders are cached per frame and settings (8 entries), so ticks between
  snapshots are cheap.
- New dependency: scipy.

## v0.4.0 — 2026-10-18 · VS3D Book + combined (matplotlib port of vs3dgbt 0.9.79)
- Book is now vs3dgbt's own book_figure (matplotlib), drawn on tastytrade data:
  - FLOW-SIGNED (green/red): inferred dealer sign × OI contracts, opacity = confidence;
    unseeded legs keep the naive sign, faded.
  - CLEAN-B (blue/magenta): net single-leg paper per strike, dealer view (bar = seed + live).
  - NET FLOW (blue/yellow): customer net bought/sold paper, participant view.
  - Bars: MM-inferred or Naive (calls+/puts−, with Total/Calls/Puts).
- Dots show yesterday-final (seed) from the seed store, so they are there on every boot.
  Exhausted-extent sticks are drawn where a bar has shrunk from its dot.
- Also on the Book: 1× ATM straddle lines, 10-point price ticks, zoom ➕/➖/↔, and the
  spot-path overlay with session time along the top.
- THE METHOD card levels:
  - PREVIEW before 09:35, and on weekends for the next session.
  - LOCKED at the first snapshot ≥ 09:35 ET. The lock is shared by all viewers and
    recomputed from the stored snapshot after a reboot. Labels show ·TESTED/·CROSSED.
  - Labels are de-collided.
- Reference = true 09:30 open (from 1-minute SPX candles), or a premarket anchor frozen
  once per day. S0 = opening straddle (ATM mid at the first ≥ 09:30 snapshot).
- Δ ladder (orange) compares the current book with the 09:30 book; a ⚡ badge shows
  when a side's net sign flips.
- KEY LEVELS card image (Dan-slide format; right-click → save).
- THE STRIP: γ dial · FUEL · CHARM · straddle gate · VIX · window ▶ PLAY. History comes
  from the stored snapshots, and VIX 5-minute candles are now recorded.
- VS3D (combined): Book × spot | terrain, side by side (1.0 : 1.5).
- Global VS3D controls:
  - expiries to aggregate (1–5)
  - live price layer: 15 / 30 / 60 s / off
  - LIVE or Snapshot frame with a scrubber
  - playback ⏮ ▶ ⏸ ⏹ at 1 / 2 / 4 s
- Chain snapshots are stored as compact DataFrame chunks (less memory), and dsign is
  stored for every subscribed expiry.
- TASTIER CVD: replayed seed prints use the leg's current delta as a stand-in.
- Terrain is still the interim heatmap (port in v0.5.0). GEX³ is panel 1 (port in v0.6.0).

## v0.3.0 — 2026-10-18 · signed data foundation
- Seed: every start replays TimeAndSale from the prior session 09:30 ET (prior RTH +
  overnight) for the 0DTE and 1DTE grids and for every Weekly/Monthly/Other expiry you
  open. tastytrade returns the last 1,000 prints per contract; the status bar shows
  "🧬 seeding…" then "🧬 seed ✓".
- Candle seed: 5-minute option candles (bidVolume/askVolume, not capped) fill the
  early part of the session the 1,000-print replay can't reach. Requests go out in
  batches of 90, under tastytrade's 100-candle limit. Candles count only for bars that
  end before a contract's first replayed print, so no volume is counted twice.
- Gap backfill: each reconnect re-asks for history, and duplicates are dropped by
  (symbol, index, type).
- Dealer sign (vs3dgbt formula): dsign = clip(−(net_seed + net_live)/(tot_seed + tot_live), −1, 1)
  per contract. Contracts with no evidence keep the naive sign at weight 0.2.
  Chain snapshots now store dsign.
- MID prints are signed by aggressorSide (your decision; differs from GBT/vs3dgbt).
- Events marked REMOVE (eventFlags 0x02) are skipped.
- Replayed prints carry their 1-minute SPX candle spot and no live greeks
  (src = replay / live column).
- Later expiries are signed on the current session: the seed is the prior session's
  flow, and live is today's.
- VS3D: Book lens control, Flow-signed (default) or Naive; bar opacity shows confidence.
  Seed coverage caption shows legs seeded, legs candle-filled and how far back the
  replay reaches.
- AG-REV: seed coverage caption, plus a CVD chart with replayed seed (grey) and live
  prints (blue).
- TASTIER: the CVD panel now includes the replayed seed prints.
- Memory: prints are stored as compact DataFrame chunks with hashed dedupe keys.
- Correction: in dxFeed, eventFlags 0x04 is SNAPSHOT_BEGIN, not SNAPSHOT_END.
  Replay completion is now detected by 6 s of quiet.

## v0.2.1 — 2026-10-18
- Fix: expiry bar no longer sticks on "loading…" after a reboot — the page reruns once
  the recorder is ready; Weekly/Monthly/Other show "loading…" until their chain arrives,
  then "ready ✓" (checked every 3 s).
- Status line: "recording 0DTE mm/dd · 1DTE mm/dd (seed)".
- Version guard: each app version runs its own recorder; a newer upload stops the older
  one. Upgrading from ≤ v0.2.0 shows a one-time "Reboot app" banner.
- Quiet shutdown: no more "Task was destroyed but it is pending" / "aclose()" log spam.
- Tabs look like tabs: bordered, faint dividers, active tab with a blue top border,
  hover highlight; top-level tabs larger than sub-tabs.

## v0.2.0 — 2026-10-18
- Common control bar on top of every tab: expiry quick-pick (0DTE / 1DTE / Weekly / Monthly /
  Other = any listed expiry) and strike window (± N strikes or ± % move).
- Any expiry can be viewed: the recorder subscribes a picked weekly/monthly on demand (±60 strikes).
- Recorder grids widened to ±60 strikes; SPX 1-minute candles (4 days of history) recorded.
- TASTIER: full 8-panel layout always drawn (empty frames say what they wait for): header
  cards, SPX price + MA9/MA21 + per-bar delta, GEX by strike, cumulative gamma, GEX regime,
  imbalance (CVD), GEX flow top 7, gamma surface, charm surface.
- VS3D: VS3D combined, Book (positions by strike, e-minis per $1, naive calls+/puts−, ATM
  straddle bands, Total/Calls/Puts) and Terrain (gradient) live on naive signing, as vs3dgbt
  showed before its flow seed; GEX³ panel 1 (convention).

## v0.1.4 — 2026-10-18
- Fix: "Fatal streamer error: Your authentication token has expired". The DXLink
  quote token expires after 24 h; the recorder now opens a fresh session every 6 h
  (new access token + new quote token) instead of holding one connection for days,
  and reconnects immediately (no back-off) if a token ever expires anyway.
- Diagnostics show token_refreshes and auto_recovered counts.

## v0.1.3 — 2026-10-17
- Chain snapshots are recorded on weekends and overnight gaps too (every 5 min when the
  market is closed, every 60 s in the trading window), so the next session's chain is
  always on screen and in the recorded history.

## v0.1.2 — 2026-10-17
- Fix: tabs stayed on "Recorder is starting" forever. Each tab and the diagnostics panel
  now re-check the recorder on their own refresh (TASTIER 30 s, AG-REV 15 s, diagnostics 30 s).
- Note: chain snapshots (chain rows) are written only inside the recording window
  (Sun 19:00 ET to Fri 16:20 ET); on a Saturday the count stays 0 by design.

## v0.1.1 — 2026-10-17
- Storage simplified: one repo, one app. Recorded data is saved to the app container's
  disk every 5 min and reloaded after page reloads (vs3dgbt-style day state).
  No GitHub token needed.
- Version shown on every screen and in recorder status for debugging.
- Deploy guide kept outside the repo (it holds the secrets).

## v0.1.0 — 2026-10-17
- App shell: black theme, tabs TASTIER / AG-REV / VS3D, recorder status bar.
- Recorder thread: tastytrade DXLink, SPX 0DTE + 1DTE grids (ATM ±40 strikes),
  TimeAndSale tape with five-bucket classification, quotes, greeks, OI, spot, 60 s chain snapshots.
- TASTIER v0: header cards, GEX by strike, cumulative net gamma, gamma flip, walls.
- AG-REV v0: live classified tape, gate checks (quote-on-print, aggressorSide, spread-leg).
- VS3D: sub-tab bar (port queued).
