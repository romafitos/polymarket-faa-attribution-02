"""Quantile forecaster — polymarket-faa-attribution-02.

Forecasts each market's Yes price at every minute 1..240 after a
checkpoint, as five quantiles (0.05, 0.25, 0.5, 0.75, 0.95). Scored by
mean pinball loss (in percentage points, lower is better).

Built from our NVIDIA v5 forecaster (adaptive-volatility quantile
forecaster: median = last price, per-market RMS vol 120 min, spread
sigma * h**0.35, cross-market sum-pull 0.60, Jensen median decay), with
two structural fixes that the FAA family forces. The practice cases are
cut from "Next CEO of NVIDIA?" (24 mutually-exclusive markets, sums
~0.8-1.09) but the final is the FAA attribution family: FOUR markets
that are NOT mutually exclusive (Iran is a foreign actor; a hack can
be by a foreign actor), whose Yes prices sum to only 0.13-0.22 on live
Polymarket data fetched 2026-11-14 02:39 UTC. Two consequences:

1. SUM-PULL GATE. The v5 sum-pull multiplies every centre by
   (1 - 0.6*(S-1)/S * pull). At S = 0.09 that is a ~7x upward explosion
   of every centre. Measured: v5 as-is scores 3.408 on live FAA cuts
   vs 0.756 with the pull gated off. The pull is therefore gated on the
   observed sum: full strength when S >= 0.85 (the NVIDIA regime),
   linearly off below S = 0.60, zero for the FAA regime. Cost on the
   practice: piw 0.238129 -> 0.238606 (+0.0005) for a 4.5x FAA rescue.

2. CENTRE BLEED (low-sum families only). Live FAA prices bleed down
   while no attribution news arrives: the family's sum fell 0.556 ->
   0.091 in four hours, every market's 120-min log-drift negative
   (-0.0025 to -0.010/min), still falling in the last hour. The centre
   therefore decays as exp(-0.008 * h), gated on the sum being below
   0.5 (full strength at S = 0, off at S >= 0.5, so the NVIDIA family
   is untouched and the decay switches itself off if attribution news
   lifts the sum), floored at 0.5x the last price so a flat regime
   cannot be underforecast by more than half. Bleed rate saturates
   around 0.008-0.010 on the live cuts (0.010 no better than 0.008).

3. LOW-SUM VOL WINDOW + MEDIAN CENTRE. The 120-min RMS is inflated by
   launch jumps long after the regime calms (FAA RMS 0.024-0.098 vs cap
   0.01), so low-sum families use a 30-min vol window instead
   (FAA 0.585 -> 0.530). And the last tick alone is a noisy centre when
   prices jump in single minutes, so the centre blends the last price
   50/50 with the median of the last 10 minutes (FAA 0.516 -> 0.473).
   Both are gated on the low-sum regime, so the practice is untouched.

4. SUBSET CAP. P(Iran) <= P(foreign actor) logically, so Iran's
   quantiles are capped at foreign's. Small measured gain (+0.0002
   on FAA cuts) but free and always true.

Everything else is the v5 configuration, re-tuned jointly with the
gate (sum-pull 0.60 -> 0.70, which recovers most of the gate's
practice cost):

- Per-market volatility: RMS of 1-min price changes over the last 120
  minutes, floored at 0.0005 and capped at 0.01. Raising the cap was
  tested and hurts on BOTH families (FAA RMS is inflated by launch
  jumps, 0.024-0.098, so a higher cap only widens spreads wrongly).
- Spread grows sub-diffusively as sigma * h**0.35.
- Asymmetric quantile widths: low-outer 1.1, low-inner 0.85,
  high-inner 0.35, high-outer 1.3 times the normal z values.
- Last-move response: the last 1-minute move is faded when up (centre
  shifted back by half the move) and continued when down.
- Sum-gated Jensen median decay (v5): median *= exp(-k * sigma^2 * h/2)
  with k = 96 * clip((S - 0.80)/0.25, 0, 1); on FAA sums it is off.
- No drift toward any level and no centre smoothing (both tested and
  hurt on the NVIDIA cuts). EWMA volatility, wider widths, vol windows
  60/240, alpha 0.30/0.40/0.45, gap off: all tested, all worse on at
  least one family.

Local scores (pooled pinball, lower is better):
- NVIDIA 12-cut 0.247642, practice item-weighted (piw) 0.238606,
  21-cut 0.179341. House baseline practice 0.363589.
- Live FAA cuts (7 checkpoints, 2026-11-13 22:40 to 2026-11-14 01:40
  UTC, answers truncated at the last recorded grid minute): 0.456948
  vs house-baseline-equivalent 0.830227 and v5-as-is 3.407812.
  These cuts are the launch transient, not the final regime; they
  validate the structural fixes, not the absolute level.

Iterations run and rejected (all numbers in VALIDATION.md): per-market
trend drift, family sum-drift, EWMA vol, jump-boosted sigma, logit-space
spreads, stay-mixture quantiles, wider widths, vol windows 60/240,
alpha 0.30/0.40/0.45, gap off, vol caps 0.015-0.03, bleed floors 0.4,
median-blend weights 0.3/0.7/1.0 and windows 5/20, bleed rates above
0.008 (saturated). The fixed family-level bleed wins over adaptive
trend terms because the bleed is a family phenomenon, not a per-market
trend.

Reads every *.in file in $MAKEFUN_INPUT_DIR (else /input) and writes
one <id>.out per case to $MAKEFUN_OUTPUT_DIR (else /output).
Standard library only, no network, deterministic.
"""

