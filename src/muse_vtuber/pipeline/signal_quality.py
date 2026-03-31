from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from brainflow.data_filter import DataFilter, WindowOperations

from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.types import CH_NAMES, Cadence, PipelineFrame

log = logging.getLogger("signal_quality")

SAMPLE_RATE = 256
EEG_LOW = 1.0
EEG_HIGH = 40.0
FLAT_STD_THRESHOLD = 0.5  # µV — below this, electrode is likely disconnected


@dataclass
class SignalQualityResult:
    channel_quality: dict[str, float]  # 0.0-1.0 per channel
    fit_status: str  # "good", "adjust", "poor"


class SignalQualityStage(Stage):
    """Per-channel EEG signal quality metric for headband fit detection.

    Computes quality as the ratio of useful EEG power (1-40Hz) to total power.
    Flat-line detection catches disconnected electrodes.
    """

    name = "signal_quality"
    cadence = Cadence.SLOW

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate

    def process(self, frame: PipelineFrame) -> None:
        if frame.eeg is None or frame.eeg.shape[1] == 0:
            return

        nfft = DataFilter.get_nearest_power_of_two(self.sample_rate)
        if frame.eeg.shape[1] < nfft:
            return

        channel_quality: dict[str, float] = {}
        n_channels = min(frame.eeg.shape[0], len(CH_NAMES))

        for ch_idx in range(n_channels):
            ch_name = CH_NAMES[ch_idx]
            ch_data = frame.eeg[ch_idx].astype(np.float64).copy()

            # Flat-line check: disconnected electrode
            if np.std(ch_data) < FLAT_STD_THRESHOLD:
                channel_quality[ch_name] = 0.0
                continue

            try:
                psd = DataFilter.get_psd_welch(
                    ch_data, nfft, nfft // 2,
                    self.sample_rate, WindowOperations.HANNING.value,
                )
                eeg_power = DataFilter.get_band_power(psd, EEG_LOW, EEG_HIGH)
                # Total power up to Nyquist
                total_power = DataFilter.get_band_power(psd, EEG_LOW, self.sample_rate / 2.0)

                if total_power > 0:
                    quality = float(eeg_power / total_power)
                    channel_quality[ch_name] = max(0.0, min(1.0, quality))
                else:
                    channel_quality[ch_name] = 0.0
            except Exception:
                log.warning("Signal quality channel %d failed", ch_idx, exc_info=True)
                channel_quality[ch_name] = 0.0

        # Determine fit status from worst channel
        if not channel_quality:
            return

        min_quality = min(channel_quality.values())
        if min_quality > 0.5:
            fit_status = "good"
        elif min_quality > 0.2:
            fit_status = "adjust"
        else:
            fit_status = "poor"

        frame.set(SignalQualityResult(
            channel_quality=channel_quality,
            fit_status=fit_status,
        ))
