"""
core/stretcher.py
High-quality time-stretch using the Rubber Band Library via pyrubberband.

Rubber Band is a phase-vocoder-based time-stretcher that preserves pitch
while changing duration. It requires:
  pip install pyrubberband
  system: rubberband-cli  (apt install rubberband-cli  /  brew install rubberband)

There is NO fallback. resample_poly is not a time-stretch (it changes pitch)
and is not acceptable for wavetable output. If pyrubberband is unavailable
at import time, a clear RuntimeError is raised when stretch() is called.

Public API
----------
stretch(samples, ratio, sr)           -> np.ndarray
    Stretch by ratio (>1 = longer/slower, <1 = shorter/faster).
    Pitch is preserved. Output length ~ int(len(samples) * ratio).

stretch_to_length(samples, target_len, sr) -> np.ndarray
    Stretch to exactly target_len samples.
    Trims or zero-pads by at most 1 sample to hit exact length.

is_available() -> bool
    True if pyrubberband + rubberband-cli are present and working.
"""

from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)

_RUBBERBAND_AVAILABLE = False
_RUBBERBAND_ERROR: str = ""

try:
    import pyrubberband as _pyrb
    _RUBBERBAND_AVAILABLE = True
except Exception as _e:
    _RUBBERBAND_ERROR = str(_e)
    logger.warning(
        "pyrubberband not available: %s\n"
        "Time-stretching will fail until you install:\n"
        "  pip install pyrubberband\n"
        "  (system) apt install rubberband-cli  OR  brew install rubberband",
        _e,
    )

# Length-ratio limits. After inversion to speed ratio:
#   length 0.02 -> speed 50x (very compressed)
#   length 50.0 -> speed 0.02x (very stretched)
_RATIO_MIN = 0.02   # shortest output relative to input
_RATIO_MAX = 50.0   # longest output relative to input


def is_available() -> bool:
    """Return True if pyrubberband and rubberband-cli are usable."""
    if not _RUBBERBAND_AVAILABLE:
        return False
    # Quick smoke-test with a tiny array
    try:
        probe = np.zeros(64, dtype=np.float32)
        _pyrb.time_stretch(probe, 44100, 1.0)
        return True
    except Exception:
        return False


def stretch(samples: np.ndarray, ratio: float, sr: int = 44100) -> np.ndarray:
    """Time-stretch *samples* by *ratio* preserving pitch.

    Parameters
    ----------
    samples : float64 mono array
    ratio   : >1.0 = longer (slower), <1.0 = shorter (faster), 1.0 = no change
    sr      : sample rate

    Returns
    -------
    float64 mono array, length approximately int(len(samples) * ratio)

    Raises
    ------
    RuntimeError if pyrubberband / rubberband-cli is not installed.
    """
    if not _RUBBERBAND_AVAILABLE:
        raise RuntimeError(
            "Time-stretching requires pyrubberband and rubberband-cli.\n"
            "Install with:\n"
            "  pip install pyrubberband\n"
            "  (system) apt install rubberband-cli  OR  brew install rubberband\n"
            f"Import error was: {_RUBBERBAND_ERROR}"
        )

    ratio = float(np.clip(ratio, _RATIO_MIN, _RATIO_MAX))

    if abs(ratio - 1.0) < 1e-6:
        return samples.astype(np.float64)

    # pyrubberband.time_stretch() takes a *speed* ratio (like tape speed):
    #   speed_ratio = 2.0 -> plays back faster -> output is shorter
    #   speed_ratio = 0.5 -> plays back slower -> output is longer
    # Our API uses a *length* ratio (>1 = longer), so we invert.
    speed_ratio = 1.0 / ratio

    # pyrubberband expects float32 mono as (N,)
    audio_f32 = samples.astype(np.float32)
    stretched  = _pyrb.time_stretch(audio_f32, sr, speed_ratio)
    return stretched.astype(np.float64)


def stretch_to_length(
    samples: np.ndarray,
    target_len: int,
    sr: int = 44100,
) -> np.ndarray:
    """Stretch *samples* to exactly *target_len* samples, preserving pitch.

    Computes the exact ratio needed, calls stretch(), then trims or
    zero-pads by at most a few samples to guarantee the exact length.

    Raises
    ------
    RuntimeError if pyrubberband / rubberband-cli is not installed.
    """
    src_len = len(samples)
    if src_len == 0 or target_len == 0:
        return np.zeros(max(target_len, 0), dtype=np.float64)

    if src_len == target_len:
        return samples.astype(np.float64)

    ratio    = target_len / src_len
    stretched = stretch(samples, ratio, sr)

    # Enforce exact length (Rubber Band output can be off by 1-2 samples)
    if len(stretched) >= target_len:
        return stretched[:target_len].astype(np.float64)
    else:
        out = np.zeros(target_len, dtype=np.float64)
        out[:len(stretched)] = stretched
        return out