import json
import math
import os
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

# Standard normal quantiles at 0.05 / 0.25 / 0.5 / 0.75 / 0.95.
NORM_Z = [-1.644854, -0.67449, 0.0, 0.67449, 1.644854]
# Width multipliers, low-outer / low-inner / high-inner / high-outer.
WIDTH_MULT = [1.1, 0.85, 0.35, 1.3]

VOL_WINDOW = 120      # minutes of 1-min diffs for the RMS volatility
VOL_FLOOR = 0.0005    # minimum per-minute sigma
VOL_CAP = 0.01        # maximum per-minute sigma
ALPHA = 0.35          # spread growth exponent: sigma * h ** ALPHA
SUM_PULL = 0.70       # weight of the cross-market sum pull
PULL_TAU = 60         # minutes over which the sum pull phases in
PULL_LO = 0.60        # sum below which the pull is fully off
PULL_HI = 0.85        # sum above which the pull is at full strength
GAP_UP = 0.5          # fade fraction of the last 1-min move when it is up
GAP_DOWN = -0.5       # continuation fraction when the last move is down
JENSEN_SCALE = 96.0   # median-decay scale (v5)
JENSEN_LO = 0.80      # sum below which the Jensen decay is fully off
JENSEN_HI = 1.05      # sum above which the Jensen decay is at full strength
BLEED_RATE = 0.008    # centre bleed per minute, low-sum families only
BLEED_HI = 0.50       # sum at/above which the bleed is fully off
BLEED_FLOOR = 0.50    # centre never decays below this fraction of last price
VOL_WINDOW_LOW = 30   # vol window for low-sum families (fast regime switch)
CENTRE_MED_W = 0.5    # blend weight of the 10-min median centre (low-sum only)
CENTRE_MED_N = 10     # minutes for the median centre
IRAN_SLUG = "faa-outage-attributed-to-iran"
FOREIGN_SLUG = "faa-outage-attributed-to-a-foreign-actor"


def _clamp6(value):
    return min(1.0, max(0.0, round(value, 6))) + 0.0


def _gate(total, lo, hi):
    """Linear gate: 0 at/below lo, 1 at/above hi."""
    if hi <= lo:
        return 1.0 if total >= lo else 0.0
    return min(1.0, max(0.0, (total - lo) / (hi - lo)))


def _rms_sigma(prices, window=VOL_WINDOW):
    """RMS of 1-min diffs over the last `window` minutes, floored/capped."""
    win = prices[-window - 1:] if len(prices) > window else prices
    diffs = [win[i + 1] - win[i] for i in range(len(win) - 1)]
    if not diffs:
        return VOL_FLOOR
    sigma = math.sqrt(sum(d * d for d in diffs) / len(diffs))
    return min(VOL_CAP, max(VOL_FLOOR, sigma))


