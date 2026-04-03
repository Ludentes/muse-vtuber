"""VTube Studio WebSocket plugin client.

Connects to VTube Studio on port 8001, authenticates, creates custom
parameters, and injects EEG values at pipeline rate.

VTS API docs: https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

log = logging.getLogger("vts")

_API_NAME = "VTubeStudioPublicAPI"
_API_VERSION = "1.0"

# Custom parameters we create in VTube Studio
PARAMETERS = [
    ("MuseBlink", 0.0, 0.0, 1.0),       # (name, default, min, max)
    ("MuseFocus", 0.0, 0.0, 1.0),
    ("MuseRelaxation", 0.0, 0.0, 1.0),
    ("MuseClench", 0.0, 0.0, 1.0),
]

# Token persistence file
_TOKEN_PATH = Path.home() / ".config" / "muse-vtuber" / "vts_token.txt"


def _request(message_type: str, data: dict | None = None) -> str:
    msg: dict[str, object] = {
        "apiName": _API_NAME,
        "apiVersion": _API_VERSION,
        "requestID": message_type,
        "messageType": message_type,
    }
    if data is not None:
        msg["data"] = data
    return json.dumps(msg)


def build_auth_request(plugin_name: str, developer: str) -> str:
    return _request("AuthenticationTokenRequest", {
        "pluginName": plugin_name,
        "pluginDeveloper": developer,
    })


def build_auth_with_token(token: str) -> str:
    return _request("AuthenticationRequest", {
        "pluginName": "muse-vtuber",
        "pluginDeveloper": "Muse VTuber Bridge",
        "authenticationToken": token,
    })


def build_parameter_creation_request(
    name: str, default: float, min_val: float, max_val: float,
) -> str:
    return _request("ParameterCreationRequest", {
        "parameterName": name,
        "explanation": f"Muse VTuber Bridge: {name}",
        "min": min_val,
        "max": max_val,
        "defaultValue": default,
    })


def build_parameter_injection_request(
    params: list[tuple[str, float]],
    weights: dict[str, float] | None = None,
) -> str:
    """Build a VTS parameter injection request.

    weights: optional per-parameter weight map. If a param name is present,
    that weight is included in the entry. Omitted weights default to 1.0 in VTS
    (full plugin override). Use weight < 1.0 to blend with camera tracking:
        Final = (plugin_value × weight) + (camera_value × (1 - weight))
    """
    values = []
    for name, value in params:
        entry: dict = {"id": name, "value": value}
        if weights and name in weights and weights[name] != 1.0:
            entry["weight"] = weights[name]
        values.append(entry)
    return _request("InjectParameterDataRequest", {
        "parameterValues": values,
    })


class VTSClient:
    """Async WebSocket client for VTube Studio plugin API."""

    def __init__(self, port: int = 8001):
        self.port = port
        self._ws = None
        self._authenticated = False
        self._token: str | None = None
        self._drain_task: asyncio.Task | None = None

    async def connect(self) -> bool:
        """Connect to VTube Studio and authenticate."""
        try:
            import websockets
            self._ws = await websockets.connect(f"ws://localhost:{self.port}")
        except Exception as e:
            log.warning("Cannot connect to VTube Studio on port %d: %s", self.port, e)
            return False

        # Try saved token first
        self._token = self._load_token()
        if self._token:
            if await self._auth_with_token(self._token):
                self._authenticated = True
                log.info("Authenticated with saved token")
                await self._create_parameters()
                await self._start_drain()
                return True

        # Request new token (shows popup in VTube Studio)
        self._token = await self._request_token()
        if self._token:
            self._save_token(self._token)
            if await self._auth_with_token(self._token):
                self._authenticated = True
                log.info("Authenticated with new token")
                await self._create_parameters()
                await self._start_drain()
                return True

        return False

    async def _send_recv(self, msg: str) -> dict | None:
        if self._ws is None:
            return None
        try:
            await self._ws.send(msg)
            response = await self._ws.recv()
            return json.loads(response)
        except Exception as e:
            log.warning("VTS communication error: %s", e)
            return None

    async def _request_token(self) -> str | None:
        resp = await self._send_recv(
            build_auth_request("muse-vtuber", "Muse VTuber Bridge")
        )
        if resp and "data" in resp and "authenticationToken" in resp["data"]:
            return resp["data"]["authenticationToken"]
        return None

    async def _auth_with_token(self, token: str) -> bool:
        resp = await self._send_recv(build_auth_with_token(token))
        if resp and "data" in resp:
            return resp["data"].get("authenticated", False)
        return False

    async def _create_parameters(self) -> None:
        for name, default, min_val, max_val in PARAMETERS:
            await self._send_recv(
                build_parameter_creation_request(name, default, min_val, max_val)
            )
            log.debug("Created VTS parameter: %s", name)

    async def _start_drain(self) -> None:
        """Start background task that reads and discards VTS responses.

        VTS sends a response for every injection request. Without draining,
        the receive buffer fills up and VTS drops the connection.
        """
        async def _drain() -> None:
            assert self._ws is not None
            try:
                async for _ in self._ws:
                    pass  # discard all responses
            except Exception:
                pass  # connection closed

        self._drain_task = asyncio.ensure_future(_drain())

    async def inject(
        self,
        blink: float = 0.0,
        focus: float = 0.0,
        relaxation: float = 0.0,
        clench: float = 0.0,
        face_angle_x: float | None = None,
        face_angle_y: float | None = None,
        face_angle_z: float | None = None,
        eye_open: float | None = None,
        head_tracking_weight: float = 1.0,
    ) -> None:
        """Inject parameter values into VTube Studio.

        EEG params go to custom MuseXxx parameters (always weight=1.0, camera
        never drives these so blending is irrelevant).
        Head tracking angles go to built-in FaceAngleX/Y/Z (degrees).
        Eye open goes to built-in EyeOpenLeft/Right (0=closed, 1=open).

        head_tracking_weight controls blending with VTS camera tracking for
        FaceAngle and EyeOpen params:
            Final = (our_value × weight) + (camera_value × (1 - weight))
        weight=1.0 (default): full IMU override, camera tracking suppressed.
        weight=0.0: camera tracking drives head pose, our values ignored.
        """
        if not self._authenticated or self._ws is None:
            return
        params: list[tuple[str, float]] = [
            ("MuseBlink", blink),
            ("MuseFocus", focus),
            ("MuseRelaxation", relaxation),
            ("MuseClench", clench),
        ]
        head_params: list[str] = []
        if face_angle_x is not None:
            params.append(("FaceAngleX", face_angle_x))
            head_params.append("FaceAngleX")
        if face_angle_y is not None:
            params.append(("FaceAngleY", face_angle_y))
            head_params.append("FaceAngleY")
        if face_angle_z is not None:
            params.append(("FaceAngleZ", face_angle_z))
            head_params.append("FaceAngleZ")
        if eye_open is not None:
            params.append(("EyeOpenLeft", eye_open))
            params.append(("EyeOpenRight", eye_open))
            head_params += ["EyeOpenLeft", "EyeOpenRight"]
        weights = {name: head_tracking_weight for name in head_params} if head_tracking_weight != 1.0 else None
        msg = build_parameter_injection_request(params, weights=weights)
        try:
            await self._ws.send(msg)
        except Exception as e:
            self._authenticated = False
            log.warning("VTS connection lost: %s", e)

    async def close(self) -> None:
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._authenticated = False

    def _load_token(self) -> str | None:
        try:
            if _TOKEN_PATH.exists():
                return _TOKEN_PATH.read_text().strip()
        except Exception as e:
            log.warning("Cannot read VTS token: %s", e)
        return None

    def _save_token(self, token: str) -> None:
        try:
            _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            _TOKEN_PATH.write_text(token)
        except Exception as e:
            log.warning("Cannot save VTS token: %s", e)
