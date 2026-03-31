import math

import numpy as np
import pytest

from muse_vtuber.pipeline.band_power import BandPowerResult
from muse_vtuber.pipeline.focus import FocusRelaxResult, FocusRelaxStage
from muse_vtuber.pipeline.types import BAND_NAMES, Cadence, PipelineFrame


def _make_frame_with_bands(
    alpha: float = 5.0,
    beta: float = 3.0,
    theta: float = 4.0,
) -> PipelineFrame:
    """Create frame with pre-computed band power result."""
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    bands = {b: 1.0 for b in BAND_NAMES}
    bands["alpha"] = alpha
    bands["beta"] = beta
    bands["theta"] = theta
    frame.set(BandPowerResult(
        band_powers_left=dict(bands),
        band_powers_right=dict(bands),
        band_powers_avg=dict(bands),
        band_powers_per_ch={b: [1.0, 1.0, 1.0, 1.0] for b in BAND_NAMES},
    ))
    return frame


def test_focus_cadence():
    stage = FocusRelaxStage()
    assert stage.cadence == Cadence.SLOW


def test_focus_formula_matches_bfivrc():
    """Focus = tanh(1.1 * log(beta / theta))"""
    stage = FocusRelaxStage()
    beta, theta = 8.0, 4.0
    frame = _make_frame_with_bands(beta=beta, theta=theta)
    stage.process(frame)
    result = frame.get(FocusRelaxResult)
    assert result is not None
    expected = math.tanh(1.1 * math.log(beta / theta))
    assert abs(result.focus_avg - expected) < 0.01


def test_relaxation_formula_matches_bfivrc():
    """Relax = tanh(1.1 * log(alpha / theta))"""
    stage = FocusRelaxStage()
    alpha, theta = 10.0, 4.0
    frame = _make_frame_with_bands(alpha=alpha, theta=theta)
    stage.process(frame)
    result = frame.get(FocusRelaxResult)
    assert result is not None
    expected = math.tanh(1.1 * math.log(alpha / theta))
    assert abs(result.relax_avg - expected) < 0.01


def test_unsigned_variants():
    """Unsigned variants clamp to [0, 1]."""
    stage = FocusRelaxStage()
    frame = _make_frame_with_bands(beta=1.0, theta=10.0)  # low focus (negative)
    stage.process(frame)
    result = frame.get(FocusRelaxResult)
    assert result is not None
    assert 0.0 <= result.focus_avg_unsigned <= 1.0
    assert 0.0 <= result.relax_avg_unsigned <= 1.0


def test_zero_theta_safe():
    """Zero theta should not crash (division by zero)."""
    stage = FocusRelaxStage()
    frame = _make_frame_with_bands(theta=0.0)
    stage.process(frame)
    result = frame.get(FocusRelaxResult)
    assert result is not None


def test_no_band_power_noop():
    stage = FocusRelaxStage()
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    stage.process(frame)
    assert frame.get(FocusRelaxResult) is None
