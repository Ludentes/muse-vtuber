from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.types import Cadence, PipelineFrame


@dataclass
class SpeechResult:
    speech_active: bool


def _hf_rms(sig: np.ndarray) -> float:
    """RMS of first-order diff — approximates high-frequency energy."""
    if len(sig) < 2:
        return 0.0
    return float(np.sqrt(np.mean(np.diff(sig) ** 2)))


class SpeechDetector(Stage):
    """Detect speech via sustained temporal EMG.

    Adaptive baseline: rolling median of temporal HF RMS.
    Flags speech when enough recent chunks exceed baseline × hf_ratio_thresh.
    """

    name = "speech_detector"
    cadence = Cadence.FAST

    def __init__(
        self,
        hf_thresh: float = 15.0,
        hf_ratio_thresh: float = 2.0,
        window_chunks: int = 48,
        min_active_frac: float = 0.4,
    ):
        self.hf_thresh = hf_thresh
        self.hf_ratio_thresh = hf_ratio_thresh
        self.window_chunks = window_chunks
        self.min_active = int(window_chunks * min_active_frac)
        self._hf_history: deque[float] = deque(maxlen=window_chunks)
        self._hf_baseline_history: deque[float] = deque(maxlen=256)
        self._hf_baseline: float = 0.0
        self._update_ctr: int = 0

    def process(self, frame: PipelineFrame) -> None:
        if frame.eeg is None or frame.eeg.shape[1] == 0:
            frame.set(SpeechResult(speech_active=False))
            return

        temporal = (frame.eeg[0] + frame.eeg[3]) / 2.0
        t_hf = _hf_rms(temporal)
        self._hf_history.append(t_hf)

        if self._hf_baseline > 1.0:
            effective_thresh = max(self._hf_baseline * self.hf_ratio_thresh, self.hf_thresh)
        else:
            effective_thresh = self.hf_thresh

        active = False
        if len(self._hf_history) >= self.window_chunks:
            n_above = sum(1 for v in self._hf_history if v > effective_thresh)
            active = n_above >= self.min_active

        self._update_ctr += 1
        if self._update_ctr >= 8:
            self._update_ctr = 0
            if not active:
                self._hf_baseline_history.append(t_hf)
                if len(self._hf_baseline_history) >= 8:
                    self._hf_baseline = float(np.median(self._hf_baseline_history))

        frame.set(SpeechResult(speech_active=active))
