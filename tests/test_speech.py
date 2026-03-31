import numpy as np
import pytest

from muse_vtuber.pipeline.speech import SpeechDetector, SpeechResult
from muse_vtuber.pipeline.types import Cadence, PipelineFrame


def _make_frame(temporal_amplitude: float = 5.0, n_samples: int = 16) -> PipelineFrame:
    """Create frame with 4-channel EEG. Temporal channels (0,3) at given amplitude."""
    eeg = np.random.randn(4, n_samples) * 2.0
    eeg[0] = np.random.randn(n_samples) * temporal_amplitude  # TP9
    eeg[3] = np.random.randn(n_samples) * temporal_amplitude  # TP10
    return PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)


def test_speech_detector_cadence():
    det = SpeechDetector()
    assert det.cadence == Cadence.FAST


def test_quiet_not_speech():
    """Low temporal HF should not trigger speech."""
    det = SpeechDetector()
    for _ in range(100):
        frame = _make_frame(temporal_amplitude=3.0)
        det.process(frame)
    result = frame.get(SpeechResult)
    assert result is not None
    assert result.speech_active is False


def test_loud_temporal_triggers_speech():
    """High sustained temporal HF triggers speech detection."""
    det = SpeechDetector()
    for _ in range(100):
        frame = _make_frame(temporal_amplitude=50.0)
        det.process(frame)
    result = frame.get(SpeechResult)
    assert result is not None
    assert result.speech_active is True


def test_none_eeg_safe():
    det = SpeechDetector()
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    det.process(frame)
    result = frame.get(SpeechResult)
    assert result is not None
    assert result.speech_active is False
