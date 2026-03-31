import numpy as np
import pytest

from muse_vtuber.pipeline.clench import ClenchDetector, ClenchResult
from muse_vtuber.pipeline.types import Cadence, PipelineFrame


def test_clench_detector_cadence():
    det = ClenchDetector()
    assert det.cadence == Cadence.FAST


def _make_clench_frame(clenching: bool, n_samples: int = 64) -> PipelineFrame:
    """Simulate clench: high 20-45Hz energy on temporal channels."""
    eeg = np.random.randn(4, n_samples) * 2.0
    if clenching:
        t = np.linspace(0, n_samples / 256.0, n_samples)
        emg = np.sin(2 * np.pi * 30 * t) * 80.0  # 30Hz, 80µV
        eeg[0] += emg  # TP9
        eeg[3] += emg  # TP10
    return PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)


def test_quiet_no_clench():
    det = ClenchDetector()
    for _ in range(20):
        frame = _make_clench_frame(clenching=False)
        det.process(frame)
    result = frame.get(ClenchResult)
    assert result is not None
    assert result.jaw_clench is False


def test_sustained_emg_triggers_clench():
    det = ClenchDetector()
    for _ in range(30):
        frame = _make_clench_frame(clenching=True)
        det.process(frame)
    result = frame.get(ClenchResult)
    assert result is not None
    assert result.jaw_clench is True


def test_none_eeg_safe():
    det = ClenchDetector()
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    det.process(frame)
    result = frame.get(ClenchResult)
    assert result is not None
    assert result.jaw_clench is False
