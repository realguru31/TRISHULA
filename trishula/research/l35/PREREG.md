# L35 — walk-forward thresholds for the Signals view. Locked 25 Oct BEFORE running.
Days: 22 sessions with 1-min option candles, chronological (24 Sep … 23 Oct). Folds: train = every day before the test
block, test = next 3 days: test blocks = days 11–13, 14–16, 17–19, 20–22 (4 folds, 12 test days).
Per signal, grid (all else = locked l29 rules):
  S1 k ∈ {3,5,7,10,15,20,30} × at-side share ∈ {0.8,0.9,0.95}
  S3 size ∈ {300,500,750,1000,1500,2000,3000}
  S4 need ∈ {1,2,3,4} × α ∈ {0.15,0.25,0.5}
  S5 share ∈ {0.03,0.05,0.08,0.10,0.15} × pts ∈ {3,4,6}
  S6 pts ∈ {6,8,10,12,16} × breadth ∈ {3,5,7}
  S7 size ∈ {500,1000,2000} × mult ∈ {5,10} × 30-min range ≤ {10,15,25}
Selection in train: among settings with ≥ 15 events, the one with the highest edge t-stat (edge = pts at 20 min minus
200 random same-day same-direction entries). Scored ONLY on the test block.
Sensitivity positions (for the one slider): fewer = choose only among the strictest third of the grid (fewest train
events), middle = whole grid, more = loosest third. Each position walk-forwarded the same way.
PASS (signal × position): pooled out-of-sample edge > 0, t ≥ 2, and ≥ 3 of 4 folds positive. Else "no edge".
