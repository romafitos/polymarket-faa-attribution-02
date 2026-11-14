# VALIDATION — polymarket-faa-attribution-02

Build-only hand-back. No repo created, no submit run (parent does that).

## Final numbers (real code path, `python3 validate.py`)

- NVIDIA 12-cut (p00–p05 + x00–x05): **0.247642**
- Practice item-weighted (piw, p00–p05): **0.238606**
- NVIDIA 21-cut: **0.179341**
- Live FAA cuts (7 checkpoints, 2026-11-13 22:40 → 2026-11-14 01:40 UTC,
  answers truncated at last recorded grid minute 02:37 UTC): **0.456948**
- Determinism: two full runs byte-identical (`byte-identical x2: True`)
- Runtime: max 0.13 s/case (cap 8 s); output 40,151–265,200 B (cap 1,048,576)
- Shape: all outputs exactly `{"forecasts": [...]}`, 240 rows × 5
  quantiles per market, values in [0, 1], non-decreasing per row
- House baseline: practice 0.363589 (RULES); FAA-cut equivalent 0.830227
  (measured with the same harness)

## Live-board gate (tightened 09:47 WIB 14 Nov: ≥8% below live #100)

Board fetched ~10:00 WIB 14 Nov 2026 via
`GET /api/competitions/polymarket-faa-attribution-02/leaderboard`
(366 submissions, 305 ranked; losses as published, 3 sig. figs.):

| rank | loss |
|---|---|
| #1 | 0.249 |
| #2 | 0.251 |
| #10 | 0.259 |
| #20 | 0.263 |
| #50 | 0.268 |
| #100 | 0.272 |
| #150 | 0.277 |

- piw 0.238606 vs #100 0.272: **12.28% below the cutoff** (8%-bar 0.250240)
- piw vs #1 0.249: 4.17% below
- **Gate PASSES**: piw ≤ 0.240 AND ≥8% below the live #100 cutoff.