def _forecast_case(case):
    horizon = case["horizon_minutes"]
    markets = case["markets"]
    last = [m["prices"][-1] for m in markets]
    total = sum(last)
    # Cross-market sum pull, gated on the observed sum (see docstring).
    pull_gate = _gate(total, PULL_LO, PULL_HI)
    pull_base = SUM_PULL * pull_gate * (total - 1.0) / total if total > 0 else 0.0
    # Sum-gated Jensen median decay (v5 term).
    jensen_gate = _gate(total, JENSEN_LO, JENSEN_HI)
    decay_k = JENSEN_SCALE * jensen_gate
    # Centre bleed, gated the other way: on only when the family sum is
    # far below 1 (non-exclusive family), off once the sum reaches 0.5.
    bleed_gate = min(1.0, max(0.0, (BLEED_HI - total) / BLEED_HI))
    offsets = [NORM_Z[0] * WIDTH_MULT[0], NORM_Z[1] * WIDTH_MULT[1], 0.0,
               NORM_Z[3] * WIDTH_MULT[2], NORM_Z[4] * WIDTH_MULT[3]]
    forecasts = []
    for market in markets:
        prices = market["prices"]
        centre0 = prices[-1]
        if bleed_gate and CENTRE_MED_W:
            # Jump smoothing (low-sum families only): blend the last price
            # with the median of the last CENTRE_MED_N minutes. FAA prices
            # jump in single minutes; the last tick alone is a noisy centre.
            w10 = sorted(prices[-CENTRE_MED_N:])
            med10 = (w10[len(w10) // 2] if len(w10) % 2 == 1
                     else 0.5 * (w10[len(w10) // 2 - 1] + w10[len(w10) // 2]))
            centre0 = (1 - CENTRE_MED_W) * centre0 + CENTRE_MED_W * med10
        # Fast vol window for low-sum families: the 120-min RMS is
        # inflated by launch jumps long after the regime calms.
        vol_win = VOL_WINDOW_LOW if bleed_gate else VOL_WINDOW
        sigma = _rms_sigma(prices, vol_win)
        # Last 1-minute move, faded when up / continued when down.
        move = centre0 - prices[-2] if len(prices) >= 2 else 0.0
        gap = (GAP_UP if move >= 0 else GAP_DOWN) * move
        rows = []
        for h in range(1, horizon + 1):
            spread = sigma * (h ** ALPHA)
            pull = 1.0 - math.exp(-h / PULL_TAU)
            centre = centre0 * (1.0 - pull_base * pull) - gap
            if bleed_gate:
                bleed = math.exp(-BLEED_RATE * bleed_gate * h)
                centre *= max(BLEED_FLOOR, bleed)
            median = centre * math.exp(-decay_k * sigma * sigma * h / 2.0)
            row = [_clamp6(centre + z * spread) for z in offsets]
            row[2] = _clamp6(median)
            row.sort()
            rows.append(row)
        forecasts.append({"id": market["id"], "q": rows})
    # Logical constraint (FAA family only): attributing the outage to Iran
    # implies attributing it to a foreign actor, so P(Iran) <= P(foreign
    # actor) at every minute. Cap Iran's quantiles at foreign's.
    by_slug = {m["slug"]: m["id"] for m in markets}
    iran = by_slug.get(IRAN_SLUG)
    foreign = by_slug.get(FOREIGN_SLUG)
    if iran and foreign:
        fmap = {f["id"]: f["q"] for f in forecasts}
        if iran in fmap and foreign in fmap:
            for h in range(horizon):
                for j in range(5):
                    if fmap[iran][h][j] > fmap[foreign][h][j]:
                        fmap[iran][h][j] = fmap[foreign][h][j]
    return {"forecasts": forecasts}


def main():
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    for in_path in sorted(in_dir.glob("*.in")):
        case = json.loads(in_path.read_text(encoding="utf-8"))
        result = _forecast_case(case)
        out_path = out_dir / (in_path.stem + ".out")
        out_path.write_text(json.dumps(result, separators=(",", ":")) + "\n",
                            encoding="utf-8")


if __name__ == "__main__":
    main()
