"""Webcam → 58-d feature vector (blendshapes + pose), async generator.

Uses MediaPipe FaceLandmarker (Tasks API) to extract:
  - 52 ARKit blendshape scores
  - 6 head pose values: rx, ry, rz (degrees), tx, ty, tz

Total: 58 floats per frame. Compatible with humanoid-anime-bs58 checkpoint.

Requires face_landmarker.task model file (not bundled with mediapipe).
Download URL: see docs/integration/muse-bridge-mlp-integration.md
Default location: ~/.cache/muse-vtuber/face_landmarker.task
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

_DEFAULT_LANDMARKER = Path.home() / ".cache" / "muse-vtuber" / "face_landmarker.task"


def _build_features(result) -> np.ndarray | None:
    """Extract 58-d feature vector from a FaceLandmarker result.

    Returns None if no face was detected or blendshapes unavailable.
    """
    if not result.face_blendshapes or not result.facial_transformation_matrixes:
        return None

    # 52 ARKit blendshape scores (MediaPipe order)
    bs_cats = result.face_blendshapes[0]
    bs = np.array([c.score for c in bs_cats], dtype=np.float32)
    if len(bs) != 52:
        tmp = np.zeros(52, dtype=np.float32)
        tmp[: min(len(bs), 52)] = bs[:52]
        bs = tmp

    # 6-d head pose from facial transformation matrix (4×4)
    mat = np.array(result.facial_transformation_matrixes[0], dtype=np.float32)
    R = mat[:3, :3]
    t = mat[:3, 3]
    sy = float(np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2))
    if sy > 1e-6:
        rx = np.arctan2(R[2, 1], R[2, 2])
        ry = np.arctan2(-R[2, 0], sy)
        rz = np.arctan2(R[1, 0], R[0, 0])
    else:
        rx = np.arctan2(-R[1, 2], R[1, 1])
        ry = np.arctan2(-R[2, 0], sy)
        rz = 0.0
    pose = np.array(
        [np.rad2deg(rx), np.rad2deg(ry), np.rad2deg(rz), t[0], t[1], t[2]],
        dtype=np.float32,
    )

    return np.concatenate([bs, pose])  # (58,)


async def feature_stream(
    camera_index: int = 0,
    max_fps: float = 30.0,
    landmarker_model: Path | None = None,
) -> AsyncGenerator[np.ndarray, None]:
    """Async generator that yields (58,) feature arrays from webcam.

    Args:
        camera_index: OpenCV camera index (0 = default webcam).
        max_fps: cap frame rate to avoid saturating the consumer.
        landmarker_model: path to face_landmarker.task; defaults to
            ~/.cache/muse-vtuber/face_landmarker.task.
    Yields:
        float32 ndarray of shape (58,): [blendshapes(52) | pose(6)]
    """
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as e:
        raise ImportError(
            "mediapipe not installed — run: uv sync --extra face"
        ) from e

    model_path = landmarker_model or _DEFAULT_LANDMARKER
    if not model_path.exists():
        raise FileNotFoundError(
            f"FaceLandmarker model not found at {model_path}\n"
            "Download face_landmarker.task — see "
            "docs/integration/muse-bridge-mlp-integration.md"
        )

    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
        num_faces=1,
        running_mode=vision.RunningMode.IMAGE,
    )

    interval = 1.0 / max_fps
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {camera_index}")

    loop = asyncio.get_running_loop()
    landmarker = vision.FaceLandmarker.create_from_options(options)

    try:
        while True:
            t0 = loop.time()

            ok, frame = await loop.run_in_executor(None, cap.read)
            if not ok:
                log.warning("Camera read failed, retrying")
                await asyncio.sleep(0.1)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            result = await loop.run_in_executor(None, landmarker.detect, mp_image)
            features = _build_features(result)
            if features is not None:
                yield features

            elapsed = loop.time() - t0
            sleep = max(0.0, interval - elapsed)
            if sleep:
                await asyncio.sleep(sleep)
    finally:
        cap.release()
        landmarker.close()
