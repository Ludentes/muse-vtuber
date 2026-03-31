"""IMU-based head pose estimator for Muse 2.

Ported from zyphraexps/frontend/src/lib/headPose.ts.

Madgwick AHRS → axis remap (Muse→VRM) → velocity-gated yaw decay → One Euro smoothing → recenter.
"""
from __future__ import annotations

import math

import numpy as np

from muse_vtuber.one_euro import OneEuroQuaternionFilter

# Quaternion = (x, y, z, w)
Quat = tuple[float, float, float, float]

DEG2RAD = math.pi / 180.0

# Tuning constants (validated on Muse 2 hardware)
GYRO_DEADZONE = 2.0        # deg/s — zero below this
STILL_THRESHOLD = 5.0       # deg/s — "still" if gyro magnitude below
STILL_FRAMES_REQUIRED = 10  # ~0.2s at 52Hz
YAW_DECAY_STILL = 0.3       # 30%/s when still
YAW_DECAY_MOVING = 0.02     # 2%/s when moving
DEFAULT_SETTLE_FRAMES = 260  # ~5s at 52Hz
DEFAULT_BETA = 0.8           # Madgwick beta — high for responsiveness


def _quat_multiply(a: Quat, b: Quat) -> Quat:
    """Hamilton product of two quaternions (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_conjugate(q: Quat) -> Quat:
    """Conjugate (inverse for unit quaternions)."""
    return (-q[0], -q[1], -q[2], q[3])


def euler_from_quat_yxz(q: Quat) -> tuple[float, float, float]:
    """Quaternion → Euler angles (YXZ order: yaw, pitch, roll).

    Returns (pitch_x, yaw_y, roll_z) in radians.
    """
    x, y, z, w = q
    # YXZ rotation order
    sinr_cosp = 2 * (w * x + y * z)
    cosr_cosp = 1 - 2 * (x * x + y * y)
    pitch = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    yaw = math.asin(sinp)

    siny_cosp = 2 * (w * z + x * y)
    cosy_cosp = 1 - 2 * (y * y + z * z)
    roll = math.atan2(siny_cosp, cosy_cosp)

    return (pitch, yaw, roll)


def quat_from_euler_yxz(pitch: float, yaw: float, roll: float) -> Quat:
    """Euler angles (YXZ) → quaternion (x, y, z, w)."""
    cx = math.cos(pitch / 2)
    sx = math.sin(pitch / 2)
    cy = math.cos(yaw / 2)
    sy = math.sin(yaw / 2)
    cz = math.cos(roll / 2)
    sz = math.sin(roll / 2)

    # YXZ order
    w = cx * cy * cz + sx * sy * sz
    x = sx * cy * cz + cx * sy * sz
    y = cx * sy * cz - sx * cy * sz
    z = cx * cy * sz - sx * sy * cz

    return (x, y, z, w)


class _MadgwickAHRS:
    """Minimal Madgwick AHRS implementation for 6-axis IMU."""

    def __init__(self, sample_rate: float = 52.0, beta: float = 0.8):
        self.sample_rate = sample_rate
        self.beta = beta
        self.q: Quat = (0.0, 0.0, 0.0, 1.0)  # identity

    def update(self, gx: float, gy: float, gz: float, ax: float, ay: float, az: float) -> None:
        """Update with gyro (rad/s) and accel (g's)."""
        q1, q2, q3, q4 = self.q  # x, y, z, w — but Madgwick uses w,x,y,z internally
        # Convert to Madgwick convention: q = [w, x, y, z]
        qw, qx, qy, qz = q4, q1, q2, q3

        dt = 1.0 / self.sample_rate

        # Rate of change from gyro
        q_dot_w = 0.5 * (-qx * gx - qy * gy - qz * gz)
        q_dot_x = 0.5 * (qw * gx + qy * gz - qz * gy)
        q_dot_y = 0.5 * (qw * gy - qx * gz + qz * gx)
        q_dot_z = 0.5 * (qw * gz + qx * gy - qy * gx)

        # Normalize accelerometer
        a_norm = math.sqrt(ax * ax + ay * ay + az * az)
        if a_norm > 0.001:
            ax /= a_norm
            ay /= a_norm
            az /= a_norm

            # Gradient descent correction
            f1 = 2 * (qx * qz - qw * qy) - ax
            f2 = 2 * (qw * qx + qy * qz) - ay
            f3 = 2 * (0.5 - qx * qx - qy * qy) - az

            j_11 = -2 * qy
            j_12 = 2 * qx
            j_13 = 0.0
            j_21 = 2 * qz
            j_22 = 2 * qw
            j_23 = -4 * qx
            j_31 = -2 * qw
            j_32 = 2 * qz
            j_33 = -4 * qy
            j_41 = 2 * qx
            j_42 = 2 * qy
            j_43 = 0.0

            sw = j_11 * f1 + j_21 * f2 + j_31 * f3
            sx = j_12 * f1 + j_22 * f2 + j_32 * f3
            sy = j_13 * f1 + j_23 * f2 + j_33 * f3
            sz = j_41 * f1 + j_42 * f2 + j_43 * f3

            s_norm = math.sqrt(sw * sw + sx * sx + sy * sy + sz * sz)
            if s_norm > 0:
                sw /= s_norm
                sx /= s_norm
                sy /= s_norm
                sz /= s_norm

            q_dot_w -= self.beta * sw
            q_dot_x -= self.beta * sx
            q_dot_y -= self.beta * sy
            q_dot_z -= self.beta * sz

        qw += q_dot_w * dt
        qx += q_dot_x * dt
        qy += q_dot_y * dt
        qz += q_dot_z * dt

        n = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
        if n > 0:
            qw /= n
            qx /= n
            qy /= n
            qz /= n

        self.q = (qx, qy, qz, qw)  # back to (x, y, z, w)


class HeadPoseEstimator:
    """Muse 2 IMU → head orientation quaternion.

    Ported from zyphraexps/frontend/src/lib/headPose.ts.
    """

    def __init__(
        self,
        beta: float = DEFAULT_BETA,
        sample_rate: float = 52.0,
        settle_frames: int = DEFAULT_SETTLE_FRAMES,
        one_euro_min_cutoff: float = 0.3,
        one_euro_beta: float = 1.5,
    ):
        self._ahrs = _MadgwickAHRS(sample_rate=sample_rate, beta=beta)
        self._sample_rate = sample_rate
        self._settle_frames = settle_frames
        self._home_inverse: Quat | None = None
        self.initialized = False
        self._frame_count = 0
        self._still_frames = 0
        self._one_euro = OneEuroQuaternionFilter(
            min_cutoff=one_euro_min_cutoff,
            beta=one_euro_beta,
        )
        # Bias offsets (degrees) — applied in get_euler_degrees()
        self.bias_pitch: float = 0.0
        self.bias_yaw: float = 0.0
        self.bias_roll: float = 0.0

    def update(self, accel: np.ndarray, gyro: np.ndarray) -> None:
        """Feed one IMU sample. Call at sensor rate (~52Hz).

        Args:
            accel: [ax, ay, az] in g's — raw Muse frame
            gyro: [gx, gy, gz] in deg/s — raw Muse frame
        """
        # Track stillness
        gyro_mag = math.sqrt(float(gyro[0]) ** 2 + float(gyro[1]) ** 2 + float(gyro[2]) ** 2)
        if gyro_mag < STILL_THRESHOLD:
            self._still_frames = min(self._still_frames + 1, STILL_FRAMES_REQUIRED + 1)
        else:
            self._still_frames = 0

        # Apply deadzone
        gx = float(gyro[0]) if abs(float(gyro[0])) >= GYRO_DEADZONE else 0.0
        gy = float(gyro[1]) if abs(float(gyro[1])) >= GYRO_DEADZONE else 0.0
        gz = float(gyro[2]) if abs(float(gyro[2])) >= GYRO_DEADZONE else 0.0

        # Feed AHRS (gyro in rad/s)
        self._ahrs.update(
            gx * DEG2RAD, gy * DEG2RAD, gz * DEG2RAD,
            float(accel[0]), float(accel[1]), float(accel[2]),
        )

        self._frame_count += 1

        if not self.initialized and self._frame_count >= self._settle_frames:
            self.recenter()
            self.initialized = True

    def _muse_to_vrm(self, q: Quat) -> Quat:
        """Remap from Muse frame to VRM/Three.js frame.

        Muse: X=forward, Y=right, Z=up
        VRM:  X=right, Y=up, Z=forward
        """
        return (q[1], q[2], q[0], q[3])

    def get_quaternion(self) -> Quat:
        """Get head orientation relative to home pose.

        Returns (x, y, z, w) identity quaternion until initialized.
        """
        if not self.initialized:
            return (0.0, 0.0, 0.0, 1.0)

        current = self._ahrs.q

        # Apply home offset: relative = homeInverse * current
        relative = current
        if self._home_inverse is not None:
            relative = _quat_multiply(self._home_inverse, current)

        # Remap to VRM frame
        remapped = self._muse_to_vrm(relative)

        # Decompose for yaw decay + pitch invert
        pitch, yaw, roll = euler_from_quat_yxz(remapped)

        # Invert pitch (VRM convention)
        pitch = -pitch

        # Velocity-gated yaw decay
        is_still = self._still_frames >= STILL_FRAMES_REQUIRED
        decay_rate = YAW_DECAY_STILL if is_still else YAW_DECAY_MOVING
        decay_per_frame = 1 - (1 - decay_rate) ** (1 / self._sample_rate)
        yaw *= (1 - decay_per_frame)

        # Recompose
        result = quat_from_euler_yxz(pitch, yaw, roll)

        # One Euro smoothing
        timestamp = self._frame_count / self._sample_rate
        result = self._one_euro.filter(result, timestamp)

        return result

    def get_euler_degrees(self) -> tuple[float, float, float]:
        """Get head orientation as (pitch, yaw, roll) in degrees.

        Convenience wrapper for VTube Studio FaceAngleX/Y/Z injection.
        Returns (0, 0, 0) until initialized.
        """
        q = self.get_quaternion()
        pitch, yaw, roll = euler_from_quat_yxz(q)
        return (
            math.degrees(pitch) + self.bias_pitch,
            math.degrees(yaw) + self.bias_yaw,
            math.degrees(roll) + self.bias_roll,
        )

    def recenter(self) -> None:
        """Store current orientation as home (looking straight ahead)."""
        self._home_inverse = _quat_conjugate(self._ahrs.q)
        self.initialized = True

    @property
    def settle_progress(self) -> float:
        if self.initialized:
            return 1.0
        return min(1.0, self._frame_count / self._settle_frames)

    def reset(self) -> None:
        self._ahrs = _MadgwickAHRS(
            sample_rate=self._sample_rate,
            beta=self._ahrs.beta,
        )
        self._home_inverse = None
        self.initialized = False
        self._frame_count = 0
        self._still_frames = 0
        self._one_euro.reset()
