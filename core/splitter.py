"""
core/splitter.py
WaveRegion selection algorithm.

Takes a list of usable zero-crossings and selects up to *num_waves*
evenly-spaced WaveRegion objects, each with a unique central ZC.

Public API
----------
select_regions(usable_zcs, num_waves, start_pad, end_pad, total_samples)
    -> list[WaveRegion]
"""

from __future__ import annotations

import math
from typing import Optional

from core.state import WaveRegion


def select_regions(
    usable_zcs: list[float],
    num_waves: int,
    start_pad: int,
    end_pad: int,
    total_samples: int,
) -> list[WaveRegion]:
    """Select up to *num_waves* evenly-spaced WaveRegions from *usable_zcs*.

    Algorithm
    ---------
    1.  Enumerate all valid candidate triplets (begin, center, end) from the
        usable ZC list.  A triplet is valid when begin < center < end and all
        three ZCs are in the work region.

    2.  Compute *num_waves* evenly-spaced ideal positions across the work
        region [start_pad, total_samples - end_pad].

    3.  For each ideal position, find the candidate triplet whose center ZC
        is closest to that ideal position.

    4.  Deduplicate: no two selected regions may share the same center ZC
        (compared by rounded integer index).  On collision, keep the one with
        the smaller distance from its ideal position; drop the other.

    5.  Return the survivors as an ordered list of WaveRegion objects.
        The count may be less than *num_waves* if insufficient triplets exist.

    Parameters
    ----------
    usable_zcs    : sorted list of usable (non-excluded, in-bounds) ZC positions
    num_waves     : requested number of output waveforms
    start_pad     : first sample of the work region
    end_pad       : samples excluded at the end
    total_samples : total length of the source audio array

    Returns
    -------
    list[WaveRegion] sorted by begin_zc
    """
    if len(usable_zcs) < 3 or num_waves < 1:
        return []

    work_lo = float(start_pad)
    work_hi = float(total_samples - end_pad)

    # ------------------------------------------------------------------
    # Step 1: build candidate triplets
    # ------------------------------------------------------------------
    # Each triplet: (begin_zc, center_zc, end_zc)
    # All adjacent triplets from the usable list.  Because usable_zcs is
    # already filtered to the work region, every triplet is in-bounds.
    candidates: list[tuple[float, float, float]] = []
    n = len(usable_zcs)
    for i in range(n - 2):
        candidates.append((usable_zcs[i], usable_zcs[i + 1], usable_zcs[i + 2]))

    if not candidates:
        return []

    # Pre-index candidates by center ZC for fast lookup
    # center_map: rounded_int_center -> (triplet, index_in_candidates)
    # We keep all candidates; the greedy step picks the nearest.

    # ------------------------------------------------------------------
    # Step 2: ideal positions
    # ------------------------------------------------------------------
    if num_waves == 1:
        ideal_positions = [(work_lo + work_hi) / 2.0]
    else:
        step = (work_hi - work_lo) / (num_waves - 1)
        ideal_positions = [work_lo + i * step for i in range(num_waves)]

    # ------------------------------------------------------------------
    # Step 3: nearest-match assignment
    # ------------------------------------------------------------------
    # For each ideal position find the candidate whose center is closest
    assignments: list[Optional[tuple[float, float, float, float]]] = []
    # Each entry: (begin, center, end, distance_from_ideal) or None

    for ideal in ideal_positions:
        best: Optional[tuple[float, float, float]] = None
        best_dist = math.inf
        for trip in candidates:
            dist = abs(trip[1] - ideal)   # distance of center from ideal
            if dist < best_dist:
                best_dist = dist
                best = trip
        if best is not None:
            assignments.append((best[0], best[1], best[2], best_dist))
        else:
            assignments.append(None)

    # ------------------------------------------------------------------
    # Step 4: deduplicate by center ZC (rounded to int)
    # ------------------------------------------------------------------
    # Keep track of which rounded center ZCs have been claimed.
    # On collision, the one with the larger distance is dropped (set None).
    center_claimed: dict[int, int] = {}  # rounded_center -> index in assignments

    for idx, assignment in enumerate(assignments):
        if assignment is None:
            continue
        _, center, _, dist = assignment
        key = round(center)
        if key in center_claimed:
            prev_idx = center_claimed[key]
            prev = assignments[prev_idx]
            if prev is None:
                center_claimed[key] = idx
            else:
                _, _, _, prev_dist = prev
                if dist < prev_dist:
                    # New one is closer — drop the previous
                    assignments[prev_idx] = None
                    center_claimed[key] = idx
                else:
                    # Previous is closer — drop the new one
                    assignments[idx] = None
        else:
            center_claimed[key] = idx

    # ------------------------------------------------------------------
    # Step 5: build WaveRegion objects from survivors
    # ------------------------------------------------------------------
    regions: list[WaveRegion] = []
    for assignment in assignments:
        if assignment is None:
            continue
        begin_zc, center_zc, end_zc, _ = assignment
        regions.append(WaveRegion(
            begin_zc    = begin_zc,
            center_zc   = center_zc,
            end_zc      = end_zc,
            begin_sample= math.floor(begin_zc),
            end_sample  = math.ceil(end_zc),
        ))

    # Sort by position (should already be ordered, but be defensive)
    regions.sort(key=lambda r: r.begin_zc)
    return regions
