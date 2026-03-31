import numpy as np
import pytest

from muse_vtuber.pipeline.band_power import BandPowerResult, BandPowerStage
from muse_vtuber.pipeline.clench import ClenchResult
from muse_vtuber.pipeline.speech import SpeechResult
from muse_vtuber.pipeline.types import BAND_NAMES, Cadence, PipelineFrame


def _make_alpha_frame(n_samples: int = 256) -> PipelineFrame:
    """Create frame with strong 10Hz alpha signal on all channels."""
    t = np.linspace(0, n_samples / 256.0, n_samples)
    alpha_signal = np.sin(2 * np.pi * 10 * t) * 20.0  # 10Hz, 20µV
    eeg = np.tile(alpha_signal, (4, 1)) + np.random.randn(4, n_samples) * 2.0
    frame = PipelineFrame(eeg=eeg, imu=None, timestamp=1.0)
    frame.set(SpeechResult(speech_active=False))
    frame.set(ClenchResult(jaw_clench=False))
    return frame


def test_band_power_cadence():
    stage = BandPowerStage()
    assert stage.cadence == Cadence.SLOW


def test_band_power_computes_all_bands():
    stage = BandPowerStage()
    frame = _make_alpha_frame()
    stage.process(frame)
    result = frame.get(BandPowerResult)
    assert result is not None
    for band in BAND_NAMES:
        assert band in result.band_powers_avg
        assert result.band_powers_avg[band] >= 0.0


def test_alpha_dominant_in_alpha_signal():
    """Alpha band should have highest power when signal is 10Hz."""
    stage = BandPowerStage()
    frame = _make_alpha_frame(n_samples=512)
    stage.process(frame)
    result = frame.get(BandPowerResult)
    assert result is not None
    assert result.band_powers_avg["alpha"] > result.band_powers_avg["delta"]
    assert result.band_powers_avg["alpha"] > result.band_powers_avg["beta"]


def test_hemisphere_separation():
    """Left (TP9+AF7) and right (AF8+TP10) powers computed separately."""
    stage = BandPowerStage()
    frame = _make_alpha_frame()
    stage.process(frame)
    result = frame.get(BandPowerResult)
    assert result is not None
    assert "alpha" in result.band_powers_left
    assert "alpha" in result.band_powers_right


def test_artifact_gate_freezes_ema():
    """During speech, EMA should not update (freeze to last clean value)."""
    stage = BandPowerStage(ema_decay=0.5)  # aggressive decay for test visibility

    # Feed clean frames to establish baseline
    for _ in range(5):
        frame = _make_alpha_frame()
        stage.process(frame)
    result_clean = frame.get(BandPowerResult)
    clean_alpha = result_clean.band_powers_avg["alpha"]

    # Feed frame during speech (should freeze)
    frame_speech = _make_alpha_frame()
    frame_speech.set(SpeechResult(speech_active=True))
    frame_speech.set(ClenchResult(jaw_clench=False))
    # Override EEG with garbage — if EMA updates, value would change drastically
    frame_speech.eeg = np.random.randn(4, 256) * 100.0
    stage.process(frame_speech)
    result_speech = frame_speech.get(BandPowerResult)

    # EMA should have frozen — value should be close to clean
    assert abs(result_speech.band_powers_avg["alpha"] - clean_alpha) < clean_alpha * 0.5


def test_none_eeg_safe():
    stage = BandPowerStage()
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    stage.process(frame)
    assert frame.get(BandPowerResult) is None
