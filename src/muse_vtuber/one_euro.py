"""One Euro Filter for quaternions.

Adapts smoothing based on motion speed:
- Slow/still → heavy smoothing (eliminates jitter)
- Fast motion → light smoothing (preserves responsiveness)

Reference: Géry Casiez et al., "1€ Filter", CHI 2012.

Ported from zyphraexps/frontend/src/lib/oneEuroFilter.ts
"""
from __future__ import annotations

import math

# Quaternion = (x, y, z, w) tuple
Quat = tuple[float, float, float, float]

# Speed below this (rad/s) is treated as zero (sensor noise at rest)
SPEED_DEADZONE = 0.15  # ~8.6°/s


def slerp(a: Quat, b: Quat, t: float) -> Quat:
    """Spherical linear interpolation between quaternions."""
    # Ensure shortest path
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    if dot < 0:
        b = (-b[0], -b[1], -b[2], -b[3])
        dot = -dot

    dot = min(1.0, dot)

    if dot > 0.9995:
        # Linear interpolation for very close quaternions
        result = tuple(a[i] + t * (b[i] - a[i]) for i in range(4))
        norm = math.sqrt(sum(c * c for c in result))
        return tuple(c / norm for c in result)

    theta_0 = math.acos(dot)
    theta = theta_0 * t
    sin_theta = math.sin(theta)
    sin_theta_0 = math.sin(theta_0)

    s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
    s1 = sin_theta / sin_theta_0

    return tuple(s0 * a[i] + s1 * b[i] for i in range(4))


def _quat_dot(a: Quat, b: Quat) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]


class OneEuroQuaternionFilter:
    """Adaptive low-pass filter for quaternions."""

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.5,
        d_cutoff: float = 1.0,
    ):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._prev_filtered: Quat | None = None
        self._prev_raw: Quat | None = None
        self._prev_timestamp: float = 0.0

    def _smoothing_factor(self, rate: float, cutoff: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        te = 1.0 / rate
        return 1.0 / (1.0 + tau / te)

    def filter(self, q: Quat, timestamp: float) -> Quat:
        if self._prev_filtered is None or self._prev_raw is None:
            self._prev_filtered = q
            self._prev_raw = q
            self._prev_timestamp = timestamp
            return q

        dt = timestamp - self._prev_timestamp
        if dt <= 0:
            return self._prev_filtered
        self._prev_timestamp = timestamp
        rate = 1.0 / dt

        # Align to shortest path
        raw_aligned = q
        if _quat_dot(raw_aligned, self._prev_raw) < 0:
            raw_aligned = (-q[0], -q[1], -q[2], -q[3])

        # Estimate angular speed
        dot = min(1.0, abs(_quat_dot(raw_aligned, self._prev_raw)))
        angle = 2 * math.acos(dot)
        speed = angle / dt

        self._prev_raw = raw_aligned

        # Smooth speed estimate
        # TODO: this is stateless (no prev_speed memory) — matches the TS source
        # but a proper 1€ filter would blend: alpha * speed + (1-alpha) * prev_speed
        d_alpha = self._smoothing_factor(rate, self.d_cutoff)
        smoothed_speed = d_alpha * speed

        # Dead zone
        effective_speed = 0.0 if smoothed_speed < SPEED_DEADZONE else smoothed_speed

        # Adaptive cutoff
        cutoff = self.min_cutoff + self.beta * effective_speed
        alpha = self._smoothing_factor(rate, cutoff)

        # Slerp toward new value
        self._prev_filtered = slerp(self._prev_filtered, raw_aligned, alpha)
        return self._prev_filtered

    def reset(self) -> None:
        self._prev_filtered = None
        self._prev_raw = None
        self._prev_timestamp = 0.0
