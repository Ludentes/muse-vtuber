"""Face tracking → VTube Studio parameter bridge.

Webcam → FaceLandmarker → 58-d features → CartoonAlive MLP → VTS InjectParameterData.
Runs as an asyncio task alongside the BCI pipeline.

Post-processing pipeline per frame:
  1. MLP inference → raw params
  2. Neutral calibration (subtract 30-frame baseline captured at startup)
  3. Per-param EMA smoothing (alpha differs by param group)
  4. Inject to VTS
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import numpy as np
import websockets

from muse_vtuber.mlp.infer import Predictor
from muse_vtuber.outputs.face_tracking import feature_stream

log = logging.getLogger(__name__)

_TOKEN_FILE = Path.home() / ".config" / "muse-vtuber" / "face_tracking_vts_token.txt"
_PLUGIN_NAME = "muse-vtuber-face"
_PLUGIN_DEVELOPER = "muse-vtuber"

# EMA alpha per param group. Lower = more smoothing (slower response).
# alpha=1.0 means no smoothing (pass-through).
_SMOOTH_ALPHA: dict[str, float] = {
    "AngleX": 0.3, "AngleY": 0.3, "AngleZ": 0.3,         # head pose — fast
    "EyeLOpen": 0.3, "EyeROpen": 0.3,                     # blink — fast
    "EyeBallX": 0.3, "EyeBallY": 0.3,                     # gaze — fast
    "EyeLSmile": 0.4, "EyeRSmile": 0.4,                   # eye shape — moderate
    "MouthOpenY": 0.4, "MouthForm": 0.4,                   # mouth — moderate
    "BrowLY": 0.6, "BrowRY": 0.6,                         # brows — slow
    "BrowLAngle": 0.6, "BrowRAngle": 0.6,
    "Cheek": 0.5,
}
_DEFAULT_ALPHA = 0.4

_CALIBRATION_FRAMES = 30  # ~1s at 30fps


class _ParamSmoother:
    def __init__(self, param_ids: list[str]) -> None:
        self._alphas = np.array(
            [_SMOOTH_ALPHA.get(p, _DEFAULT_ALPHA) for p in param_ids],
            dtype=np.float32,
        )
        self._prev: np.ndarray | None = None

    def smooth(self, values: np.ndarray) -> np.ndarray:
        if self._prev is None:
            self._prev = values.copy()
            return values
        self._prev = self._alphas * self._prev + (1.0 - self._alphas) * values
        return self._prev.copy()


async def _authenticate(ws) -> None:
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    saved = _TOKEN_FILE.read_text().strip() if _TOKEN_FILE.exists() else ""

    req = {
        "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
        "requestID": "auth", "messageType": "AuthenticationRequest",
        "data": {
            "pluginName": _PLUGIN_NAME, "pluginDeveloper": _PLUGIN_DEVELOPER,
            "authenticationToken": saved,
        },
    }
    await ws.send(json.dumps(req))
    resp = json.loads(await ws.recv())
    if resp["data"].get("authenticated"):
        log.info("face_params: VTS authenticated")
        return

    token_req = {
        "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
        "requestID": "token", "messageType": "AuthenticationTokenRequest",
        "data": {"pluginName": _PLUGIN_NAME, "pluginDeveloper": _PLUGIN_DEVELOPER},
    }
    await ws.send(json.dumps(token_req))
    token_resp = json.loads(await ws.recv())
    token = token_resp["data"]["authenticationToken"]
    _TOKEN_FILE.write_text(token)

    req["data"]["authenticationToken"] = token
    await ws.send(json.dumps(req))
    final = json.loads(await ws.recv())
    if not final["data"].get("authenticated"):
        raise RuntimeError("face_params: VTS auth failed after token request")
    log.info("face_params: VTS authenticated (new token)")


async def _inject(ws, params: dict[str, float]) -> None:
    payload = {
        "apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
        "requestID": "inject", "messageType": "InjectParameterDataRequest",
        "data": {
            "faceFound": True, "mode": "set",
            "parameterValues": [{"id": k, "value": float(v)} for k, v in params.items()],
        },
    }
    await ws.send(json.dumps(payload))
    await ws.recv()


async def run(
    predictor: Predictor,
    camera_index: int = 0,
    vts_port: int = 8001,
    landmarker_model: Path | None = None,
) -> None:
    """Main loop: webcam → MLP → VTS. Reconnects on disconnect."""
    smoother = _ParamSmoother(predictor._param_ids)

    # Neutral calibration: capture baseline before injecting anything
    baseline: np.ndarray | None = None
    calib_buf: list[np.ndarray] = []
    log.info(
        "face_params: calibrating neutral face (%d frames) — look straight ahead",
        _CALIBRATION_FRAMES,
    )

    url = f"ws://localhost:{vts_port}"
    while True:
        try:
            async with websockets.connect(url) as ws:
                await _authenticate(ws)
                log.info(
                    "face_params: streaming camera %d → VTS %s", camera_index, url
                )
                async for features in feature_stream(
                    camera_index=camera_index, landmarker_model=landmarker_model
                ):
                    raw = predictor.predict(features)
                    values = np.array(
                        [raw[p] for p in predictor._param_ids], dtype=np.float32
                    )

                    # Phase 1: collect calibration baseline
                    if baseline is None:
                        calib_buf.append(values.copy())
                        if len(calib_buf) >= _CALIBRATION_FRAMES:
                            baseline = np.mean(calib_buf, axis=0)
                            log.info("face_params: calibration done")
                        continue  # don't inject during calibration

                    # Phase 2: subtract baseline, smooth, inject
                    calibrated = values - baseline
                    smoothed = smoother.smooth(calibrated)
                    final = dict(zip(predictor._param_ids, smoothed.tolist()))
                    await _inject(ws, final)

        except (OSError, websockets.ConnectionClosed) as e:
            log.warning("face_params: VTS lost (%s), retrying in 3s", e)
            await asyncio.sleep(3)
