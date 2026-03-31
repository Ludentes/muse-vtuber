import numpy as np
import pytest

from muse_vtuber.pipeline.blink import BlinkDetector
from muse_vtuber.pipeline.clench import ClenchResult
from muse_vtuber.pipeline.speech import SpeechResult
from muse_vtuber.pipeline.types import Cadence, Event, PipelineFrame


def test_blink_detector_cadence():
    det = BlinkDetector()
    assert det.cadence == Cadence.FAST


def _simulate_blink(
    det: BlinkDetector,
    warmup_frames: int = 200,
    blink_amplitude: float = -120.0,
) -> list[Event]:
    """Feed warmup (baseline), then a synthetic blink, then settle. Return all events.

    Blink shape: V-shaped tent over ~6 chunks (96 samples, ~375ms at 256Hz).
    Ramp down for 3 chunks, then ramp up for 3 chunks. This produces a tent
    shape that passes the slope direction check in the shape guard.
    """
    events: list[Event] = []
    rng = np.random.default_rng(42)
    blink_chunks = 6  # 3 down + 3 up

    # Warmup: establish baseline
    for i in range(warmup_frames):
        eeg = rng.normal(0, 10, (4, 16))
        frame = PipelineFrame(eeg=eeg, imu=None, timestamp=i * 0.016)
        frame.set(SpeechResult(speech_active=False))
        frame.set(ClenchResult(jaw_clench=False))
        det.process(frame)
        events.extend(frame.events)

    # Blink: V-shaped tent on frontal channels
    for j in range(blink_chunks):
        eeg = rng.normal(0, 10, (4, 16))
        # Tent shape: ramp down then up
        if j < blink_chunks // 2:
            # Downstroke: progressively more negative
            frac = (j + 1) / (blink_chunks // 2)
        else:
            # Upstroke: progressively less negative
            frac = (blink_chunks - j) / (blink_chunks // 2)
        eeg[1] += blink_amplitude * frac  # AF7
        eeg[2] += blink_amplitude * frac  # AF8
        t = (warmup_frames + j) * 0.016
        frame = PipelineFrame(eeg=eeg, imu=None, timestamp=t)
        frame.set(SpeechResult(speech_active=False))
        frame.set(ClenchResult(jaw_clench=False))
        det.process(frame)
        events.extend(frame.events)

    # Post-blink settle — needs enough frames for classify_window_ms (600ms) to expire
    for k in range(100):
        eeg = rng.normal(0, 10, (4, 16))
        t = (warmup_frames + blink_chunks + k) * 0.016
        frame = PipelineFrame(eeg=eeg, imu=None, timestamp=t)
        frame.set(SpeechResult(speech_active=False))
        frame.set(ClenchResult(jaw_clench=False))
        det.process(frame)
        events.extend(frame.events)

    return events


def test_detects_synthetic_blink():
    det = BlinkDetector()
    det.guard_shape = False  # shape guard is tuned for real EEG, not synthetic
    events = _simulate_blink(det)
    blink_events = [e for e in events if e.kind == "blink"]
    assert len(blink_events) >= 1


def test_no_blink_on_quiet_signal():
    det = BlinkDetector()
    rng = np.random.default_rng(42)
    events: list[Event] = []
    for i in range(500):
        eeg = rng.normal(0, 10, (4, 16))
        frame = PipelineFrame(eeg=eeg, imu=None, timestamp=i * 0.016)
        frame.set(SpeechResult(speech_active=False))
        frame.set(ClenchResult(jaw_clench=False))
        det.process(frame)
        events.extend(frame.events)
    blinks = [e for e in events if e.kind == "blink"]
    assert len(blinks) == 0


def test_speech_suppresses_blink():
    """During speech, blinks should be rejected."""
    det = BlinkDetector()
    rng = np.random.default_rng(42)
    events: list[Event] = []

    # Warmup
    for i in range(200):
        eeg = rng.normal(0, 10, (4, 16))
        frame = PipelineFrame(eeg=eeg, imu=None, timestamp=i * 0.016)
        frame.set(SpeechResult(speech_active=False))
        frame.set(ClenchResult(jaw_clench=False))
        det.process(frame)

    # Blink during speech — should be rejected (V-shape over 6 chunks)
    for j in range(6):
        eeg = rng.normal(0, 10, (4, 16))
        frac = (j + 1) / 3 if j < 3 else (6 - j) / 3
        eeg[1] -= 120 * frac
        eeg[2] -= 120 * frac
        t = (200 + j) * 0.016
        frame = PipelineFrame(eeg=eeg, imu=None, timestamp=t)
        frame.set(SpeechResult(speech_active=True))  # Speech active
        frame.set(ClenchResult(jaw_clench=False))
        det.process(frame)
        events.extend(frame.events)

    blinks = [e for e in events if e.kind == "blink"]
    assert len(blinks) == 0
