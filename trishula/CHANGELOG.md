# TRISHULA changelog

Semantic versioning: MAJOR.MINOR.PATCH. The running version is shown in the app's
status bar, every tab footer, and the Recorder diagnostics panel.

## v0.42.0 — 2026-11-24 · OrderFlow: "drop mid" toggle · fade / follow at highs & lows (from the "zero" write-up)
- keep mid / drop mid: ignore prints traded strictly inside the bid/ask (34–43 % of SPX prints) in the map, footprint
  and unusual options, SPX / ES / SPY.
- Toggle "fade / follow at highs & lows" (off by default): at each new session high / low after 10:00, the last 15 min
  of single-leg 0DTE money leaning AGAINST it → FADE, pushing THROUGH it → FOLLOW (cut = 0.5 × the lean's own
  standard deviation so far today). Scored on the last 15 finished events of each kind from the saved lean days +
  today, SPX 30 min later → verdict FADE / FOLLOW / SIT OUT (needs ≥ 5 events, average > 0, ≥ 55 % right).
  Today's events marked on the SPX candles (yellow = fade, cyan = follow; hover = lean and 30-min result).
- First look, 10 saved days (5–23 Nov): fade 18 events 39 % right −4.1 pts · follow 36 events 56 % +2.4; the
  walk-forward verdict would have traded FOLLOW on 4 days for −49 pts. Collecting; tune at ~20 days.

## v0.41.2 — 2026-11-24 · memory: unusual options no longer keeps a copy of the tape · 15:30 safety copy
- 23 Nov: memory 1.27 GB at 12:00 → 2.12 GB by the 13:16 reconnect (long-dated book skipped) → 2.28 GB peak by 14:00,
  130 memory thins; no 16:05 / 16:11 attempt in the ship log → the app was most likely killed for memory before the close.
- Unusual options kept a full copy of the day's prints per market on the recorder (v0.41.0). Now it builds it only
  while computing and caches just the flagged orders (a few hundred rows).
- ES / SPY prints measured at ~33 MB on 23 Nov (SPY 503k, ES 20k rows) — not the cause; left as they are.
- New 15:30 ET safety copy (12:00 · 14:00 · 15:30 · 16:05 close · 16:11 re-send); intraday copies still deleted
  once the close copy is up.

## SPX BB v0.48.3 — 2026-11-23 · Disconnect pane under the width / straddle chart
- width ÷ straddle (how many straddles out the 0.05 bids sit), z-score vs its own rolling 30 min, bars with ±2 lines:
  magenta z > 2 = wings rich vs ATM (edges lagging a falling straddle) · blue z < −2 = ATM rich vs wings.
- Title shows today's lag: the shift (0–15 min) where 1-min changes of width and straddle line up best
  (20 Nov ≈ 2 min, 23 Nov ≈ 1 min, both corr 0.19 — the edges move in steps more than they lag).

## v0.41.1 — 2026-11-23 · Terrain candles blue up / yellow down (were white / orange)

## SPX BB v0.48.2 — 2026-11-23 · "higher of two" fixed
- "higher of two" no longer runs its own model fitted on max(open, close) history (it showed a third set of curves and
  SAFEST). It now shows whichever of the two runs uses the higher VIX TODAY, whole: curves, tables, SAFEST. 23 Nov:
  close 35.89 > open 31.38 → identical to prior close (SAFEST 6300 / 6315). Run line says which one it picked.
- Backtest 2017→ (put misses at 5 / 1 / 0.5 %): pick-higher 4.26 / 0.93 / 0.44 vs prior close 3.94 / 0.88 / 0.48,
  VIX open 4.71 / 1.05 / 0.64, old fitted-max 4.55 / 1.05 / 0.60; VIX-up ≥10 % days 3.80 (prior close 8.86);
  VIX-down ≥10 % days 0 at 1 % (= prior close). One fewer fit per press.

## SPX BB v0.48.1 — 2026-11-23 · Run model fits all three VIX versions; toggle only switches the display
- One press of Run model (0DTE) fits prior close, VIX open and higher of two together; the VIX toggle switches curves,
  tables, best ratio, SAFEST and the run line instantly — no rerun.
- SAFEST / 2nd SAFEST follow the toggle: prior close = days with closing VIX ≤ today's close rounded up (as before);
  VIX open = days whose VIX open was ≤ today's exact open; higher of two = days judged by the higher of the two, cut
  at today's exact higher value. 23 Nov: puts 6300 / 6315 → 6315 / 6425 on VIX open.
- Before today's VIX open exists (03:15 ET) the VIX open / higher choices show prior close with a warning.

## SPX BB v0.48.0 — 2026-11-23 · 0DTE model: VIX toggle (prior close / VIX open / higher of two)
- Next to Run model (0DTE only): which VIX the 0DTE fit uses. prior close = as before (default). VIX open = that
  day's Yahoo VIX open (the 03:15 ET overnight value, fixed for the day), history fitted on the same input. higher of
  two = the cautious one. Before today's VIX open exists it falls back to prior close and says so.
- Run line shows the VIX used and, when not prior close, the prior close next to it. SAFEST / 2nd SAFEST unchanged
  (still bucketed on the closing VIX). 1DTE unchanged.
- Backtest 2017→ (RESEARCH_LOG §17): no real difference on average; when VIX jumps ≥10 % overnight the prior-close
  fit is too tight (8.9 % misses at its 5 % put strike) and VIX open fixes it (3.8 %); when VIX falls ≥10 % overnight
  (15 days) VIX open moves puts closer (1 miss at its 1 % strike vs 0). Higher of two sits between.

