#!/usr/bin/env python3
"""Paired small-sample statistics for mimic candidate comparisons.

Input JSON is a list of paired items, each ``{"treatment": x, "baseline": y}``
(lower composite is better, so the per-item improvement delta is baseline -
treatment). Follows the small-n discipline from the loop research:

  - per-item paired deltas,
  - BCa bootstrap CI (n=2000, seeded),
  - sign-flip permutation test (exact when items <= 12, else 20k seeded),
  - verdict ``improved`` iff CI lower bound > 0 AND p < 0.05.

Deterministic given the seed. Under-claims by default: any construct-validity
shortfall (empty, single item, zero variance) yields improved=false.
"""

import argparse
import itertools
import json
import math
import random
import statistics
import sys
from pathlib import Path

BOOTSTRAP_N = 2000
PERM_N = 20000
EXACT_PERM_MAX = 12


def deltas(items):
    return [it["baseline"] - it["treatment"] for it in items]


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    idx = q * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _normal_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _normal_ppf(p):
    # Acklam's rational approximation to the inverse normal CDF.
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def bca_ci(sample, seed, alpha=0.05):
    """BCa bootstrap CI for the mean of ``sample``."""
    n = len(sample)
    if n < 2:
        return (0.0, 0.0)
    theta_hat = statistics.mean(sample)
    rng = random.Random(seed)
    boot = []
    for _ in range(BOOTSTRAP_N):
        resample = [sample[rng.randrange(n)] for _ in range(n)]
        boot.append(statistics.mean(resample))
    boot.sort()
    n_less = sum(1 for b in boot if b < theta_hat)
    prop = n_less / BOOTSTRAP_N
    if prop <= 0.0 or prop >= 1.0:
        # Degenerate acceleration; fall back to the percentile interval.
        return (_percentile(boot, alpha / 2), _percentile(boot, 1 - alpha / 2))
    z0 = _normal_ppf(prop)
    # Jackknife acceleration.
    jack = []
    total = sum(sample)
    for i in range(n):
        jack.append((total - sample[i]) / (n - 1))
    jbar = statistics.mean(jack)
    num = sum((jbar - x) ** 3 for x in jack)
    den = 6.0 * (sum((jbar - x) ** 2 for x in jack) ** 1.5)
    acc = num / den if den else 0.0
    z_lo, z_hi = _normal_ppf(alpha / 2), _normal_ppf(1 - alpha / 2)

    def adjust(z):
        return _normal_cdf(z0 + (z0 + z) / (1 - acc * (z0 + z)))

    return (_percentile(boot, adjust(z_lo)), _percentile(boot, adjust(z_hi)))


def sign_flip_p(sample, seed):
    """Two-sided sign-flip permutation test that the mean delta is 0."""
    n = len(sample)
    if n == 0:
        return 1.0
    observed = abs(sum(sample))
    if n <= EXACT_PERM_MAX:
        count = 0
        total = 0
        for signs in itertools.product((1, -1), repeat=n):
            total += 1
            if abs(sum(s * x for s, x in zip(signs, sample))) >= observed - 1e-12:
                count += 1
        return count / total
    rng = random.Random(seed)
    count = 0
    for _ in range(PERM_N):
        flipped = sum(x if rng.random() < 0.5 else -x for x in sample)
        if abs(flipped) >= observed - 1e-12:
            count += 1
    return (count + 1) / (PERM_N + 1)


def analyze(items, seed):
    d = deltas(items)
    n = len(d)
    mean_delta = statistics.mean(d) if d else 0.0
    ci_low, ci_high = bca_ci(d, seed) if n >= 2 else (0.0, 0.0)
    p = sign_flip_p(d, seed) if n >= 1 else 1.0
    improved = bool(n >= 2 and ci_low > 0 and p < 0.05)
    return {
        "n": n,
        "mean_delta": mean_delta,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p,
        "improved": improved,
        "seed": seed,
    }


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("data", help="JSON list of {treatment, baseline} pairs")
    p.add_argument("--seed", type=int, default=20240607)
    return p.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    path = Path(args.data)
    if not path.exists():
        print(f"missing data file: {path}", file=sys.stderr)
        return 2
    items = json.loads(path.read_text())
    result = analyze(items, args.seed)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
