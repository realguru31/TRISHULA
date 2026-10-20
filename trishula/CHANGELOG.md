# TRISHULA changelog

Semantic versioning: MAJOR.MINOR.PATCH. The running version is shown in the app's
status bar, every tab footer, and the Recorder diagnostics panel.

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
