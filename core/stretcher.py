"""
core/stretcher.py
Time-stretch wrapper using pyrubberband (Rubber Band Library).

Falls back to scipy.signal.resample_poly if pyrubberband is not available,
with a warning. The fallback is lower quality but keeps the app functional
during development before rubberband-cli is installed.

Public API
----------
stretch(samples, ratio, sr)           -> np.ndarray
    Stretch *samples* by *ratio* (>1 = longer, <1 = shorter).

stretch_to_length(samples, target_len, sr) -> np.ndarray
    Stretch to exactly *target_len* samples.
"""

from __future__ import annotations

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

_RUBBERBAND_AVAILABLE = False
try:
    import pyrubberband as pyrb
    _RUBBERBAND_AVAILABLE = True
    logger.debug("pyrubberband available.")
except Exception as e:
    logger.warning(
        "pyrubberband not available (%s). "
        "Time-stretching will use scipy fallback (lower quality). "
        "Install rubberband-cli and pyrubberband for full quality.", e
    )


# Clamp ratios to safe range for Rubber Band
_RATIO_MIN = 0.02
_RATIO_MAX = 50.0


def stretch(samples: np.ndarray, ratio: float, sr: int = 44100) -> np.ndarray:
    """Time-stretch *samples* by *ratio*.

    ratio > 1.0  -> output is longer  (slower)
    ratio < 1.0  -> output is shorter (faster)
    ratio = 1.0  -> no change

    Parameters
    ----------
    samples : float64 mono array
    ratio   : stretch factor
    sr      : sample rate

    Returns
    -------
    float64 mono array, length approximately int(len(samples) * ratio)
    """
    ratio = float(np.clip(ratio, _RATIO_MIN, _RATIO_MAX))

    if abs(ratio - 1.0) < 1e-6:
        return samples.copy()

    if _RUBBERBAND_AVAILABLE:
        return _stretch_rubberband(samples, ratio, sr)
    else:
        return _stretch_scipy(samples, ratio)


def stretch_to_length(
    samples: np.ndarray,
    target_len: int,
    sr: int = 44100,
) -> np.ndarray:
    """Stretch *samples* to exactly *target_len* samples.

    Uses time-stretch (not resampling) so pitch is preserved.
    Output is trimmed or zero-padded to hit exactly *target_len*.
    """
    src_len = len(samples)
    if src_len == 0 or target_len == 0:
        return np.zeros(target_len, dtype=np.float64)

    if src_len == target_len:
        return samples.copy()

    ratio = target_len / src_len
    stretched = stretch(samples, ratio, sr)

    # Trim or zero-pad to hit exact length
    if len(stretched) >= target_len:
        return stretched[:target_len].astype(np.float64)
    else:
        out = np.zeros(target_len, dtype=np.float64)
        out[: len(stretched)] = stretched
        return out


# ---------------------------------------------------------------------------
# Internal backends
# ---------------------------------------------------------------------------

def _stretch_rubberband(samples: np.ndarray, ratio: float, sr: int) -> np.ndarray:
    """High-quality stretch via Rubber Band Library."""
    # pyrubberband expects float32 and (N,) or (N, ch)
    audio_f32 = samples.astype(np.float32)
    stretched  = pyrb.time_stretch(audio_f32, sr, ratio)
    return stretched.astype(np.float64)


def _stretch_scipy(samples: np.ndarray, ratio: float) -> np.ndarray:
    """Low-quality fallback stretch via polyphase resampling.

    This changes pitch too (it's a resample, not a true time-stretch).
    Acceptable only as a development fallback.
    """
    from math import gcd
    from scipy.signal import resample_poly

    # Express ratio as a rational up/down pair
    # Use 1000 as denominator for reasonable precision
    denom = 1000
    numer = max(1, int(round(ratio * denom)))
    g = gcd(numer, denom)
    up, down = numer // g, denom // g

    logger.warning(
        "Using scipy resample fallback (up=%d, down=%d) -- install rubberband-cli for quality.",
        up, down,
    )
    return resample_poly(samples, up, down).astype(np.float64)
