"""
core/zero_crossing.py
Interpolated zero-crossing detection, direction tagging, and exclusion zones.

Public API
----------
detect(samples)
    -> list[tuple[float, bool]]
    All interpolated ZC positions with direction: True = rising, False = falling.

compute_exclusions(zc_list, min_samples, max_samples)
    -> (excluded_min, excluded_max)

filter_usable(zc_list, excluded_min, excluded_max, start_pad, end_pad,
              total_samples, edge_mode)
    -> list[tuple[float, bool]]
    ZCs inside the work region, not in excluded zones, matching edge_mode.
    edge_mode: 'none' | 'rising' | 'falling'
"""

from __future__ import annotations
import numpy as np


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect(samples: np.ndarray) -> list[tuple[float, bool]]:
    """Return interpolated zero-crossing positions with direction.

    Each entry is (position, is_rising) where:
      is_rising = True  -> signal goes from negative to positive (rising edge)
      is_rising = False -> signal goes from positive to negative (falling edge)

    Interpolation formula for sign changes:
        zc_pos = i + s[i] / (s[i] - s[i+1])

    Exact zeros: direction inferred from the sign of the next non-zero sample.
    """
    n = len(samples)
    if n < 2:
        return []

    crossings: list[tuple[float, bool]] = []

    for i in range(n - 1):
        a = samples[i]
        b = samples[i + 1]
        if a * b < 0.0:
            pos = i + a / (a - b)
            is_rising = b > a   # negative->positive = rising
            crossings.append((pos, is_rising))
        elif a == 0.0:
            if i == 0 or samples[i - 1] != 0.0:
                # Direction: look ahead for next non-zero
                is_rising = True
                for j in range(i + 1, min(i + 10, n)):
                    if samples[j] != 0.0:
                        is_rising = samples[j] > 0.0
                        break
                crossings.append((float(i), is_rising))

    if n > 0 and samples[-1] == 0.0 and (n < 2 or samples[-2] != 0.0):
        is_rising = samples[-2] < 0.0 if n >= 2 else True
        crossings.append((float(n - 1), is_rising))

    crossings.sort(key=lambda x: x[0])
    return crossings


# ---------------------------------------------------------------------------
# Exclusion zones (operate on position only, direction-agnostic)
# ---------------------------------------------------------------------------

def compute_exclusions(
    zc_list: list[tuple[float, bool]],
    min_samples: int,
    max_samples: int,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Compute min/max excluded regions from a ZC list.

    Parameters
    ----------
    zc_list     : list of (position, is_rising) from detect()
    min_samples : ZC spacing below this -> min-excluded
    max_samples : ZC gap above this     -> max-excluded

    Returns
    -------
    excluded_min, excluded_max : list of (start, end) float sample pairs
    """
    excluded_min: list[tuple[float, float]] = []
    excluded_max: list[tuple[float, float]] = []

    positions = [zc[0] for zc in zc_list]
    if len(positions) < 2:
        return excluded_min, excluded_max

    half_min = min_samples / 2.0
    in_run   = False
    run_start = 0.0

    for i in range(len(positions) - 1):
        gap = positions[i + 1] - positions[i]
        if gap < min_samples:
            if not in_run:
                in_run    = True
                run_start = positions[i]
        else:
            if in_run:
                in_run  = False
                run_end = positions[i]
                excluded_min.append((
                    max(0.0, run_start - half_min),
                    run_end + half_min,
                ))

    if in_run:
        excluded_min.append((
            max(0.0, run_start - half_min),
            positions[-1] + half_min,
        ))

    for i in range(len(positions) - 1):
        gap = positions[i + 1] - positions[i]
        if gap > max_samples:
            excluded_max.append((positions[i], positions[i + 1]))

    return excluded_min, excluded_max


# ---------------------------------------------------------------------------
# Usable ZC filter
# ---------------------------------------------------------------------------

def filter_usable(
    zc_list: list[tuple[float, bool]],
    excluded_min: list[tuple[float, float]],
    excluded_max: list[tuple[float, float]],
    start_pad: int,
    end_pad: int,
    total_samples: int,
    edge_mode: str = "none",
) -> list[tuple[float, bool]]:
    """Return ZCs inside the work region, not excluded, matching edge_mode.

    edge_mode : 'none'    -- no direction filter (default, all crossings)
                'rising'  -- only rising-edge crossings (neg->pos)
                'falling' -- only falling-edge crossings (pos->neg)

    Work region: [start_pad, total_samples - end_pad]
    """
    lo = float(start_pad)
    hi = float(total_samples - end_pad)
    all_excluded = excluded_min + excluded_max

    usable: list[tuple[float, bool]] = []
    for pos, is_rising in zc_list:
        if pos < lo or pos > hi:
            continue
        if any(s <= pos <= e for s, e in all_excluded):
            continue
        if edge_mode == "rising" and not is_rising:
            continue
        if edge_mode == "falling" and is_rising:
            continue
        usable.append((pos, is_rising))

    return usable
