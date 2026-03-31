from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from brainflow.data_filter import DataFilter, DetrendOperations, WindowOperations

from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.clench import ClenchResult
from muse_vtuber.pipeline.speech import SpeechResult
from muse_vtuber.pipeline.types import (
    BAND_NAMES,
    BANDS,
    LEFT_CHS,
    RIGHT_CHS,
    Cadence,
    PipelineFrame,
)

log = logging.getLogger("band_power")


@dataclass
class BandPowerResult:
    """Band power per hemisphere and average, EMA-smoothed."""

    band_powers_left: dict[str, float]
    band_powers_right: dict[str, float]
    band_powers_avg: dict[str, float]
    band_powers_per_ch: dict[str, list[float]]  # raw per-channel for debug


class BandPowerStage(Stage):
    """Compute frequency band power with artifact-gated EMA smoothing.

    When blink, clench, or speech is active, the EMA target freezes
    to the last clean value to prevent artifact contamination.
    """

    name = "band_power"
    cadence = Cadence.SLOW

    def __init__(self, ema_decay: float = 0.04, sample_rate: int = 256):
        self.ema_decay = ema_decay
        self.sample_rate = sample_rate
        self._ema: dict[str, list[float]] = {}  # band -> [ch0, ch1, ch2, ch3]

    def _is_artifact(self, frame: PipelineFrame) -> bool:
        speech = frame.get(SpeechResult)
        clench = frame.get(ClenchResult)
        if speech and speech.speech_active:
            return True
        if clench and clench.jaw_clench:
            return True
        return any(e.kind == "blink" for e in frame.events)

    def _compute_raw_band_powers(self, eeg: np.ndarray) -> dict[str, list[float]] | None:
        """Compute raw band power per channel. Returns None on failure."""
        nfft = DataFilter.get_nearest_power_of_two(self.sample_rate)
        if eeg.shape[1] < nfft:
            return None

        n_channels = eeg.shape[0]
        band_powers: dict[str, list[float]] = {b: [] for b in BAND_NAMES}

        for ch_idx in range(n_channels):
            channel_data = eeg[ch_idx].astype(np.float64).copy()
            try:
                mu = np.mean(channel_data)
                sd = np.std(channel_data)
                if sd > 0:
                    np.clip(channel_data, mu - 4 * sd, mu + 4 * sd, out=channel_data)
                DataFilter.detrend(channel_data, DetrendOperations.LINEAR.value)
                psd = DataFilter.get_psd_welch(
                    channel_data, nfft, nfft // 2,
                    self.sample_rate, WindowOperations.HANNING.value,
                )
                for band_name in BAND_NAMES:
                    low, high = BANDS[band_name]
                    power = DataFilter.get_band_power(psd, low, high)
                    band_powers[band_name].append(float(power))
            except Exception:
                log.warning("BandPower channel %d failed", ch_idx, exc_info=True)
                for band_name in BAND_NAMES:
                    band_powers[band_name].append(0.0)

        return band_powers

    def _update_ema(self, raw: dict[str, list[float]], artifact: bool) -> None:
        """Update EMA. If artifact, skip update (freeze)."""
        if artifact:
            return
        alpha = self.ema_decay
        for band, values in raw.items():
            if band not in self._ema:
                self._ema[band] = list(values)
            else:
                for i in range(len(values)):
                    if i < len(self._ema[band]):
                        self._ema[band][i] = alpha * values[i] + (1 - alpha) * self._ema[band][i]
                    else:
                        self._ema[band].append(values[i])

    def _hemisphere_avg(self, band: str, indices: list[int]) -> float:
        if band not in self._ema:
            return 0.0
        values = self._ema[band]
        selected = [values[i] for i in indices if i < len(values)]
        return sum(selected) / len(selected) if selected else 0.0

    def process(self, frame: PipelineFrame) -> None:
        if frame.eeg is None or frame.eeg.shape[1] == 0:
            return

        raw = self._compute_raw_band_powers(frame.eeg)
        if raw is None:
            return

        artifact = self._is_artifact(frame)
        self._update_ema(raw, artifact)

        left = {b: self._hemisphere_avg(b, LEFT_CHS) for b in BAND_NAMES}
        right = {b: self._hemisphere_avg(b, RIGHT_CHS) for b in BAND_NAMES}
        avg = {b: (left[b] + right[b]) / 2.0 for b in BAND_NAMES}

        frame.set(BandPowerResult(
            band_powers_left=left,
            band_powers_right=right,
            band_powers_avg=avg,
            band_powers_per_ch=raw,
        ))
