import math

import numpy as np
import pytest

from muse_vtuber.head_pose import HeadPoseEstimator


def _identity_imu_sample() -> tuple[np.ndarray, np.ndarray]:
    """Stationary Muse: gravity on Z-up axis, no rotation."""
    accel = np.array([0.0, 0.0, 1.0], dtype=np.float32)  # 1g on Z (up)
    gyro = np.array([0.0, 0.0, 0.0], dtype=np.float32)    # no rotation
    return accel, gyro


class TestHeadPoseEstimator:
    def test_returns_identity_before_settle(self):
        hpe = HeadPoseEstimator()
        accel, gyro = _identity_imu_sample()
        hpe.update(accel, gyro)
        q = hpe.get_quaternion()
        # Before settling, should return identity
        assert abs(q[3] - 1.0) < 0.01  # w ≈ 1

    def test_settles_after_enough_frames(self):
        hpe = HeadPoseEstimator(settle_frames=50)  # faster settle for test
        accel, gyro = _identity_imu_sample()
        for _ in range(60):
            hpe.update(accel, gyro)
        # After settle, should be initialized
        assert hpe.initialized is True

    def test_recenter_resets_to_identity(self):
        hpe = HeadPoseEstimator(settle_frames=10)
        accel, gyro = _identity_imu_sample()
        for _ in range(20):
            hpe.update(accel, gyro)
        hpe.recenter()
        q = hpe.get_quaternion()
        # After recenter with stationary IMU, should be near identity
        angle = 2 * math.acos(min(1.0, abs(q[3])))
        assert math.degrees(angle) < 5.0

    def test_gyro_rotation_produces_movement(self):
        hpe = HeadPoseEstimator(settle_frames=10)
        accel = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        no_gyro = np.array([0.0, 0.0, 0.0], dtype=np.float32)

        # Settle
        for _ in range(20):
            hpe.update(accel, no_gyro)

        # Apply yaw rotation (30 deg/s around Muse Z axis for 1 second)
        yaw_gyro = np.array([0.0, 0.0, 30.0], dtype=np.float32)
        for _ in range(52):  # 52Hz × 1s
            hpe.update(accel, yaw_gyro)

        q = hpe.get_quaternion()
        angle = 2 * math.acos(min(1.0, abs(q[3])))
        # Should have rotated noticeably (exact amount depends on decay)
        assert math.degrees(angle) > 5.0

    def test_yaw_decays_when_still(self):
        hpe = HeadPoseEstimator(settle_frames=10)
        accel = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        no_gyro = np.array([0.0, 0.0, 0.0], dtype=np.float32)

        # Settle
        for _ in range(20):
            hpe.update(accel, no_gyro)

        # Apply rotation
        yaw_gyro = np.array([0.0, 0.0, 30.0], dtype=np.float32)
        for _ in range(26):  # 0.5s of rotation
            hpe.update(accel, yaw_gyro)

        q_before = hpe.get_quaternion()
        angle_before = 2 * math.acos(min(1.0, abs(q_before[3])))

        # Now stay still — yaw should decay
        for _ in range(260):  # 5 seconds still
            hpe.update(accel, no_gyro)

        q_after = hpe.get_quaternion()
        angle_after = 2 * math.acos(min(1.0, abs(q_after[3])))

        assert angle_after < angle_before  # decayed

    def test_reset(self):
        hpe = HeadPoseEstimator(settle_frames=10)
        accel, gyro = _identity_imu_sample()
        for _ in range(20):
            hpe.update(accel, gyro)
        assert hpe.initialized is True
        hpe.reset()
        assert hpe.initialized is False

    def test_settle_progress(self):
        hpe = HeadPoseEstimator(settle_frames=100)
        assert hpe.settle_progress == 0.0
        accel, gyro = _identity_imu_sample()
        for _ in range(50):
            hpe.update(accel, gyro)
        assert 0.4 < hpe.settle_progress < 0.6
        for _ in range(60):
            hpe.update(accel, gyro)
        assert hpe.settle_progress == 1.0
