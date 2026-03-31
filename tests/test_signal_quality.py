import numpy as np
import pytest

from muse_vtuber.pipeline.signal_quality import SignalQualityResult, SignalQualityStage
from muse_vtuber.pipeline.types import CH_NAMES, Cadence, PipelineFrame


def test_cadence_is_slow():
    stage = SignalQualityStage()
    assert stage.cadence == Cadence.SLOW


def test_clean_sine_scores_high():
    """A clean 10Hz sine wave (within EEG band) should score > 0.5 and fit_status='good'."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    signal = np.sin(2 * np.pi * 10 * t) * 20.0  # 10Hz, 20µV
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.channel_quality[ch] > 0.5, f"{ch} quality {result.channel_quality[ch]} should be > 0.5"
    assert result.fit_status == "good"


def test_high_frequency_noise_scores_low():
    """Pure high-frequency noise (>40Hz) should score < 0.5."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    # 80Hz noise — above EEG band
    signal = np.sin(2 * np.pi * 80 * t) * 20.0
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.channel_quality[ch] < 0.5, f"{ch} quality {result.channel_quality[ch]} should be < 0.5"


def test_flat_signal_scores_near_zero():
    """A flat (zero-variance) signal indicates a disconnected electrode — quality near 0."""
    stage = SignalQualityStage()
    eeg = np.zeros((4, 256))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.channel_quality[ch] < 0.05, f"{ch} quality {result.channel_quality[ch]} should be near 0"
    assert result.fit_status == "poor"


def test_none_eeg_safe():
    """None EEG should not crash and should produce no result."""
    stage = SignalQualityStage()
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    stage.process(frame)
    assert frame.get(SignalQualityResult) is None
