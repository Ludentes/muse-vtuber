from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from brainflow.data_filter import DataFilter, WindowOperations

from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.types import CH_NAMES, Cadence, PipelineFrame

log = logging.getLogger("signal_quality")

SAMPLE_RATE = 256
EEG_LOW = 1.0
EEG_HIGH = 40.0
FLAT_STD_THRESHOLD = 0.5  # µV — below this, electrode is likely disconnected
RAIL_THRESHOLD = 995.0  # µV — ADC saturation


@dataclass
class SignalQualityResult:
    # Amplitude-based (original): railed + std dev check
    amplitude_quality: dict[str, float] = field(default_factory=dict)
    amplitude_fit: str = "unknown"
    # PSD-based (new): EEG band power ratio
    psd_quality: dict[str, float] = field(default_factory=dict)
    psd_fit: str = "unknown"


def _amplitude_quality(ch_data: np.ndarray) -> float:
    """Original algorithm: railed check + std dev scoring."""
    n = len(ch_data)
    railed = float(np.sum(np.abs(ch_data) > RAIL_THRESHOLD)) / n
    railed_score = max(0.0, 1.0 - railed * 10)

    std = float(np.std(ch_data))
    if std < 2.0:
        std_score = 0.2
    elif std > 200.0:
        std_score = 0.3
    else:
        std_score = 1.0

    return round(min(railed_score, std_score), 2)


def _psd_quality(ch_data: np.ndarray, nfft: int, sample_rate: int) -> float | None:
    """New algorithm: EEG band power / total power ratio."""
    if len(ch_data) < nfft:
        return None
    try:
        data = ch_data.astype(np.float64).copy()
        psd = DataFilter.get_psd_welch(
            data, nfft, nfft // 2,
            sample_rate, WindowOperations.HANNING.value,
        )
        eeg_power = DataFilter.get_band_power(psd, EEG_LOW, EEG_HIGH)
        total_power = DataFilter.get_band_power(psd, EEG_LOW, sample_rate / 2.0)
        if total_power > 0:
            return max(0.0, min(1.0, float(eeg_power / total_power)))
        return 0.0
    except Exception:
        log.warning("PSD quality failed", exc_info=True)
        return None


def _fit_status_by_poor_count(quality: dict[str, float]) -> str:
    """Original: count channels below 0.7."""
    poor_count = sum(1 for q in quality.values() if q < 0.7)
    if poor_count == 0:
        return "good"
    elif poor_count <= 2:
        return "adjust"
    return "poor"


def _fit_status_by_min(quality: dict[str, float]) -> str:
    """PSD: min channel quality thresholds."""
    if not quality:
        return "unknown"
    min_q = min(quality.values())
    if min_q > 0.5:
        return "good"
    elif min_q > 0.2:
        return "adjust"
    return "poor"


class SignalQualityStage(Stage):
    """Per-channel EEG signal quality — computes both amplitude and PSD metrics."""

    name = "signal_quality"
    cadence = Cadence.SLOW

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate

    def process(self, frame: PipelineFrame) -> None:
        if frame.eeg is None or frame.eeg.shape[1] == 0:
            return

        nfft = DataFilter.get_nearest_power_of_two(self.sample_rate)
        n_channels = min(frame.eeg.shape[0], len(CH_NAMES))

        amp_quality: dict[str, float] = {}
        psd_quality: dict[str, float] = {}

        for ch_idx in range(n_channels):
            ch_name = CH_NAMES[ch_idx]
            ch_data = frame.eeg[ch_idx]

            # Flat-line → both methods score 0
            if np.std(ch_data) < FLAT_STD_THRESHOLD:
                amp_quality[ch_name] = 0.0
                psd_quality[ch_name] = 0.0
                continue

            amp_quality[ch_name] = _amplitude_quality(ch_data)

            psd_q = _psd_quality(ch_data, nfft, self.sample_rate)
            if psd_q is not None:
                psd_quality[ch_name] = round(psd_q, 2)

        if not amp_quality:
            return

        frame.set(SignalQualityResult(
            amplitude_quality=amp_quality,
            amplitude_fit=_fit_status_by_poor_count(amp_quality),
            psd_quality=psd_quality,
            psd_fit=_fit_status_by_min(psd_quality),
        ))
