import math

import numpy as np
import pytest


def _quat(axis_angle_deg: float, axis: tuple = (0, 1, 0)) -> tuple[float, float, float, float]:
    """Create quaternion from axis-angle (x, y, z, w)."""
    rad = math.radians(axis_angle_deg) / 2
    s = math.sin(rad)
    c = math.cos(rad)
    return (axis[0] * s, axis[1] * s, axis[2] * s, c)


class TestOneEuroQuaternionFilter:
    def test_first_sample_passthrough(self):
        from muse_vtuber.one_euro import OneEuroQuaternionFilter

        filt = OneEuroQuaternionFilter()
        q_in = (0.0, 0.0, 0.0, 1.0)
        q_out = filt.filter(q_in, timestamp=0.0)
        assert abs(q_out[3] - 1.0) < 0.01  # w ≈ 1

    def test_smooths_jittery_input(self):
        from muse_vtuber.one_euro import OneEuroQuaternionFilter

        filt = OneEuroQuaternionFilter(min_cutoff=0.3, beta=1.5)
        identity = (0.0, 0.0, 0.0, 1.0)

        # Feed identity for a while
        for i in range(20):
            filt.filter(identity, timestamp=i * 0.019)

        # Inject small jitter — output should be smoothed (closer to identity)
        jittery = _quat(3.0)  # 3° rotation — small jitter
        result = filt.filter(jittery, timestamp=20 * 0.019)

        # Output should be less than 3° from identity (smoothed)
        angle = 2 * math.acos(min(1.0, abs(result[3])))
        assert math.degrees(angle) < 3.0

    def test_fast_motion_tracks(self):
        from muse_vtuber.one_euro import OneEuroQuaternionFilter

        filt = OneEuroQuaternionFilter(min_cutoff=0.3, beta=1.5)

        # Move quickly through a sequence
        for i in range(30):
            q = _quat(i * 3.0)  # 3°/frame = fast motion
            result = filt.filter(q, timestamp=i * 0.019)

        # After fast motion, output should track reasonably close
        target = _quat(29 * 3.0)
        # Dot product measures closeness (1.0 = identical)
        dot = sum(a * b for a, b in zip(result, target))
        assert abs(dot) > 0.9  # within ~25° — tracking during fast motion

    def test_reset(self):
        from muse_vtuber.one_euro import OneEuroQuaternionFilter

        filt = OneEuroQuaternionFilter()
        filt.filter((0.0, 0.0, 0.0, 1.0), timestamp=0.0)
        filt.reset()
        # After reset, next sample should be passthrough
        q = _quat(45.0)
        result = filt.filter(q, timestamp=1.0)
        dot = sum(a * b for a, b in zip(result, q))
        assert abs(dot) > 0.99

    def test_speed_deadzone(self):
        """Slow motion (below deadzone) should be heavily smoothed."""
        from muse_vtuber.one_euro import OneEuroQuaternionFilter

        filt = OneEuroQuaternionFilter(min_cutoff=0.3, beta=1.5)
        identity = (0.0, 0.0, 0.0, 1.0)

        # Establish baseline
        for i in range(50):
            filt.filter(identity, timestamp=i * 0.019)

        # Tiny movement — below deadzone
        tiny = _quat(0.5)  # 0.5°
        result = filt.filter(tiny, timestamp=50 * 0.019)
        angle = 2 * math.acos(min(1.0, abs(result[3])))
        # Should be heavily smoothed — barely moved
        assert math.degrees(angle) < 0.5
