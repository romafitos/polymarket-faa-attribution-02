# Polymarket FAA attribution forecast — polymarket-faa-attribution-02

Forecasts each market's Yes price at every minute 1..240 after a
checkpoint, as five quantiles (0.05, 0.25, 0.5, 0.75, 0.95). Scored by
mean pinball loss (percentage points, lower is better). Python 3.13,
stdlib only, no network, deterministic.

## Method

Adaptive-volatility quantile forecaster, built from our NVIDIA v5
forecaster and re-engineered for the FAA family:

- **Centre:** last price, blended 50/50 with the median of the last 10
  minutes on low-sum families (jump smoothing); the last 1-minute move
  is faded when up and continued when down.
- **Volatility:** RMS of 1-minute price changes — 120-minute window
  normally, 30-minute window on low-sum families (the 120-min RMS is
  inflated by launch jumps). Floored at 0.0005, capped at 0.01.
- **Spread:** sigma * h**0.35, asymmetric quantile widths
  (low-outer 1.1, low-inner 0.85, high-inner 0.35, high-outer 1.3).
- **Sum pull (gated):** cross-market pull toward sum 1, weight 0.70,
  phased in over 60 minutes — but only when the observed sum is
  >= 0.85, linearly off below 0.60. The FAA family sums to 0.13–0.22
  (not mutually exclusive), where the ungated pull explodes centres ~7x.
- **Centre bleed (low-sum families only):** centre decays as
  exp(-0.008 * h), gated off once the family sum reaches 0.5, floored
  at 0.5x the last price. Live FAA prices bleed down while no
  attribution news arrives.
- **Subset cap:** P(Iran) <= P(foreign actor) — Iran's quantiles are
  capped at foreign's.
- **Jensen median decay (v5):** median *= exp(-96 * gate * sigma^2 * h/2),
  gated on the sum (off on FAA sums).

## Scores (pooled pinball loss, local backtest)

| set | this entry | house baseline | v5 as-is |
|---|---|---|---|
| NVIDIA 12-cut | **0.247642** | 0.368632 | 0.247187 |
| Practice item-weighted (piw) | **0.238606** | 0.363589 | 0.238129 |
| NVIDIA 21-cut | **0.179341** | — | 0.178745 |
| Live FAA cuts (7) | **0.456948** | 0.830227 | 3.407812 |

Live board at hand-back (~10:00 WIB 14 Nov 2026, 366 submissions,
305 ranked): #1 0.249, #10 0.259, #100 0.272. piw 0.238606 is 12.3%
below the #100 cutoff (8%-bar 0.250240) and 4.2% below #1. The practice
is cut from NVIDIA and is no guide to the final (different markets);
the FAA-cut column is the final-family evidence.

## Validation

`python3 validate.py` on the real code path: 21 NVIDIA cuts + 7 live
FAA cuts, run twice — numbers reproduce exactly, outputs
byte-identical, max runtime 0.13 s/case (cap 8 s), output 40–265 KB
(cap 1 MiB), all quantiles in [0, 1] and non-decreasing. See
VALIDATION.md for the full experiment log.

## Files

- `main.py` — the entry (Python 3.13, stdlib only).
- `LICENSE` — MIT.
- `VALIDATION.md` — exact numbers, live-board comparison, and every
  iteration tried with its measured result.
- `exp.py`, `validate.py`, `fetch-kit.mjs`, `board*.mjs` — local
  experiment harness, validation runner, kit fetcher, live-board
  fetcher (not part of the entry; the entry is `main.py` alone).
- `kit/` — the fresh kit downloaded for this competition.
- `faa_hist_*.json`, `faa_grids.json` — live Polymarket price history
  fetched 2026-11-14 02:39 UTC and the 1-minute grids built from it.
