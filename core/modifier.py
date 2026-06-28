"""
core/modifier.py
Per-waveform Offset, Stretch, Suppress, and Distribute transforms.

Each transform has a 'begin' and 'end' value that interpolates linearly
across all waveforms:
    param[k] = begin + (k / (K-1)) * (end - begin)

All transforms operate on raw float64 sample slices extracted from the
source audio.  They are applied in order before the length-normalisation
resample and before filtering.

Public API
----------
apply_all(raw_samples, regions, ..., sr) -> list[np.ndarray]
    Apply offset, stretch, suppress, distribute to every region.
    Returns a list of float64 arrays (variable length, pre-resample).

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
    offset_begin:     float, offset_end:     float,
    stretch_begin:    float, stretch_end:    float,
    suppress_begin:   float, suppress_end:   float,
    distribute_begin: float, distribute_end: float,
    sr: int = 44100,
) -> list[np.ndarray]:
    """Apply Offset, Stretch, Suppress, Distribute to each region.

    Returns one float64 array per region (variable length).
    The caller is responsible for the subsequent length-normalisation resample.
    """
    K = len(regions)
    result: list[np.ndarray] = []

    for k, region in enumerate(regions):
        t = k / max(K - 1, 1)

        off_val  = _interp(offset_begin,     offset_end,     t)
        str_val  = _interp(stretch_begin,    stretch_end,    t)
        sup_val  = _interp(suppress_begin,   suppress_end,   t)
        dis_val  = _interp(distribute_begin, distribute_end, t)

        # 1. Offset: slice raw audio with window shift applied.
        #    Also compute where the center ZC lands in the chunk (float index).
        chunk, center_in_chunk = _apply_offset(raw_samples, region, off_val)

        # 2. Stretch: asymmetric half-compression via Rubber Band.
        #    Returns updated chunk and updated center position.
        chunk, center_in_chunk = _apply_stretch(
            chunk, region, off_val, str_val, center_in_chunk, sr
        )

        # 3. Suppress: volume ramp on one half (uses center_in_chunk).
        chunk = _apply_suppress(chunk, sup_val, center_in_chunk)

        # 4. Distribute: resample each half to a new proportion of total length.
        chunk = _apply_distribute(chunk, dis_val, center_in_chunk)

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
) -> tuple[np.ndarray, float]:
    """Shift the sample window around the central ZC.

    Returns (chunk, center_in_chunk) where center_in_chunk is the float
    index of the expected central ZC position within the returned chunk.

    offset  = 0.0  -> window is [begin_zc, end_zc]
    offset  = +0.5 -> window shifts forward: center_zc moves toward start
    offset  = -0.5 -> window shifts backward: center_zc moves toward end
    """
    if abs(offset) < 1e-6:
        s0 = region.begin_sample
        s1 = region.end_sample
        center_in_chunk = region.center_zc - float(s0)
    else:
        if offset > 0:
            half = region.center_zc - region.begin_zc
            shift = offset * half
        else:
            half = region.end_zc - region.center_zc
            shift = offset * half

        new_begin = region.begin_zc + shift
        new_end   = region.end_zc   + shift

        s0 = max(0, int(math.floor(new_begin)))
        s1 = min(len(raw), int(math.ceil(new_end)))
        center_in_chunk = region.center_zc - float(s0)

    if s1 <= s0:
        return np.zeros(1, dtype=np.float64), 0.0

    chunk = raw[s0:s1].astype(np.float64)
    # Clamp center to valid range
    center_in_chunk = max(0.0, min(float(len(chunk) - 1), center_in_chunk))
    return chunk, center_in_chunk


def _apply_stretch(
    chunk: np.ndarray,
    region: WaveRegion,
    offset: float,
    stretch_val: float,
    center_in_chunk: float,
    sr: int,
) -> tuple[np.ndarray, float]:
    """Asymmetric time-stretch of the two halves around the central ZC.

    Returns (chunk, new_center_in_chunk).

    stretch_val = 0.0  -> no change
    stretch_val = +0.5 -> first half compressed 50%, second half stretched
    stretch_val = -0.5 -> first half stretched, second half compressed 50%
    """
    if abs(stretch_val) < 1e-6:
        return chunk, center_in_chunk

    n = len(chunk)
    if n < 4:
        return chunk, center_in_chunk

    split = int(round(center_in_chunk))
    split = max(1, min(n - 1, split))

    first  = chunk[:split]
    second = chunk[split:]

    if len(first) < 2 or len(second) < 2:
        return chunk, center_in_chunk

    if stretch_val > 0:
        r_first  = 1.0 - stretch_val
        r_second = len(first) * (1.0 - r_first) / len(second) + 1.0
    else:
        r_second = 1.0 + stretch_val
        r_first  = len(second) * (1.0 - r_second) / len(first) + 1.0

    r_first  = float(np.clip(r_first,  0.05, 20.0))
    r_second = float(np.clip(r_second, 0.05, 20.0))

    first_s  = _stretcher.stretch(first,  r_first,  sr)
    second_s = _stretcher.stretch(second, r_second, sr)

    new_center = float(len(first_s))   # center is at the join
    return np.concatenate([first_s, second_s]), new_center


def _apply_suppress(
    chunk: np.ndarray,
    suppress_val: float,
    center_in_chunk: float,
) -> np.ndarray:
    """Volume-ramp one half of the waveform.

    suppress_val = 0.0   -> no change
    suppress_val = +1.0  -> first half fully attenuated (ramp 0->1 toward center)
    suppress_val = -1.0  -> second half fully attenuated (ramp 1->0 away from center)
    """
    if abs(suppress_val) < 1e-6:
        return chunk

    n = len(chunk)
    if n < 2:
        return chunk

    mid   = int(round(center_in_chunk))
    mid   = max(1, min(n - 1, mid))
    out   = chunk.copy()
    scale = 1.0 - abs(suppress_val)

    if suppress_val > 0:
        ramp = np.linspace(scale, 1.0, mid, endpoint=False)
        out[:mid] *= ramp
    else:
        ramp = np.linspace(1.0, scale, n - mid)
        out[mid:] *= ramp

    return out


def _apply_distribute(
    chunk: np.ndarray,
    distribute_val: float,
    center_in_chunk: float,
) -> np.ndarray:
    """Redistribute samples between the two halves by resampling each.

    The total output length equals the input length exactly.
    The split point is the calculated center ZC position (not re-detected).

    distribute_val = 0.0   -> no change
    distribute_val = +0.5  -> first half gets 50% more samples (stretched),
                              second half gets correspondingly fewer (compressed)
    distribute_val = -0.5  -> first half gets 50% fewer samples (compressed),
                              second half gets correspondingly more (stretched)

    Each half is resampled via np.interp to its new sample count, preserving
    waveform shape. The two halves are then concatenated.
    """
    if abs(distribute_val) < 1e-6:
        return chunk

    n = len(chunk)
    if n < 4:
        return chunk

    split = int(round(center_in_chunk))
    split = max(1, min(n - 1, split))

    first  = chunk[:split]
    second = chunk[split:]
    n1     = len(first)
    n2     = len(second)

    if n1 < 1 or n2 < 1:
        return chunk

    # distribute_val > 0: first half grows, second shrinks
    # distribute_val < 0: first half shrinks, second grows
    # Scale factor: at +0.5, first half gains 50% of its length,
    # and second half loses that many samples to compensate.
    extra = int(round(distribute_val * n1))  # samples to add/remove from first half
    new_n1 = max(1, n1 + extra)
    new_n2 = max(1, n - new_n1)              # second gets whatever remains

    # Resample each half independently via linear interpolation
    x_old1 = np.linspace(0.0, 1.0, n1)
    x_new1 = np.linspace(0.0, 1.0, new_n1)
    first_r = np.interp(x_new1, x_old1, first)

    x_old2 = np.linspace(0.0, 1.0, n2)
    x_new2 = np.linspace(0.0, 1.0, new_n2)
    second_r = np.interp(x_new2, x_old2, second)

    return np.concatenate([first_r, second_r])
