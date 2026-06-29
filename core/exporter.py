"""
core/exporter.py
Export processed waveforms as a numbered ZIP of 44.1 kHz / 16-bit mono WAVs.

Public API
----------
export_zip(waves, wavetable_name, output_path, sr)
    Write a ZIP file to *output_path* containing:
        <wavetable_name>_0000.wav
        <wavetable_name>_0001.wav
        ...
    Each file is 44.1 kHz, 16-bit PCM, mono.

sanitise_name(name) -> str
    Strip characters illegal in filenames/ZIP entry names.
"""

from __future__ import annotations

import io
import re
import zipfile
import logging
from pathlib import Path

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# Characters not allowed in ZIP entry names / filesystem filenames
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def sanitise_name(name: str) -> str:
    """Replace illegal filename characters with underscores, strip leading/trailing spaces."""
    name = name.strip()
    name = _ILLEGAL.sub("_", name)
    return name or "wavebreach"


def export_zip(
    waves: list[np.ndarray],
    wavetable_name: str,
    output_path: str | Path,
    sr: int = 44100,
) -> int:
    """Write *waves* as a numbered ZIP of 16-bit WAV files.

    Parameters
    ----------
    waves          : list of float64 arrays, all the same length
    wavetable_name : base name for the ZIP entries (sanitised internally)
    output_path    : full path to the output .zip file
    sr             : sample rate (default 44100)

    Returns
    -------
    int : number of waveforms written

    Raises
    ------
    ValueError  : if waves is empty
    IOError     : if the output path cannot be written
    """
    if not waves:
        raise ValueError("No waveforms to export.")

    name    = sanitise_name(wavetable_name)
    n_waves = len(waves)
    # Zero-pad width: at least 4 digits, more if > 9999 waves
    pad     = max(4, len(str(n_waves - 1)))
    output_path = Path(output_path)

    logger.info(
        "Exporting %d waveforms as '%s' to %s",
        n_waves, name, output_path,
    )

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, wave in enumerate(waves):
            entry_name = f"{name}_{i:0{pad}d}.wav"

            # Convert float64 -> int16
            clipped = np.clip(wave, -1.0, 1.0)
            pcm16   = (clipped * 32767.0).astype(np.int16)

            # Write to an in-memory WAV buffer
            buf = io.BytesIO()
            sf.write(buf, pcm16, sr, subtype="PCM_16", format="WAV")
            buf.seek(0)

            zf.writestr(entry_name, buf.read())

    logger.info("Export complete: %s (%d waves)", output_path, n_waves)
    return n_waves