Caveat (brief's own warning, repeated here deliberately): the practice
is cut from "Next CEO of NVIDIA?" — different markets from the final.
The practice gate is a proxy; the final is 12 cases on the 4 FAA
markets, 2026-11-14 14:00 UTC → +48 h. The FAA-cut column above is the
only final-family evidence, and it is 7 overlapping cuts from the
5-hour launch transient — it validates the structural fixes, not the
absolute level. If the final's prices flatten instead of bleeding, the
bleed term costs roughly +0.07–0.10 (bounded by the 0.5 floor); if they
keep bleeding at the measured rate it saves ~0.19 vs no bleed.

## The key structural finding

The FAA family is NOT mutually exclusive (Iran ⊂ foreign actor; a hack
can be by a foreign actor). Live sums (Polymarket public history,
fetched 2026-11-14 02:39 UTC): 0.13–0.22, vs NVIDIA sums 0.81–1.09.
The v5 sum-pull at S = 0.09 multiplies centres by ~7x. Measured on
live FAA cuts: **v5 as-is 3.407812** vs house baseline 0.830227.
The sum-pull gate alone fixes it (FAA 0.756), and the bleed + fast vol
window + median centre bring it to 0.457.

Live FAA data at fetch time (2026-11-14 02:39 UTC): Iran 0.515 → 0.018,
foreign 0.255 → 0.0295, hack 0.155 → 0.036, AI 0.215 → 0.008 (first →
last point). Family sum 0.556 (22:37) → 0.091 (02:37). Every market's
120-min log-drift negative (-0.0025 to -0.010/min). Loss concentrates
in hack (1.78 of 0.756 base) and in the median/shoulder taus.

## Experiment log (all measured on NVIDIA 12-cut / piw / FAA 7-cut)

Starting point: v5 as-is — 12-cut 0.247187, piw 0.238129, FAA 3.407812.

| # | change | 12-cut | piw | FAA | verdict |
|---|---|---|---|---|---|
| 0 | sum-pull OFF entirely | 0.252212 | 0.246406 | 0.755647 | gate needed, not removal |
| 1 | sum-pull gate (0.85, 0.95) | 0.250590 | 0.244340 | 0.755647 | — |
| 1 | sum-pull gate (0.80, 0.90) | 0.249537 | 0.243666 | 0.755647 | — |
| 1 | sum-pull gate (0.70, 0.90), pull 0.70 | 0.247920 | 0.239995 | 0.755647 | — |
| 1 | **sum-pull gate (0.60, 0.85), pull 0.70** | **0.247642** | **0.238606** | **0.755647** | ADOPTED |
| 2 | vol cap 0.015 / 0.02 / 0.03 | 0.253–0.258 | 0.247–0.251 | 0.773–0.851 | reject (hurts both) |
| 2 | alpha 0.30 / 0.40 / 0.45 | 0.249–0.258 | 0.241–0.255 | 0.757–0.782 | reject |
| 2 | vol win 60 / 240 | 0.260–0.261 | 0.255 | 0.730–0.764 | reject (global) |
| 2 | wider widths [1.1,.85,.5,1.6] / [1.3,1,.5,1.5] | 0.249–0.250 | 0.242–0.243 | 0.760–0.783 | reject |
| 2 | gap off | 0.248929 | 0.242249 | 0.758639 | reject (keep gap) |
| 3 | EWMA vol hl 30 / 60 | 0.252 | 0.245–0.246 | 0.749–0.759 | reject (piw cost) |
| 3 | median-only decay k=0.001–0.002, gated | 0.247642 | 0.238606 | 0.738–0.746 | weaker than centre decay |
| 4 | centre decay k=0.002–0.006, gated, floor 0.5 | 0.247642 | 0.238606 | 0.724–0.570 | k rises help; saturates ~0.008 |
| 5 | per-market trend drift (win 60/120, shrink 0.5/1) | 0.247642 | 0.238606 | 0.736–0.776 | reject (noisy, ~no gain) |
| 5 | family sum-drift (shrink 0.5/1, cap .005/.01) | 0.247642 | 0.238606 | 0.739–0.746 | reject (early cuts lack 120-min history) |
| 6 | **vol window 30, low-sum only** | 0.247642 | 0.238606 | **0.529744** | ADOPTED (15: 0.544, 45: 0.543) |
| 7 | jump boost x2/x3 (k=2/3) | 0.249–0.251 | 0.241–0.245 | 0.585197 | reject (never triggers at checkpoints; hurts piw) |
| 8 | subset cap Iran ≤ foreign | 0.247642 | 0.238606 | 0.584988 | ADOPTED (tiny gain, always true) |
| 9 | stay-mixture quantiles | 0.281113 | 0.272576 | 0.586100 | reject (piw disaster) |
| 10 | logit-space spreads (cap .05/.10) | 0.259 | 0.257 | 0.548–0.591 | reject (piw cost) |
| 11 | **centre median blend w=0.5, n=10, low-sum only** | 0.247642 | 0.238606 | **0.472550** | ADOPTED (w=0.3: 0.476, w=0.7: 0.475, w=1.0: 0.495; n=5: 0.479, n=20: 0.466) |
| 12 | alpha_low 0.30 / 0.45 | 0.247642 | 0.238606 | 0.519–0.536 | reject |
| 13 | bleed k=0.007 / 0.008 / 0.010 / 0.012 (with vol30+medblend) | 0.247642 | 0.238606 | 0.463 / **0.457** / 0.456 / 0.464 | **k=0.008 ADOPTED** (0.010 within noise, 0.012 worse) |
| 13 | bleed floor 0.4 (k=0.008) | 0.247642 | 0.238606 | 0.454637 | not adopted (noise-level; floor 0.5 is safer) |

All low-sum-gated terms leave the NVIDIA numbers bit-identical
(piw 0.238606, 12-cut 0.247642) by construction: the gates are 0 on
NVIDIA sums (≥0.81) and 1 on FAA sums (≤0.22).

## Kit grade-local

`node cli/makefun.mjs grade-local --kit . --bot <dir> --driver process`
from inside the unpacked kit answers: "polymarket-faa-attribution-02
is a program/v1 competition: its scorer and reference data are not
published in the kit, so it is graded on the server only" — no local
grade-local run exists for this harness. Instead, `main.py` was run
directly on the kit's own practice inputs (`kit/.../input/p00–p05.in`):
all 6 cases produce valid outputs (19/19/19/23/24/24 markets, 240×5
quantiles, values in [0,1], non-decreasing), and `validate.py` scores
those same cases through the real code path at piw 0.238606.

## Reproduce

1. `python3 exp.py` — v5-as-is vs house baseline on both cut sets.
2. `python3 validate.py` — real `main.py` code path, 28 cuts, 2 runs.
3. Live FAA data: `faa_hist_*.json` (Polymarket public
   `prices-history`, fidelity=1) → `faa_grids.json` (house 1-min grid
   rules). NVIDIA cuts: `~/workspace/makefun/polymarket-nvidia-ceo-forecast-01/cuts/`.
