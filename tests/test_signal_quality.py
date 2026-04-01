import numpy as np
import pytest

from muse_vtuber.pipeline.signal_quality import SignalQualityResult, SignalQualityStage
from muse_vtuber.pipeline.types import CH_NAMES, Cadence, PipelineFrame


def test_cadence_is_slow():
    stage = SignalQualityStage()
    assert stage.cadence == Cadence.SLOW


def test_clean_sine_amplitude_good():
    """A clean 10Hz sine at 20µV should get amplitude_fit='good' (std in 2-200 range)."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    signal = np.sin(2 * np.pi * 10 * t) * 20.0
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.amplitude_quality[ch] >= 0.7, f"{ch} amplitude {result.amplitude_quality[ch]}"
    assert result.amplitude_fit == "good"


def test_clean_sine_psd_good():
    """A clean 10Hz sine should have high PSD quality (most power in EEG band)."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    signal = np.sin(2 * np.pi * 10 * t) * 20.0
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.psd_quality[ch] > 0.5, f"{ch} psd {result.psd_quality[ch]}"
    assert result.psd_fit == "good"


def test_high_frequency_noise_psd_low():
    """Pure 80Hz noise should score low in PSD quality."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    signal = np.sin(2 * np.pi * 80 * t) * 20.0
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.psd_quality[ch] < 0.5, f"{ch} psd {result.psd_quality[ch]}"


def test_high_frequency_noise_amplitude_good():
    """Pure 80Hz at 20µV has std ~14 (in 2-200 range), so amplitude says 'good'."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    signal = np.sin(2 * np.pi * 80 * t) * 20.0
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    # Amplitude method doesn't care about frequency — std is fine
    assert result.amplitude_fit == "good"


def test_flat_signal_both_poor():
    """Flat signal: both methods should score near 0 / poor."""
    stage = SignalQualityStage()
    eeg = np.zeros((4, 256))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.amplitude_quality[ch] < 0.05
        assert result.psd_quality[ch] < 0.05
    assert result.amplitude_fit == "poor"
    assert result.psd_fit == "poor"


def test_weak_signal_amplitude_low():
    """1µV sine: amplitude method flags as weak (std < 2), PSD still scores high."""
    stage = SignalQualityStage()
    t = np.linspace(0, 1.0, 256)
    signal = np.sin(2 * np.pi * 10 * t) * 1.0  # 1µV — very weak
    eeg = np.tile(signal, (4, 1))
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    stage.process(frame)
    result = frame.get(SignalQualityResult)
    assert result is not None
    for ch in CH_NAMES:
        assert result.amplitude_quality[ch] <= 0.2, "Amplitude should flag weak signal"
        assert result.psd_quality[ch] > 0.5, "PSD should still score high (good frequency content)"


def test_none_eeg_safe():
    """None EEG should not crash and should produce no result."""
    stage = SignalQualityStage()
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    stage.process(frame)
    assert frame.get(SignalQualityResult) is None
