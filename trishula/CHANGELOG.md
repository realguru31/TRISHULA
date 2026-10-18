# TRISHULA changelog

Semantic versioning: MAJOR.MINOR.PATCH. The running version is shown in the app's
status bar, every tab footer, and the Recorder diagnostics panel.

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
