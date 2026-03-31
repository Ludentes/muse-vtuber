from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from brainflow.data_filter import DataFilter

from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.types import Cadence, PipelineFrame

log = logging.getLogger("clench_detector")


@dataclass
class ClenchResult:
    jaw_clench: bool


class ClenchDetector(Stage):
    """Detect jaw clench via sustained high-frequency EMG on temporal channels.

    Bandpass 20-45Hz, compute RMS envelope, threshold with duration gate.
    """

    name = "clench_detector"
    cadence = Cadence.FAST

    def __init__(
        self,
        bp_low: float = 20.0,
        bp_high: float = 45.0,
        rms_threshold: float = 25.0,
        min_chunks: int = 5,
        sample_rate: int = 256,
    ):
        self.bp_low = bp_low
        self.bp_high = bp_high
        self.rms_threshold = rms_threshold
        self.min_chunks = min_chunks
        self.sample_rate = sample_rate
        self._above_count: int = 0

    def process(self, frame: PipelineFrame) -> None:
        if frame.eeg is None or frame.eeg.shape[1] < 4:
            frame.set(ClenchResult(jaw_clench=False))
            return

        # Average temporal channels (TP9 + TP10)
        temporal = ((frame.eeg[0] + frame.eeg[3]) / 2.0).astype(np.float64).copy()

        # Bandpass 20-45Hz
        try:
            DataFilter.perform_bandpass(
                temporal, self.sample_rate,
                self.bp_low, self.bp_high,
                4, 0, 0.0,
            )
        except Exception:
            log.warning("Bandpass filter failed", exc_info=True)
            frame.set(ClenchResult(jaw_clench=False))
            return

        rms = float(np.sqrt(np.mean(temporal ** 2)))

        if rms > self.rms_threshold:
            self._above_count += 1
        else:
            self._above_count = max(0, self._above_count - 2)

        clenching = self._above_count >= self.min_chunks
        frame.set(ClenchResult(jaw_clench=clenching))
