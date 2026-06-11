"""
core/audio_io.py
Load audio files of any common format, convert to 44.1 kHz / 16-bit mono,
and return a float64 numpy array normalised to [-1.0, 1.0].

Supported paths:
  1. soundfile alone  — WAV, AIFF, FLAC, OGG (libsndfile-native)
  2. pydub + ffmpeg   — MP3, M4A, AAC, WMA, and anything else ffmpeg handles

The caller always receives a uniform float64 array at 44100 Hz regardless of
the source format.  Stereo/multichannel input is reduced to the left (first)
channel only.

Constants
---------
MAX_DURATION_SECONDS : float
    Files longer than this are rejected.
TARGET_SR : int
    Output sample rate — always 44100.
"""

from __future__ import annotations

import io
import os
import tempfile
import logging
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

MAX_DURATION_SECONDS: float = 10.0
TARGET_SR: int = 44100

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_audio(path: str | os.PathLike) -> Tuple[np.ndarray, int]:
    """Load *path*, convert to 44.1 kHz mono float64, return (samples, sr).

    Parameters
    ----------
    path : str | PathLike
        Path to any audio file.

    Returns
    -------
    samples : np.ndarray
        float64, shape (N,), values in [-1.0, 1.0].
    sr : int
        Always 44100.

    Raises
    ------
    ValueError
        If the file is longer than MAX_DURATION_SECONDS after conversion.
    RuntimeError
        If the file cannot be decoded by any available backend.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    samples, sr = _load_any(path)

    # Stereo / multichannel → left channel only
    if samples.ndim == 2:
        samples = samples[:, 0]

    # Ensure float64, normalised to [-1, 1]
    samples = _to_float64(samples)

    # Resample to 44100 if needed
    if sr != TARGET_SR:
        samples = _resample(samples, sr, TARGET_SR)
        sr = TARGET_SR

    # Duration guard
    duration = len(samples) / sr
    if duration > MAX_DURATION_SECONDS:
        raise ValueError(
            f"File is {duration:.2f}s — maximum allowed is "
            f"{MAX_DURATION_SECONDS:.0f}s."
        )

    return samples, sr


def samples_to_int16(samples: np.ndarray) -> np.ndarray:
    """Convert float64 [-1, 1] array to int16 for WAV export."""
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def write_wav(path: str | os.PathLike, samples: np.ndarray, sr: int = TARGET_SR) -> None:
    """Write float64 samples as a 16-bit PCM WAV file."""
    i16 = samples_to_int16(samples)
    sf.write(str(path), i16, sr, subtype="PCM_16")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_any(path: Path) -> Tuple[np.ndarray, int]:
    """Try soundfile first; fall back to pydub if it fails."""
    try:
        return _load_soundfile(path)
    except Exception as sf_exc:
        logger.debug("soundfile failed (%s), trying pydub…", sf_exc)
        try:
            return _load_pydub(path)
        except Exception as pd_exc:
            raise RuntimeError(
                f"Could not decode '{path.name}'.\n"
                f"soundfile error: {sf_exc}\n"
                f"pydub error: {pd_exc}\n\n"
                "Ensure ffmpeg is installed and on your PATH for MP3/M4A/AAC support."
            ) from pd_exc


def _load_soundfile(path: Path) -> Tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), dtype="float64", always_2d=False)
    return data, sr


def _load_pydub(path: Path) -> Tuple[np.ndarray, int]:
    """Use pydub (ffmpeg) to decode, then convert to numpy float64."""
    from pydub import AudioSegment

    ext = path.suffix.lstrip(".").lower() or "mp3"
    seg: AudioSegment = AudioSegment.from_file(str(path), format=ext)

    sr = seg.frame_rate
    # Export to raw PCM bytes (signed 16-bit little-endian)
    raw = seg.raw_data
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)

    # De-interleave channels → always keep only channel 0
    n_ch = seg.channels
    if n_ch > 1:
        samples = samples[::n_ch]          # stride-select channel 0

    # Normalise to [-1, 1]
    samples = samples / 32768.0
    return samples, sr


def _to_float64(samples: np.ndarray) -> np.ndarray:
    """Ensure float64 in [-1.0, 1.0] regardless of input dtype."""
    if samples.dtype == np.float64:
        return np.clip(samples, -1.0, 1.0)
    if samples.dtype == np.float32:
        return samples.astype(np.float64)
    # Integer dtypes
    info = np.iinfo(samples.dtype)
    return samples.astype(np.float64) / max(abs(info.min), abs(info.max))


def _resample(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """High-quality polyphase resampling via scipy."""
    from math import gcd
    from scipy.signal import resample_poly

    g = gcd(src_sr, dst_sr)
    up = dst_sr // g
    down = src_sr // g
    return resample_poly(samples, up, down).astype(np.float64)
