"""
core/state.py
Central application state dataclass.  All UI panels and core processors
share a single AppState instance (passed by reference).  Nothing in here
does any computation — it is pure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class WaveRegion:
    """One selected single-cycle waveform, expressed in interpolated sample coords."""
    begin_zc: float        # interpolated sample index of begin zero-crossing
    center_zc: float       # interpolated sample index of central zero-crossing
    end_zc: float          # interpolated sample index of end zero-crossing
    begin_sample: int      # integer index for array slicing (floor of begin_zc)
    end_sample: int        # integer index for array slicing (ceil of end_zc)


@dataclass
class AppState:
    # ------------------------------------------------------------------ #
    #  Raw audio (populated on file load)                                 #
    # ------------------------------------------------------------------ #
    raw_samples: Optional[np.ndarray] = None   # float64, mono, normalised to [-1, 1]
    sample_rate: int = 44100                   # always 44100 after load
    source_path: str = ""
    duration_samples: int = 0                  # len(raw_samples)

    # ------------------------------------------------------------------ #
    #  Processing parameters (mirrors UI controls 1-to-1)                #
    # ------------------------------------------------------------------ #
    start_pad: int = 0           # samples excluded at front
    end_pad: int = 0             # samples excluded at end
    num_waves: int = 16          # requested number of single-cycle waveforms
    min_samples: int = 64        # ignore ZC gaps smaller than this
    max_samples: int = 4096      # ignore ZC gaps larger than this

    length_mode: str = "samples"  # "pitch" | "samples"
    length_hz: float = 440.0      # target pitch in Hz (when mode == "pitch")
    length_samples: int = 2048    # target length in samples (when mode == "samples")

    filter_mode: str = "LP"       # "LP" | "HP" | "BP" | "OFF"
    filter_cutoff: float = 8000.0
    filter_q: float = 0.707

    normalize_enabled: bool = True
    normalize_db: float = 0.0     # 0.0 to -3.0

    edge_mode: str = "none"        # "none" | "rising" | "falling"

    # Modify — each has begin and end value; interpolated linearly across waves
    offset_begin: float = 0.0     # -0.5 to +0.5
    offset_end: float = 0.0
    stretch_begin: float = 0.0    # -0.5 to +0.5
    stretch_end: float = 0.0
    suppress_begin: float = 0.0   # -1.0 to +1.0
    suppress_end: float = 0.0

    # ------------------------------------------------------------------ #
    #  Derived / computed (populated after Go or live ZC pass)            #
    # ------------------------------------------------------------------ #
    all_zero_crossings: list = field(default_factory=list)   # list[float]
    excluded_min: list = field(default_factory=list)         # list[tuple[float,float]]
    excluded_max: list = field(default_factory=list)         # list[tuple[float,float]]
    selected_waves: list = field(default_factory=list)       # list[WaveRegion]
    processed_waves: list = field(default_factory=list)      # list[np.ndarray]

    current_wave_index: int = 0
    wavetable_name: str = "wavebreach"
