"""
core/splitter.py
WaveRegion selection algorithm.

select_regions(usable_zcs, num_waves, start_pad, end_pad, total_samples,
               edge_mode)
    -> list[WaveRegion]

usable_zcs is now list[tuple[float, bool]] from zero_crossing.filter_usable().
edge_mode controls which ZCs may serve as the *central* ZC of a region:
  'none'    -- any ZC
  'rising'  -- only rising-edge ZCs as center
  'falling' -- only falling-edge ZCs as center

Begin and end ZCs of a region are unrestricted by edge_mode.
"""

from __future__ import annotations

import math
from typing import Optional

from core.state import WaveRegion


def select_regions(
    usable_zcs: list[tuple[float, bool]],
    num_waves: int,
    start_pad: int,
    end_pad: int,
    total_samples: int,
    edge_mode: str = "none",
) -> list[WaveRegion]:
    """Select up to *num_waves* evenly-spaced WaveRegions.

    Algorithm
    ---------
    1. Build candidate triplets (begin, center, end) from all adjacent
       triples in usable_zcs.  For a triplet to be valid, its center ZC
       must match edge_mode (if not 'none').  Begin/end ZCs are unrestricted.

    2. Compute num_waves evenly-spaced ideal positions across the work region.

    3. Greedy nearest-match: each ideal position claims the triplet whose
       center ZC is nearest.

    4. Deduplicate: no two regions may share the same center ZC (rounded int).
       On collision keep the closer one.

    5. Return sorted list of WaveRegion objects.
    """
    if len(usable_zcs) < 3 or num_waves < 1:
        return []

    work_lo = float(start_pad)
    work_hi = float(total_samples - end_pad)

    # ------------------------------------------------------------------
    # Step 1: candidate triplets
    # ------------------------------------------------------------------
    # A triplet is (begin_pos, center_pos, end_pos, begin_rising, center_rising)
    # center must satisfy edge_mode; begin/end are free.
    candidates: list[tuple[float, float, float]] = []
    n = len(usable_zcs)
    for i in range(n - 2):
        b_pos, _         = usable_zcs[i]
        c_pos, c_rising  = usable_zcs[i + 1]
        e_pos, _         = usable_zcs[i + 2]

        if edge_mode == "rising"  and not c_rising:
            continue
        if edge_mode == "falling" and     c_rising:
            continue

        candidates.append((b_pos, c_pos, e_pos))

    if not candidates:
        return []

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
    assignments: list[Optional[tuple[float, float, float, float]]] = []

    for ideal in ideal_positions:
        best: Optional[tuple[float, float, float]] = None
        best_dist = math.inf
        for trip in candidates:
            dist = abs(trip[1] - ideal)
            if dist < best_dist:
                best_dist = dist
                best = trip
        if best is not None:
            assignments.append((best[0], best[1], best[2], best_dist))
        else:
            assignments.append(None)

    # ------------------------------------------------------------------
    # Step 4: deduplicate by center ZC
    # ------------------------------------------------------------------
    center_claimed: dict[int, int] = {}

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
                    assignments[prev_idx] = None
                    center_claimed[key] = idx
                else:
                    assignments[idx] = None
        else:
            center_claimed[key] = idx

    # ------------------------------------------------------------------
    # Step 5: build WaveRegion objects
    # ------------------------------------------------------------------
    regions: list[WaveRegion] = []
    for assignment in assignments:
        if assignment is None:
            continue
        begin_zc, center_zc, end_zc, _ = assignment
        regions.append(WaveRegion(
            begin_zc     = begin_zc,
            center_zc    = center_zc,
            end_zc       = end_zc,
            begin_sample = math.floor(begin_zc),
            end_sample   = math.ceil(end_zc),
        ))

    regions.sort(key=lambda r: r.begin_zc)
    return regions
