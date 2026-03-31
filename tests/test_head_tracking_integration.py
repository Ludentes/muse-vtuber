import math

import numpy as np
import pytest

from muse_vtuber.head_pose import HeadPoseEstimator
from muse_vtuber.outputs.vmc import VMCBoneTransform, split_head_neck


def test_split_identity_gives_identity():
    identity = (0.0, 0.0, 0.0, 1.0)
    neck, head = split_head_neck(identity)
    assert abs(neck.rot_w - 1.0) < 0.01
    assert abs(head.rot_w - 1.0) < 0.01


def test_split_rotation_distributes():
    """A 30° rotation should split ~12° neck + ~18° head."""
    rad = math.radians(30) / 2
    q = (0.0, math.sin(rad), 0.0, math.cos(rad))  # 30° yaw
    neck, head = split_head_neck(q)

    neck_angle = 2 * math.acos(min(1.0, abs(neck.rot_w)))
    head_angle = 2 * math.acos(min(1.0, abs(head.rot_w)))

    assert 8 < math.degrees(neck_angle) < 16   # ~12°
    assert 14 < math.degrees(head_angle) < 22  # ~18°
