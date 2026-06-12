"""
core/modifier.py
Per-waveform Offset, Stretch, and Suppress transforms.

Each transform has a 'begin' and 'end' value that interpolates linearly
across all waveforms:
    param[k] = begin + (k / (K-1)) * (end - begin)

All transforms operate on raw float64 sample slices extracted from the
source audio.  They are applied in order before the length-normalisation
stretch and before filtering.

Public API
----------
apply_all(raw_samples, regions, params, sr) -> list[np.ndarray]
    Apply offset, stretch, suppress to every region in *regions*.
    Returns a list of float64 arrays (variable length, pre-stretch).

interpolate_param(begin, end, k, K) -> float
    Linear interpolation helper, exported for testing.
"""

from __future__ import annotations

import math
import logging
import numpy as np

from core.state import WaveRegion
from core import stretcher as _stretcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_all(
    raw_samples: np.ndarray,
    regions: list[WaveRegion],
    offset_begin:   float, offset_end:   float,
    stretch_begin:  float, stretch_end:  float,
    suppress_begin: float, suppress_end: float,
    sr: int = 44100,
) -> list[np.ndarray]:
    """Apply Offset, Stretch, Suppress to each region.

    Returns one float64 array per region (variable length).
    The caller is responsible for the subsequent length-normalisation stretch.
    """
    K = len(regions)
    result: list[np.ndarray] = []

    for k, region in enumerate(regions):
        t = k / max(K - 1, 1)

        off_val  = _interp(offset_begin,   offset_end,   t)
        str_val  = _interp(stretch_begin,  stretch_end,  t)
        sup_val  = _interp(suppress_begin, suppress_end, t)

        # 1. Slice the raw audio for this region (with offset applied)
        chunk = _apply_offset(raw_samples, region, off_val)

        # 2. Stretch (asymmetric half-compression)
        chunk = _apply_stretch(chunk, region, off_val, str_val, sr)

        # 3. Suppress (volume ramp on one half)
        chunk = _apply_suppress(chunk, sup_val)

        result.append(chunk)

    return result


def interpolate_param(begin: float, end: float, k: int, K: int) -> float:
    """Linear interpolation: 0.0 at k=0, 1.0 at k=K-1."""
    t = k / max(K - 1, 1)
    return begin + t * (end - begin)


# ---------------------------------------------------------------------------
# Individual transforms
# ---------------------------------------------------------------------------

def _interp(begin: float, end: float, t: float) -> float:
    return begin + t * (end - begin)


def _apply_offset(
    raw: np.ndarray,
    region: WaveRegion,
    offset: float,
) -> np.ndarray:
    """Shift the sample window around the central ZC.

    offset  = 0.0  -> window is [begin_zc, end_zc]  (centred on center_zc)
    offset  = +0.5 -> window shifts forward: center_zc moves to start of frame
    offset  = -0.5 -> window shifts backward: center_zc moves to end of frame

    The shift amount scales with the half-cycle length:
      - Positive offset: shift = offset * (center_zc - begin_zc)
      - Negative offset: shift = offset * (end_zc - center_zc)
    The integer slice is adjusted accordingly; the center ZC identity is
    unchanged.
    """
    if abs(offset) < 1e-6:
        s0 = region.begin_sample
        s1 = region.end_sample
    else:
        if offset > 0:
            half = region.center_zc - region.begin_zc
            shift = offset * half
        else:
            half = region.end_zc - region.center_zc
            shift = offset * half   # negative shift, moves window back

        new_begin = region.begin_zc + shift
        new_end   = region.end_zc   + shift

        s0 = max(0, int(math.floor(new_begin)))
        s1 = min(len(raw), int(math.ceil(new_end)))

    if s1 <= s0:
        return np.zeros(1, dtype=np.float64)

    return raw[s0:s1].astype(np.float64)


def _apply_stretch(
    chunk: np.ndarray,
    region: WaveRegion,
    offset: float,
    stretch_val: float,
    sr: int,
) -> np.ndarray:
    """Asymmetric time-stretch of the two halves around the central ZC.

    stretch_val = 0.0  -> no change
    stretch_val = +0.5 -> first half compressed 50%, second half stretched
    stretch_val = -0.5 -> first half stretched, second half compressed 50%

    The split point in *chunk* is derived from how far the center_zc sits
    inside the (possibly offset) window.
    """
    if abs(stretch_val) < 1e-6:
        return chunk

    n = len(chunk)
    if n < 4:
        return chunk

    # Find where the center ZC lands within the chunk.
    # After offset, the window started at new_begin (float).
    if abs(offset) < 1e-6:
        window_start = float(region.begin_sample)
    else:
        if offset > 0:
            half = region.center_zc - region.begin_zc
            shift = offset * half
        else:
            half = region.end_zc - region.center_zc
            shift = offset * half
        window_start = region.begin_zc + shift

    center_in_chunk = int(round(region.center_zc - window_start))
    center_in_chunk = max(1, min(n - 1, center_in_chunk))

    first  = chunk[:center_in_chunk]
    second = chunk[center_in_chunk:]

    if len(first) < 2 or len(second) < 2:
        return chunk

    if stretch_val > 0:
        # First half compressed, second stretched
        r_first  = 1.0 - stretch_val          # < 1 -> shorter
        r_second = len(first) * (1.0 - r_first) / len(second) + 1.0
    else:
        # First half stretched, second compressed
        r_second = 1.0 + stretch_val           # < 1 -> shorter (stretch_val < 0)
        r_first  = len(second) * (1.0 - r_second) / len(first) + 1.0

    r_first  = float(np.clip(r_first,  0.05, 20.0))
    r_second = float(np.clip(r_second, 0.05, 20.0))

    first_s  = _stretcher.stretch(first,  r_first,  sr)
    second_s = _stretcher.stretch(second, r_second, sr)

    return np.concatenate([first_s, second_s])


def _apply_suppress(chunk: np.ndarray, suppress_val: float) -> np.ndarray:
    """Volume-ramp one half of the waveform.

    suppress_val = 0.0   -> no change
    suppress_val = +1.0  -> first half fully attenuated (fade 1->0 across first half)
    suppress_val = -1.0  -> second half fully attenuated (fade 0->1... wait, see below)

    The ramp goes from 1.0 at the zero-crossing boundary to (1 - |suppress|)
    at the far edge of the affected half, so:
      - At +1.0: first half ramps from 1.0 (at center ZC) down to 0.0 (at begin)
      - At -1.0: second half ramps from 1.0 (at center ZC) down to 0.0 (at end)

    The center ZC itself always stays at its natural amplitude (it's at the
    boundary between halves).
    """
    if abs(suppress_val) < 1e-6:
        return chunk

    n = len(chunk)
    if n < 2:
        return chunk

    out = chunk.copy()
    mid = n // 2
    scale = 1.0 - abs(suppress_val)   # 0.0 = fully attenuated, 1.0 = unchanged

    if suppress_val > 0:
        # Attenuate first half: ramp from scale (at sample 0) to 1.0 (at mid)
        ramp = np.linspace(scale, 1.0, mid, endpoint=False)
        out[:mid] *= ramp
    else:
        # Attenuate second half: ramp from 1.0 (at mid) to scale (at end)
        ramp = np.linspace(1.0, scale, n - mid)
        out[mid:] *= ramp

    return out
