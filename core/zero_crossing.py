"""
core/zero_crossing.py
Interpolated zero-crossing detection and exclusion-zone computation.

Public API
----------
detect(samples)                  -> list[float]
    All interpolated ZC positions in the array.

compute_exclusions(zc_list, min_samples, max_samples)
    -> (excluded_min, excluded_max)
    Both are list[tuple[float, float]] of (start, end) sample ranges.

filter_usable(zc_list, excluded_min, excluded_max, start_pad, end_pad, total)
    -> list[float]
    ZCs that are inside the work region and not inside any excluded zone.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect(samples: np.ndarray) -> list[float]:
    """Return interpolated zero-crossing positions for *samples*.

    For each adjacent pair where a sign change occurs:
        zc = i + s[i] / (s[i] - s[i+1])

    Exact zeros (s[i] == 0.0) are included as integer positions, but only
    if they are not already captured by an adjacent sign-change crossing,
    to avoid duplicates.

    Returns a sorted list of float sample positions.
    """
    n = len(samples)
    if n < 2:
        return []

    crossings: list[float] = []

    # Sign-change crossings (the main case)
    for i in range(n - 1):
        a = samples[i]
        b = samples[i + 1]
        if a * b < 0.0:
            # Linear interpolation: where does the line cross zero?
            crossings.append(i + a / (a - b))
        elif a == 0.0:
            # Exact zero — include unless the previous sample was also zero
            # (flat zero region — only mark the first sample of the run)
            if i == 0 or samples[i - 1] != 0.0:
                crossings.append(float(i))

    # Handle last sample being exactly zero
    if n > 0 and samples[-1] == 0.0 and (n < 2 or samples[-2] != 0.0):
        crossings.append(float(n - 1))

    crossings.sort()
    return crossings


# ---------------------------------------------------------------------------
# Exclusion zones
# ---------------------------------------------------------------------------

def compute_exclusions(
    zc_list: list[float],
    min_samples: int,
    max_samples: int,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Compute min-excluded and max-excluded regions from a ZC list.

    Min exclusion
    -------------
    Any pair of consecutive ZCs that are closer than *min_samples* triggers
    a min-excluded zone.  Contiguous runs of such close-packed ZCs are merged
    into a single region.  The zone spans from the first ZC of the run to the
    last, with a half-min_samples buffer on each side so the overlay visually
    covers the problematic neighbourhood.

    Max exclusion
    -------------
    Any gap between consecutive ZCs that is wider than *max_samples* is a
    max-excluded zone spanning exactly that gap.

    Parameters
    ----------
    zc_list     : sorted list of interpolated ZC positions
    min_samples : spacing threshold for min exclusion
    max_samples : spacing threshold for max exclusion

    Returns
    -------
    excluded_min : list of (start, end) float sample pairs
    excluded_max : list of (start, end) float sample pairs
    """
    excluded_min: list[tuple[float, float]] = []
    excluded_max: list[tuple[float, float]] = []

    if len(zc_list) < 2:
        return excluded_min, excluded_max

    half_min = min_samples / 2.0

    # --- Min exclusion: find runs of close-packed ZCs ---
    in_run = False
    run_start = 0.0

    for i in range(len(zc_list) - 1):
        gap = zc_list[i + 1] - zc_list[i]
        if gap < min_samples:
            if not in_run:
                in_run = True
                run_start = zc_list[i]
        else:
            if in_run:
                in_run = False
                run_end = zc_list[i]
                excluded_min.append((
                    max(0.0, run_start - half_min),
                    run_end + half_min,
                ))

    # Close an open run at the end of the list
    if in_run:
        run_end = zc_list[-1]
        excluded_min.append((
            max(0.0, run_start - half_min),
            run_end + half_min,
        ))

    # --- Max exclusion: gaps wider than max_samples ---
    for i in range(len(zc_list) - 1):
        gap = zc_list[i + 1] - zc_list[i]
        if gap > max_samples:
            excluded_max.append((zc_list[i], zc_list[i + 1]))

    return excluded_min, excluded_max


# ---------------------------------------------------------------------------
# Usable ZC filter
# ---------------------------------------------------------------------------

def filter_usable(
    zc_list: list[float],
    excluded_min: list[tuple[float, float]],
    excluded_max: list[tuple[float, float]],
    start_pad: int,
    end_pad: int,
    total_samples: int,
) -> list[float]:
    """Return ZCs that are inside the work region and not in any excluded zone.

    Work region: [start_pad, total_samples - end_pad]
    A ZC is excluded if it falls inside any excluded_min or excluded_max range.
    """
    lo = float(start_pad)
    hi = float(total_samples - end_pad)

    # Build a fast exclusion test: merge all exclusion ranges into one list
    all_excluded: list[tuple[float, float]] = excluded_min + excluded_max

    usable: list[float] = []
    for zc in zc_list:
        if zc < lo or zc > hi:
            continue
        if any(s <= zc <= e for s, e in all_excluded):
            continue
        usable.append(zc)

    return usable
