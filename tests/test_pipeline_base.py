import numpy as np
import pytest

from muse_vtuber.pipeline.types import (
    BANDS,
    CH_NAMES,
    Cadence,
    Event,
    PipelineFrame,
)


def test_pipeline_frame_set_get():
    """Typed result storage and retrieval."""
    from dataclasses import dataclass

    @dataclass
    class FakeResult:
        value: float

    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    assert frame.get(FakeResult) is None

    frame.set(FakeResult(value=42.0))
    result = frame.get(FakeResult)
    assert result is not None
    assert result.value == 42.0


def test_pipeline_frame_events():
    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    assert frame.events == []

    frame.events.append(Event(kind="blink", timestamp=1.0, confidence=0.95))
    assert len(frame.events) == 1
    assert frame.events[0].kind == "blink"


def test_bands_defined():
    assert "alpha" in BANDS
    assert "beta" in BANDS
    assert "theta" in BANDS
    assert "delta" in BANDS
    assert "gamma" in BANDS
    for low, high in BANDS.values():
        assert low < high


def test_ch_names():
    assert CH_NAMES == ["TP9", "AF7", "AF8", "TP10"]


# --- Pipeline runner tests ---

from muse_vtuber.pipeline.base import Pipeline, Stage


class CounterStage(Stage):
    name = "counter"
    cadence = Cadence.FAST

    def __init__(self):
        self.count = 0

    def process(self, frame: PipelineFrame) -> None:
        self.count += 1


class SlowStage(Stage):
    name = "slow"
    cadence = Cadence.SLOW

    def __init__(self):
        self.count = 0

    def process(self, frame: PipelineFrame) -> None:
        self.count += 1


class FailingStage(Stage):
    name = "failing"
    cadence = Cadence.FAST

    def process(self, frame: PipelineFrame) -> None:
        raise ValueError("boom")


def test_pipeline_runs_matching_cadence():
    fast = CounterStage()
    slow = SlowStage()
    pipeline = Pipeline(stages=[fast, slow])

    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    pipeline.run(Cadence.FAST, frame)
    assert fast.count == 1
    assert slow.count == 0

    pipeline.run(Cadence.SLOW, frame)
    assert fast.count == 1
    assert slow.count == 1


def test_pipeline_survives_stage_failure():
    failing = FailingStage()
    counter = CounterStage()
    pipeline = Pipeline(stages=[failing, counter])

    frame = PipelineFrame(eeg=None, imu=None, timestamp=1.0)
    pipeline.run(Cadence.FAST, frame)
    # Counter still ran despite failing stage before it
    assert counter.count == 1