## v0.41.0 — 2026-11-20 · OrderFlow: unusual options (4 toggles + table), SPX / ES / SPY
- ORDERS, not prints: prints on the same contract, same side, same second = one order (a 500-lot fills as 50–70
  prints). Size that matters = delta notional (|Δ| × contracts × multiplier × underlying, Δ from the order's price).
  Uses the single-leg / all toggle (ES feed has no spread-leg flag).
- Toggles (each on its own, or together; nothing changes when all are off), each showing only the top 5 / 10 / 20:
  1 big orders — biggest orders of the day by delta notional (top-N adapts by itself, no fixed size).
  2 bursts — a strike trading > 2 / 3 / 5 / 10 × its own rolling 15 / 30 / 60-min median minute (and above the
    market's typical busy strike-minute); ranked by that multiple.
  3 paying up — orders at-or-through (or through-only) the quote; ranked by delta notional.
  4 new positions — volume today reaching 1 / 1.5 / 2 × prior-close OI (OI ≥ 50 / 100 / 500 / 1,000); largest OI first.
- Marks on the candles (and footprint) at the underlying price and time, labelled ("7375C sold 571 · $305k"):
  blue = bullish (calls bought / puts sold), magenta = bearish; size = contracts; shape per flag, star = 2+ flags.
- Table: time, strike, C/P, size, price, bought/sold, read, premium $, delta $M, vs spot, flags hit; top 20 / 50 / 100
  by delta $ / premium / size / time; any flag or 2+ flags; click a row → yellow ring on the chart.
- Recorder: ES / SPY prints keep their contract symbol; open interest subscribed for the ES / SPY strikes (needs restart).
- 18 Nov SPX top 10: 12:23 7375C sold 571 ($305k) 10 min before the 12:33 high; 13:11 7290P + 7315P bought $904k near
  the 7315 low (price then rallied).

## v0.40.0 — 2026-11-20 · OrderFlow: ES options + SPY options (SPX / ES / SPY / 3 stacked)
- Recorder also streams the nearest-expiry ES options (strikes ±4.5 % of ES) and SPY options (±4 % of SPY): every
  print (trade replay from 09:30 on connect), with aggressor side, spread-leg flag and the underlying price at the print.
- OrderFlow tab: market toggle SPX / ES / SPY / 3 stacked. Same candles / footprint views, same single-leg / all toggle,
  RTH only. ES and SPY are drawn on their own price (ES 2-pt rows, SPY 0.2-pt rows, candles from the underlying).
- Delta for ES / SPY prints from each trade's own price (implied vol → Black-Scholes); size in SPX-equivalent delta
  (delta × size × multiplier × underlying ÷ SPX) so the three charts are on one scale.
- ES feed carries no spread-leg flag (checked 20 Nov): single-leg = all for ES, said in the ES caption.
- Day zip adds x_es_prints.parquet and x_spy_prints.parquet.

## v0.39.0 — 2026-11-20 · VS3D → OrderFlow tab (options delta map / footprint)
- New sub-tab next to Lean. Every 0DTE print → customer delta (aggressor × option delta × size × 100) placed at the SPX
  price where it traded; per minute × 2-pt rows, incremental on the print store (core/orderflow.py).
- View toggle: candles (default) = 5-min × 2-pt delta map under SPX candles + cumulative options delta vs SPX;
  footprint = 15-min bars, each cell "sold × bought" (k Δ), coloured by net, bar total under each bar (last 3h / full day).
- prints toggle single-leg (default) / all. Colours as Lean: blue = deltas bought, magenta = sold.
- 18 Nov check: tracks the bar's move (single-leg 5-min corr +0.66 vs all +0.60), does not predict the next bar.

## v0.38.0 — 2026-11-18 · AG-REV ridges: "AG tilt" view
- New view in the V5 ridges toolbar, built against AG's 17 Nov screenshot: tilted perspective (far strikes small at the
  top, near strikes wide at the bottom), SPX through the strikes it trades at, and a ridge only rises for minutes
  above 2× that strike's own 30-min median (steady ATM churn stays flat). Pinned strike red, 3 busiest yellow, next 5
  green, rest cyan. Uses the Legs control (All / Single / Multi). Strikes ±120 around spot (+ price path ± 40).

## v0.37.1 — 2026-11-18 · close copy sent twice (16:05 and 16:11)
- A shipper left over from the previous version (still running after an update, with a frozen recorder) could upload a
  stale ..._close.zip at 16:05. The current recorder now re-sends the close copy at 16:11, so the final file is fresh.

## v0.37.0 — 2026-11-18 · day data saved to GitHub three times a day
- 17 Nov's dump never reached GitHub (container restarted, error lost). Now AutoShip sends safety copies at 12:00 and
  14:00 ET plus the close copy at 16:05 (each retried every minute for 14 min); once the close copy is up the day's
  intraday copies are deleted. Every attempt (ok / error) is logged to state/ship_log.json on the state branch.

## SPX BB app v0.47.2 — 2026-11-17 · put / call model tables always 4 rows (charts line up)
- "★ Best ratio" (and "Furthest") rows always shown; when nothing qualifies: "none · all bids inside the 50¢ zone".

## SPX BB app v0.47.1 — 2026-11-17 · fix: SPX line / title / chart range back on live spot
- v0.47.0 wrongly moved the white SPX line, the chart title and the chart's start to today's open. Back as before
  (live spot at the press). Only the solid curve is measured from today's open; dotted from yesterday's close.

## SPX BB app v0.47.0 — 2026-11-17 · 0DTE model: today-open and yesterday-close curves
- 0DTE model chart: solid yellow "today open" = the model's 0DTE fit (open → low / high) measured from today's 09:30
  open (premarket: current spot, moved once to the real open after 09:30, same %); dotted yellow "yesterday close" =
  the model's close → next-day low / high fit on history to yesterday, measured from yesterday's close; red dotted
  cautious (95 %) for the solid line. Ratios / ★ / table colours stay on the solid line. Model maths unchanged.
- 1DTE unchanged (close-based, spot at the press). Spot line labelled OPEN / PREMKT.

## SPX BB app v0.46.0 — 2026-11-17 · compact: whole page fits at 80 % zoom
- Base font 14 px, tighter spacing / captions; model charts 330 px, live charts 470 px; slimmer spot box.
- sold C / sold P / ask alert on one row; long notes (SAFEST definition, buffer / MAE) behind ⓘ.

## SPX BB app v0.45.0 — 2026-11-17 · lighter inputs, taller charts, straddle from 09:30
- Input fields: lighter fill + visible border (hover / focus brighter); sold C blue edge, sold P magenta edge; their
  labels bigger. Live charts 640 px tall (fill down to the bottom of the middle panel).
- ATM straddle backfilled on every load from tastytrade 1-minute trade candles (0DTE strikes across today's SPX range
  ± 30): the line runs from 09:30; live mid readings take priority where recorded.

## SPX BB app v0.44.0 — 2026-11-17 · MAE on your sold strikes
- Sold-strike table: MAE = worst price against you today — highest TRADE from tastytrade 1-minute candles (from 09:30;
  1DTE sold after the close: from 15:00) or highest ASK seen live in RTH, e.g. "0.25 @10:54 T".
- Feed subscribes 1-minute candles only for the sold strikes; saved with the edge history, cleared with the expiry.

## SPX BB app v0.43.0 — 2026-11-17 · ATM straddle overlay on the width chart
- Tracker records the ATM straddle (call mid + put mid at the strike nearest spot, two-sided quotes) once a minute per
  expiry, saved with the edge history (survives restarts).
- Width chart: width in pts on the right axis (as before) + ATM straddle in $ on the left axis, scaled so both lines
  start at the same height (09:30, or the straddle's first reading) — compare ATM vs far-OTM decay paths.

## SPX BB app v0.42.0 — 2026-11-17 · no commas in strikes, bigger labels, 0.5 % buffer
- Strikes without thousands commas everywhere in SPX BB (tables, chart labels, hovers, Telegram). SPX prices keep theirs.
- Model chart labels bigger: SOLD 15, SAFEST / 2nd SAFEST / SPX 13.
- Model chart x-range: spot → furthest of (last live bid, edge, SAFEST, 2nd SAFEST, sold strike) + 0.5 % (was 1 %).

## SPX BB app v0.41.0 — 2026-11-17 · sold strikes: white lines + tied to their expiry
- Model charts: bold white SOLD line at your sold put / call; the chart widens to keep it in view.
- Live edge chart: sold lines white dotted (both sides).
- Each sold strike remembers the expiry you were viewing when you entered it and clears once that expiry ends —
  a 0DTE sale is gone next morning, a 1DTE sale after the close carries into the next day as the 0DTE.
  Sold-strike / ask alerts watch only that expiry.

## SPX BB app v0.40.1 — 2026-11-17 · refresh dropdown says what it is
- Shows "🔄 refresh 10 s" (5 / 30 / 60 s) and "⏸ PAUSED".

## SPX BB app v0.40.0 — 2026-11-17 · screen refresh selector, zoom kept
- VIEW box: screen refresh 5 s / 10 s (default) / 30 s / 60 s / ⏸ pause — redraws of the live charts + the model's
  live bids only; the tracker and Telegram alerts still check every 5 s.
- Charts keep your zoom / pan across refreshes (double-click resets). ALERTS caption: 0DTE 09:30–16:00.

## SPX BB app v0.39.0 — 2026-11-17 · charts show today's session only
- Both live charts: 09:30 ET → now (overnight / premarket: since the 21:00 roll; an expired expiry: its 09:30–16:00).
  The y-axis fits that window, so a 6850 → 6450 put-edge move fills the chart instead of a sliver. Display only.

## SPX BB app v0.38.0 — 2026-11-17 · every day starts clean (alerts were dead today)
- Bug: the jump-alert level ratcheted outward silently while alerts were off, so the 17 Nov expiry carried stray
  1DTE / overnight 0.05 bids (5800P, 7950C) into today's 0DTE → the 6960 → 6850 put edge move sent nothing.
- Now: outside its window the level COPIES the edge both ways; 0DTE window 09:30–16:00 ET weekdays, 1DTE 15:00–21:00.
  First alert counts from the edge when the window opens. Levels are never reloaded after a restart.
- Sold-strike and ask ≥ level warnings: once per DAY. View opens on 0DTE; saved view resets to 0DTE at 21:00.

## SPX BB app v0.37.0 — 2026-11-17 · edge model: live bids on frozen curves (TRISHULA stays v0.36.0)
- Run model fits once and FREEZES the expected-loss / cautious curves, SAFEST / 2nd SAFEST and the reference spot.
  Every 5 s after that the bid dots, ★ best ratio, furthest put/call and the ratio cells re-price from live bids against
  those frozen curves. Caption shows the run's spot + time and the live-bid time.
- The SPX BB app has its own version number (core/version.py BB_VERSION), so SPX BB-only pushes never restart
  TRISHULA's recorder mid-session.

## v0.36.0 — 2026-11-16 · SPX BB is its own app
- New entry file `spxbb.py`: a second Streamlit app (same repo, same secrets copied over, nothing new). Own slim
  tastytrade feed (`core/bbfeed.py`): SPX spot, bid/ask on every SPXW strike of the two SPX BB expiries (21:00 ET roll),
  SPX 1-min candles. Tracker, Telegram alerts, edge model, charts and controls unchanged. Password = APP_PASSWORD.
- TRISHULA: SPX BB tab, its tracker / alerts and the all-strikes quote subscription removed (the 5 s redraws, the 5 s
  scan and ~1,000+ extra quoted symbols no longer share TRISHULA's CPU).
- Tracker: stop() so a newer version's tracker replaces the old one without double alerts.
- Settings + edge history stay on the trishula-state branch, so they carry over.

## v0.35.1 — 2026-11-16 · SPX BB control bar tidied
- Controls in one row of three bordered boxes: VIEW (expiry · min bid), ALERTS (0DTE / 1DTE on-off + jump, with the
  rules in the header), TELEGRAM (status + send test). Labels moved into small headers. Display only.

## v0.35.0 — 2026-11-16 · Book levels: 2 up · 1 balance · 2 down (as Dan)
- The ladder had 3 tests per side and a "next BAL" line for every rung (11 lines) — not from Dan's material. Now:
  UP TEST + UP 2, BALANCE, DN TEST + DN 2 (the guide's upper / lower test, anchor, and "second test levels").
- Chart: no "next BAL" lines; the second tests are dimmer and labelled UP 2 / DN 2. Card: one line per side for
  what happens on acceptance (range TEST → TEST 2 and its balance), nothing beyond.
- Locks saved before this version (3 per side) are trimmed to 2 on display and in the NinjaTrader / TradingView feed.

## v0.34.0 — 2026-11-16 · SPX BB history = edge changes only, kept across reboots
- A chart point is stored only when the call or put edge STRIKE changes (bid/ask and spot moves no longer add
  points). The charts put them on a 1-minute grid to now, edges held as steps; SPX comes from the recorder's
  1-minute candles (stored spot outside cash hours).
- The edge history, alert markers and alert levels are saved to state/bb_history.json on the state branch (at most
  once a minute, only after a change) and reloaded on start — a reboot no longer loses the morning.

## v0.33.0 — 2026-11-16 · SPX BB every 5 seconds
- Tracker checks every 5 s (was 15): edges, chart points and Telegram alerts react within ~5 s.
- Live section of the tab refreshes every 5 s (was 15); the two charts are rebuilt only when their data changed,
  otherwise the identical figures are re-sent.
- Chart history stores a point only when an edge or its quote changed, spot moved ≥ 0.50, or once a minute — a full
  day still fits (cap raised to 12,000 points per expiry). Tracker part needs a reboot.

## v0.32.1 — 2026-11-16 · day zip carries the long-dated book
- The day zip (📦 / 📤 / the 16:05 GitHub upload) now includes book.parquet — the long-dated book as at the send
  (sym, exp, strike, cp, type, iv, gamma, oi, volume for every subscribed expiry beyond 0/1DTE) — and
  book_state.json, so Terrain's book layer can be rebuilt offline to fit against Dan's map. Needs a reboot.

## v0.32.0 — 2026-11-16 · SPX BB: Telegram when a sold strike's ASK reaches a level
- New setting under the sold boxes, default 0.50: when the ASK of your sold C or sold P reaches it, one Telegram
  ("⚠️ … your sold 7,100P ASK 0.55 (bid 0.45) ≥ 0.50", spot, that side's edge, time). Regular hours only
  (09:30–16:00 ET, weekdays) — overnight asks are too wide. Empty sold box = not watched. Once per expiry / side /
  strike / level; a new strike or level arms it again. Same Telegram channel. Uses the view toggle's expiry.

## v0.31.1 — 2026-11-16 · SPX BB model charts: far end + 1 %
- Model charts still start at spot; the far end is now the furthest of (last live bid, edge, SAFEST, 2nd SAFEST)
  + 1 % of that strike (was 2 %). Display only.

## v0.31.0 — 2026-11-16 · SPX BB alerts: both expiries, 1DTE only 15:00–21:00 ET, "EDGE"
- Alerts no longer follow the view toggle (the saved toggle was 1DTE, so 0DTE never alerted). Now both expiries
  alert whatever any tab shows: **0DTE always** (while live) · **1DTE only 15:00–21:00 ET**.
- Separate **Alert 0DTE / Alert 1DTE** switches, each with its own jump size (5–50 pts, default 10), saved;
  an old single threshold carries over to both.
- Edge levels are kept per expiry date: tomorrow's expiry keeps its level when it turns 0DTE at 21:00. Outside its
  window (or switched off) the level follows the edge silently, so the first alert after 15:00 is measured from the
  edge at that time, not from hours earlier.
- Telegram text says **CALL EDGE / PUT EDGE** (was "WALL"). Sold-strike warnings apply to the expiry being viewed.

## v0.30.4 — 2026-11-15 · SPX BB model: one small box per side + best-ratio star
- The combined table is replaced by a box above each chart (puts above the put chart, calls above the call chart):
  SAFEST, 2nd SAFEST, Furthest put / Furthest call (the last live bid) and ★ Best ratio — strike, history move,
  bid, chance per year, ratio after fees. Sold rows, per-session %, expected loss and cautious ratio removed.
- ★ Best ratio = highest ratio after fees among live bids where expected loss ≤ 50¢ (the chart's far-OTM zone;
  ties go further from spot); a yellow star marks it on the chart at its bid.
- SPX label moved inside the plot so it no longer overlaps the title.

## v0.30.3 — 2026-11-15 · SPX BB model charts: spot → last bid + 2 %
- Each model chart runs from spot (solid line, labelled "SPX …") out to the furthest of the last live bid, the 0.05
  edge, SAFEST and 2nd SAFEST, plus 2 % of that strike (calls ×1.02, puts ×0.98). Replaces display_window, which ran
  on into strikes with nothing to sell. Height still capped at 50¢. Button-only rules unchanged.

## v0.30.2 — 2026-11-15 · SPX BB model charts reach the furthest live bid
- Each model chart's strike range now always includes the furthest live bid (the 0.05 call / put edge at the press)
  as well as SAFEST / 2nd SAFEST; before, display_window alone could stop short of it (calls ended ~7,975 while
  the 0.05 edge was 8,025). Blank-bid strikes still aren't drawn. Button-only rules unchanged.

## v0.30.1 — 2026-11-15 · SPX BB edge model: SAFEST lines, readable charts, % probability
- core/edge_model.py replaced with the user's new version, unchanged (sha256 9034b9c0…) — adds run.safest().
- SAFEST / 2nd SAFEST for puts and calls (run.safest): rows in the table (strike, historical move + date, bid at
  that strike from the press snapshot, chance, expected loss, ratios — "no bid" shows no ratio) and dashed lines
  on the charts with labels and a ▼ on the bid.
- Charts redrawn like the edge script: live bids as dots (blank bids not drawn), expected loss dashed, cautious
  (95 %) dotted, y capped at 50¢, x = run.display_window (widened to keep SAFEST on screen); title shows SPX, VIX
  and the fitted typical-move formula.
- Probability shown as % per session and times per year (× 252 sessions) instead of 1 in N.
- Still button-only: nothing runs on load, rerun, toggle change or in the tracker thread.

## v0.30.0 — 2026-11-15 · SPX BB: edge model (button only)
- core/edge_model.py added **unchanged** (user's file, sha256 e2b752e9…). History from Yahoo via its own
  load_history(); `yfinance` added to requirements.
- Top of the SPX BB tab: **▶ Run model**. The model runs ONLY on that press — never in the 15-s tracker thread,
  never on a rerun / auto-refresh / reload, never on a toggle change, no cache. On press: the toggle selected at that
  moment, spot + source from rec.spot_now(), now_et without tzinfo → edge_model.run_model(...); stored in
  st.session_state with a frozen snapshot of the bids, edges and sold strikes.
- Shows: last-run line (time ET, toggle, spot + source, VIX + its date); call edge, put edge, sold C, sold P with
  chance reached (1 in N), expected loss (¢), ratio after fees, cautious ratio; charts of expected loss vs bid for
  every strike with a bid from spot to 20 % (x-axis zoomed with display_window, analysis covers the full 20 %), full
  table in an expander; the open/close note. Results stay until the next press; if the toggle changes they stay,
  labelled with the toggle they were run for.
- A reload clears the results (st.session_state is per browser tab); it does not run the model.

## v0.29.1 — 2026-11-15 · SPX BB width chart = one line
- The 0.05-bid width chart shows only the width (call edge − put edge), as in the user's sheet; the call / put
  distance lines are removed (distances are in the middle panel).

## v0.29.0 — 2026-11-15 · SPX BB tab (0.05-bid liquidity edges + Telegram)
- New top-level tab **SPX BB** (tabs/spxbb.py, core/bb.py), laid out like the user's sheet:
  - toggle **0DTE · <date> / 1DTE · <date>** (EXPIRED shown after 16:00); SPX BB's own roll is **21:00 ET** — after
    the close "1DTE" stays tomorrow until 21:00 (the rest of TRISHULA still rolls at 16:15);
  - C / P / R / W panel: call & put 0.05-bid edge, distance, % of spot, bid/ask; R = put dist ÷ call dist; W = width;
    spot box (SPX, or the option-implied spot pre-market / after the close);
  - your **sold C / sold P** inputs: buffer to the edge, live ask, distance from spot — green when your strike is
    outside the last 0.05 bid, red when the edge has reached it;
  - charts: 0.05-bid width; furthest 0.05-bid strikes with the **call band blue / put band magenta** shaded from spot
    to the edge, alert markers, your sold strikes.
- Recorder subscribes bid/ask on **every** 0DTE and 1DTE SPXW strike (the edges can be 600 pts out; legs are ±60).
- Background tracker every 15 s, running pre-market and whenever the app is up. **Telegram**: an edge alerts when it is
  ≥ threshold pts beyond the last alerted strike, away from spot (high-water mark, no repeats); one warning when an
  edge reaches your sold strike. Threshold dropdown 5–50 (default 10), min bid, alerts on/off, 📨 test button.
  No alerts on stale quotes or in the 09:15–09:30 gap. Settings + sold strikes saved to state/bb_config.json.
- Secrets: **TG_BOT_TOKEN / TG_CHAT_ID** in Streamlit secrets only. Day zip gains spx_bb.json.

## v0.28.0 — 2026-11-14 · SPXO / AM split + real expiry times · CLEAN-B dealer sign · TASTIER surfaces by strike
- **SPXO / SPX AM monthlies (core/expiry.py):** tastytrade lists every root expiring on a date in one list, and TRISHULA
  mixed them (Colab check 14 Nov: Wed 18 Nov = SPXO AM + SPXW PM; Fri 20 Nov = SPX AM monthly + SPXW; same 16 Dec,
  18 Dec, 15 Jan). Now:
  - 0DTE / 1DTE recording, snapshots, Book, Lean, TASTIER, extra expiries: **SPXW (PM) only**.
  - AM contracts (SPXO weekly, SPX monthly) go to the long-dated book / Terrain as their own expiry `YYYY-MM-DDAM`,
    expiring **09:30 ET** on their date; they count up to the settle and drop out at the open.
  - Book header on the day before an AM settle: "AM-settled at <day> 09:30 open, ±2 % of spot: SPXO OI … · SPX OI …".
- **Real expiry times everywhere** (were hard-coded 16:00 in dealer, terrain, gex, tetris, lean, book, AG-REV, VS3D):
  each PM expiry ends at the chain's stops_trading_at — **13:00 ET on the half days 27 Nov and 24 Dec** — so charm,
  gamma and time-to-close are right on those days.
- **CLEAN-B (single-leg Book) dealer sign fixed:** was −(net calls − net puts), a bull/bear direction number that showed
  customer-bought puts as dealer LONG. Now dealer position = −(net calls + net puts). Feeds the CLEAN-B 09:25 lock and
  the NinjaTrader clean levels. (12 Nov 11:36 replay: UP 7660 · BAL 7625 · DN 7605 with price pinned 7625–7635.)
- **TASTIER gamma + vanna surfaces by STRIKE** (the Tastier layout, bright bands at the big strikes): every 5 min, each
  strike's dealer γ / vanna at that moment's SPX price; flip line from the total γ by price. The start position now uses
  the PRE-OPEN sign × morning OI, then today's customer flow once (v0.19.3 used the live sign, which already contained
  today's flow, then subtracted it again → one solid colour).

## v0.27.1 — 2026-11-12 · Day data → GitHub Releases (so Claude can pull it)
- New core/ship.py: the "📦 prepare today's data" zip is uploaded to a **GitHub Release** on this repo, tag
  `data-YYYY-MM-DD` (tagged on the trishula-state branch, pre-release, never "latest"). Release files are not in the
  git history, so the repo does not grow, and nothing redeploys the app.
- **Automatic** once per trading day at 16:05–16:14 ET (before the 16:15 roll) as `trishula_day_<date>_close.zip`.
- **📤 send today to GitHub** button in "Today's data + past sessions" for a mid-session copy
  (`..._<HHMM>.zip`, ET); status + errors shown next to it.
- **Retention:** only the newest 10 data days are kept; older data releases and their tags are deleted after each
  send. Code, main and trishula-state are never touched.
- Token: the existing GITHUB_STATE_TOKEN (Contents read/write covers releases). No token → button disabled, no auto.
- app.py `_day_zip` now calls `core.ship.day_zip` (same contents).

## v0.27.0 — 2026-11-12 · Book levels = Dan's Test/Anchor method · Terrain defaults
- Why: the old card (vs3dgbt rule) centred its window on the 09:30 open at ±2.5× straddle and locked at 09:35. On
  12 Nov it locked UP 7565 (already below spot) >> 7600, DN 7400, BALANCE 7465 — mostly unusable. The guide (§4.3–4.7)
  reads levels from the OPENING position in contracts (not gamma), around spot ± 1× straddle, and they stay static.
- **Book levels rewritten (core/book.py `method_levels`)**, guide only, no tuned thresholds:
  - range = spot ± 1× ATM straddle; clusters = runs of same-sign strikes, level = the cluster's biggest strike;
  - UPPER / LOWER TEST = biggest dealer-short cluster above / below spot inside the range;
  - ANCHOR (balance) = biggest dealer-long cluster between the tests;
  - ladder (3 tests per side): next test = biggest short within one straddle beyond the broken test (nearest beyond
    if none, marked "outside range"); after acceptance the range is broken test → next test, balance = biggest long
    between. Acceptance is described ("NOW 7,631: beyond upper test 7,600 — if it holds…"), never decided;
  - card also shows cluster size and span, TESTED / TRADED THROUGH, the long/short alternation count in the range
    (fishbone, descriptive), "Morning: treat all levels as tests"; Book chart draws the ladder anchors (next BAL).
  - removed: open-centred 2.5× window, wall shift (ᵂ), fly-package flags, 20 %-of-max test picking.
- **Lock at 09:25 ET** (pre-market, like his published levels): first chain snapshot ≥ 09:25, centred on that
  snapshot's spot (ES-implied pre-market) ± its straddle. **OI guard**: a snapshot whose near-spot 0DTE OI still equals
  the previous day's logged OI is skipped ("OI stale — lock pending"); 12 Nov OI arrived 06:30 ET. Late = after 09:30.
  Single-leg (CLEAN-B) lock: same method, from 09:25. Locks saved before v0.27.0 still render with the old card.
- NinjaTrader / TradingView feeds carry the new tests (up to 3 per side) and balance — formats unchanged.
- **Terrain defaults**: Range Dan, Signed on, Sign source single-leg, OI + Volume, volume weight 0.05, long-dated book
  ON at weight 0.35, simulated gamma/charm off. Changed settings are kept in the page URL, so a reload keeps them.
- Fix: Terrain cache key and frozen-column key include the number of long-dated book expiries — a map drawn before
  the book subscribed ("0 expiries") is no longer reused.

## v0.26.0 — 2026-11-12 · Terrain: long-dated book layer (risk-reversal prior)
- Why: 12 Nov 10:30 — our 0DTE dealer sign agreed with VS3D's Positions by Strike at 12 / 15 strikes (all prints,
  corr +0.55), yet our gradient was green where his was red. His gradient is ALWAYS the whole book (every expiry,
  months out + Flex); this morning it was the textbook dealer short risk reversal (long calls above, short puts
  below). We only modelled 1–3 tape-signed expiries.
- Recorder: once per session (90 s after start, skipped if memory is high) subscribes **Greeks + Summary only** for
  the long-dated book — every expiry in the next 10 days + monthly / quarterly / EOM out to ~6 months, strikes within
  ±7 % of spot every 25 pts (≈ 1–2 k symbols). Not added to legs, prints or snapshots. Status shows `book`.
- Terrain controls ▸ **Long-dated book (risk-reversal prior)** + **Book weight** (default 0.3): adds those contracts
  as OI × (calls +w / puts −w) on top of the tape-signed expiries; past columns use the same book. Default OFF until
  scored against his screenshots.

## v0.25.1 — 2026-11-11 · Terrain calibration tools (from his VS3D tooltips)
- Terrain controls ▸ **Volume weight** (0–1, default 1): field weight = OI + w × today's volume. VS3D nets out
  market-maker and customer-vs-customer trades (dealer imbalance ≈ 1–2 % of volume, guide §1.3); turn this down
  until our numbers match his tooltip. Part of the frozen signature (switching rebuilds the past columns).
- Dan range: **HPT probe** in the title in VS3D's tooltip units and sign (+ = dealers BUY per $1 up): at spot, at the
  short-gamma core and at the long-gamma core (price shown). Charm title: HPT at spot per 5 min.
- Dan range: **soft saturation** (≈ linear near 0, full colour at 4 × cap) and the gamma-pocket overlay switched off
  — its solid red "core" was the blocky blob. VS3D-style **max / min lines** (§7.7): magenta = local max,
  cyan = local min, on gamma and charm.
- Fixes: "$" in titles no longer turns the text into italic maths; "cap auto-recalibrated" note hidden in Dan range.
- Tip: the session axis (overnight from 20:15 vs 09:30–16:00) is the existing 🌙 GTH toggle in the player bar.

## v0.25.0 — 2026-11-11 · Terrain vs VS3D: Dan scale, sign source · Lean: rule C dropped
- Terrain controls ▸ Range: new **Dan (minis, linear ±250 / ±100)** — gamma in E-minis per $1 (±250), charm in E-minis
  per 5 min (±100), linear, power 1, symmetric (VS3D guide §2.1 / §2.4 / §3.1 / §7.5 / §7.9). A light day (< 100 minis/$1)
  now LOOKS light instead of solid green. Titles show "Dan ±250 minis/$1" / "Dan ±100 minis/5min".
- Terrain controls ▸ **Sign source**: all prints (as before) · single-leg (spread / complex legs removed, like Book chart 2)
  · opening book (pre-open sign × OI only ≈ VS3D's 9pm expiring-OI blue dots; weighting forced to OI). Past columns
  rebuilt from snapshots use the same sign source; switching re-freezes (part of the frozen signature).
- More expiries in the field = the existing "Expiries to aggregate" slider (1–5); no new control.
- Defaults unchanged (Manual cap, all prints) — the new options are for scoring against VS3D screenshots first.
- Lean: rule C removed from presets and the locked test (user, 11 Nov); lean panel taller (chart 900 px).

## v0.24.1 — 2026-11-09 · lean saves: right day, never lose data
- Fix: after a post-close restart the recorder points at tomorrow's expiry while its replayed prints are today's →
  the save went to tomorrow's file (the "6 Nov" file held 5 Nov replay data). Now a day is saved only when the 0DTE
  expiry IS today (ET), and each file keeps only its own date (old days' SPX bars / replayed prints dropped, ~65 KB).
- Saves MERGE with what is already on the branch: per minute and expiry the fuller row wins, SPX bars are unioned →
  a restart mid-day (replay-thin data) can no longer overwrite the live-recorded minutes.
- Extra save right after 16:00 ET (a restart between 16:00 and the 16:15 roll no longer cuts the day).
- Lean tab / locked test read each file's own date (they used the last SPX date in the file); files without RTH bars
  of their own date are hidden (the bad 6 Nov file). Clearer message when there is no live session.

## v0.24.0 — 2026-11-05 · VS3D ▸ Lean (lean candles, live single-leg) + permanent lean minutes + locked test
- New VS3D sub-tab **Lean**: SPX 1-min candles painted by the options-flow lean (blue bull · magenta bear · grey),
  flow = delta $ from the recorded prints (calls bought / puts sold vs puts bought / calls sold), single-leg or all.
  Every setting is a toggle: day (today live / any saved day) · preset A–D · bars 1/5 min · 0DTE or 0+1DTE ·
  single-leg / all prints · lean rolling N min / since open / per bar · sticky / band · X · 2-bar break · cooldown ·
  skip first 10 min · grey holds / flattens. Net Δ$ bars + lean panel with ±X; ▲▼ = executed at every colour change;
  trade table and the day's net points after 0.5 pt per round trip.
- Lean minutes (single-leg AND all prints, 0DTE + 1DTE, $M Δ bull / bear per minute + SPX 1-min OHLC) saved to the
  `trishula-state` branch as state/lean/YYYY-MM-DD.json every 15 min and at the 16:15 roll (~70 KB a day; same
  GITHUB_STATE_TOKEN as the 09:35 lock; survives reboots). Also inside 📦 today's data as lean_minutes.json.
- ⭐ saved settings: save the settings on screen with a note (state/lean_settings.json); listed with the locked rules
  and included in the history zip. 📦 "prepare lean history" = every saved day + settings in one zip.
- 🧪 Locked test A–D (pre-registered 5 Nov, RESEARCH_LOG §12) runs on the saved days with 200 time-shifted nulls.
- Research scripts L47 / L48 (lean-candle tests) added to research.zip.

## v0.23.1 — 2026-11-05 · past sessions download
- 📦 section now lists the past sessions the recorder saved on the container (flushed every few minutes and at the
  16:15 roll) and zips any of them: prints with the spreadLeg flag, chain snapshots, spot, OI, meta — the raw parquet
  parts, no re-processing. Lets research use full-day single-leg tape (the tastytrade replay keeps only the last ~1,000
  prints per contract). Saved days survive a code update but not a Reboot.

## v0.23.0 — 2026-11-02 · single-leg levels on NinjaTrader · TradingView paste + "TRISHULA Levels" Pine script
- Feed `book` adds the single-leg levels (clean_levels, clean_state, clean_locked_at) from the app's single-leg lock;
  the single-leg lock now also stores its profile.
- NinjaTrader indicator 7.1.0: single-leg levels dotted — SL UP dodger blue · SL DN magenta · SL BAL yellow (faded =
  preview), labels left of the profile, own switch + colours; status line shows single-leg locked / preview.
- Book tab: "TradingView paste" box (copy icon) — one line per day: TRI1|date|M:/m: main levels|S:/s: single-leg
  levels|P: 09:35 main profile|Q: single-leg profile (SPX prices, ±100 of spot; upper case = locked).
- tradingview/TRISHULA_Levels.pine (1.0.0): 10 paste fields, date read from the paste; each day's 10 levels drawn
  across that day's session in the NinjaTrader colours (latest day extends right + labels); latest day's main and
  single-leg 09:35 profiles to the right of the last bar; SPX prices converted on ES / MES / SPX CFDs by the live
  chart ÷ SPX ratio (taken where SPX prints, held overnight). No straddle, no live bars.

## v0.22.0 — 2026-10-28 · Book: 09:35 dots + single-leg view on NinjaTrader · single-leg levels on the app
- 09:35 lock now stores its own profile (dealer net contracts per strike, ±200 of spot); saved/restored with the lock.
  Feed profile rows carry net_935. NinjaTrader v7: with dots ON the profile gets a ZERO LINE in the middle (right =
  dealer long, left = short), dot = 09:35 value, grey line = move since the lock; dots OFF = bars from the edge as before.
- Feed `clean_profile` = single-leg (clean-B) book per strike. NinjaTrader v7 draws it on the LEFT edge (blue = dealer
  +, magenta = −; strikes with no single-leg evidence have no bar); width / offset / opacity / colours in "4. Book".
  Level and straddle labels move right of the band.
- App, Book chart 2 (CLEAN-B): levels now from the single-leg book's OWN structure (was the flow-book lock imposed),
  own lock taken at the first computation ≥ 09:35 (feed thread, ~09:35–09:36), saved/restored like the main lock;
  title shows "preview" / "locked hh:mm". Main book, its levels and the card are untouched.
- NinjaTrader indicator now versioned on its own: 7.0.0 (shown on the chart), history in ninja/CHANGELOG.md.
- Fix: Book-tab card header now shows the lock note (restored / LATE LOCK) — v0.21.2 only showed it in the combined view.

## v0.21.2 — 2026-10-27 · memory fix (27 Oct 13:2x crash) + 09:35 lock survives reboots
- CRASH CAUSE (log 27 Oct): RSS 2.0–2.4 GB at 1.13M prints, swinging ±800 MB → platform kill. Measured on a 1.24M-print
  replay: the print store itself is only ~176 MB; the NinjaTrader feed copied + enriched the WHOLE store every minute
  (~1 GB transient) and glibc kept the freed memory (RSS +700 MB until a trim).
  · rec.print_minutes(exp): signed volume per contract-minute aggregated INCREMENTALLY (only new prints) — used by the
    feed and the Signals view instead of prep_prints on the whole store (identical minute flow, tested).
  · glibc tuning at start-up (≤2 arenas, fixed 1 MB mmap threshold, trim threshold 32 MB) + trim after every feed write.
  · Result on the replay (1.24M prints, feed thread running, every heavy tab twice): steady ~0.5–0.9 GB, peak 1.19 GB
    (feed alone: +2 MB per write after the first, was +800 MB).
- 09:35 LOCK SURVIVES A REBOOT: saved when it forms to the app's own repo, side branch `trishula-state`,
  file state/lock.json (overwritten daily; Streamlit runs only `main`, so a save never redeploys). Restored after a
  restart → the Book tab and the NinjaTrader feed keep the exact 09:35 levels ("restored after restart").
  Needs secrets GITHUB_STATE_TOKEN (fine-grained, this repo, Contents read/write); optional GITHUB_STATE_REPO.
  Without it — or if the lock formed while the app was down — the lock is flagged "⚠ LATE LOCK hh:mm" in the Book header
  and in the NinjaTrader status line. Diagnostics shows backup read / saved / errors.
- NinjaTrader indicator v6: status line shows the lock note.

## v0.21.1 — 2026-10-27 · NinjaTrader indicator v5 (indicator only, app code unchanged)
- Signal arrows sometimes missing after a reload (status line showed the marks, chart didn't): v4 drew them as drawing
  objects from OnBarUpdate on a "new data" flag and remembered what it had drawn → timing-dependent. v5 PAINTS arrows,
  labels and the status line in OnRender every repaint, like the Book — a mark in the feed that passes the filters is on
  the chart every time, pinned to its bar and ES price. No drawing objects at all. New setting "Arrow size". Status line
  shows "passed only" / "all". Compile-checked; filter tested on the 07:04 feed (More · 0+1DTE · passed only = 9 S6 marks).

## v0.21.0 — 2026-10-27 · Book levels + profile in the NinjaTrader feed
- Feed gets a `book` section (0DTE, same logic as the VS3D Book): key levels UP TEST / DN TEST / BALANCE with
  state = PREVIEW (yesterday's book, before the 09:35 ET lock) or LOCKED (frozen for the session, `locked_at`), the
  straddle band (spot ± ATM straddle, moves with spot), and the flow-signed profile — dealer NET CONTRACTS per strike
  (inferred sign × OI, conf = opacity), strikes within ±150 of spot. Every price in SPX and ES (× ES/SPX latest minute).
- NinjaTrader indicator v4: paints the Book in OnRender (no drawing objects, no chart reload) — levels across the chart,
  DASHED while PREVIEW, SOLID once LOCKED, each labelled with ES and SPX price; dotted straddle band; profile bars from
  the right edge (green = dealer long, red = dealer short, numbers = contracts · SPX strike). New "4. Book" settings:
  levels / straddle / profile on-off, profile width + opacity, numbers on-off, line width, colours. Status line shows
  book PREVIEW / LOCKED. Compile-checked.

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
