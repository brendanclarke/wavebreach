"""
core/filter_dsp.py
Resonant 2-pole biquad filter using the SVF (State Variable Filter) formulation.

Supports LP, HP, BP modes with meaningful Q on all three.
Applied via scipy sosfilt (second-order sections, numerically stable).

Public API
----------
design_filter(mode, cutoff_hz, q, sr)  -> sos array (shape 1x6)
apply_filter(samples, sos)             -> filtered float64 array
compute_response(sos, sr, n_points)    -> (freqs_hz, magnitude_db)
"""

from __future__ import annotations

import math
import numpy as np
from scipy.signal import sosfilt, sosfreqz


def design_filter(
    mode: str,
    cutoff_hz: float,
    q: float,
    sr: int = 44100,
) -> np.ndarray:
    """Design a 2-pole resonant biquad filter as a SOS array.

    Uses the Audio EQ Cookbook / SVF formulation so that Q has a perceptually
    consistent meaning across LP, HP, and BP modes:
      - Q = 0.707  -> Butterworth (maximally flat, no resonance peak)
      - Q > 0.707  -> resonance peak at cutoff
      - Q < 0.707  -> overdamped

    Parameters
    ----------
    mode       : 'LP' | 'HP' | 'BP'
    cutoff_hz  : cutoff / centre frequency in Hz
    q          : resonance (0.1 - 10.0)
    sr         : sample rate (default 44100)

    Returns
    -------
    sos : np.ndarray, shape (1, 6)
        Second-order sections array for use with scipy.signal.sosfilt.
    """
    cutoff_hz = float(np.clip(cutoff_hz, 1.0, sr / 2.0 - 1.0))
    q         = float(np.clip(q, 0.001, 1000.0))

    w0    = 2.0 * math.pi * cutoff_hz / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = sin_w / (2.0 * q)

    if mode == "LP":
        b0 = (1.0 - cos_w) / 2.0
        b1 =  1.0 - cos_w
        b2 = (1.0 - cos_w) / 2.0
    elif mode == "HP":
        b0 =  (1.0 + cos_w) / 2.0
        b1 = -(1.0 + cos_w)
        b2 =  (1.0 + cos_w) / 2.0
    elif mode == "BP":
        b0 =  sin_w / 2.0
        b1 =  0.0
        b2 = -sin_w / 2.0
    else:
        raise ValueError(f"Unknown filter mode: {mode!r}. Use 'LP', 'HP', or 'BP'.")

    a0 =  1.0 + alpha
    a1 = -2.0 * cos_w
    a2 =  1.0 - alpha

    # Normalise by a0
    sos = np.array([[
        b0 / a0, b1 / a0, b2 / a0,
        1.0,     a1 / a0, a2 / a0,
    ]])
    return sos


def apply_filter(samples: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """Apply SOS filter to *samples* (float64 mono). Returns float64 array."""
    return sosfilt(sos, samples).astype(np.float64)


def compute_response(
    sos: np.ndarray,
    sr: int = 44100,
    n_points: int = 2048,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute frequency response of *sos* filter.

    Returns
    -------
    freqs_hz : np.ndarray  -- log-spaced from 20 Hz to sr/2
    mag_db   : np.ndarray  -- magnitude response in dB
    """
    w, h = sosfreqz(sos, worN=n_points, fs=sr)
    mag_db = 20.0 * np.log10(np.abs(h) + 1e-12)
    return w.astype(np.float64), mag_db.astype(np.float64)
