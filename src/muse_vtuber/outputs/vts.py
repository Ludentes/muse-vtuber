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
    msg = {
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
    weight: float = 1.0,
) -> str:
    values = []
    for name, value in params:
        entry: dict = {"id": name, "value": value}
        if weight != 1.0:
            entry["weight"] = weight
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
                return True

        # Request new token (shows popup in VTube Studio)
        self._token = await self._request_token()
        if self._token:
            self._save_token(self._token)
            if await self._auth_with_token(self._token):
                self._authenticated = True
                log.info("Authenticated with new token")
                await self._create_parameters()
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

    async def inject(
        self,
        blink: float = 0.0,
        focus: float = 0.0,
        relaxation: float = 0.0,
        clench: float = 0.0,
    ) -> None:
        """Inject parameter values into VTube Studio."""
        if not self._authenticated or self._ws is None:
            return
        params = [
            ("MuseBlink", blink),
            ("MuseFocus", focus),
            ("MuseRelaxation", relaxation),
            ("MuseClench", clench),
        ]
        msg = build_parameter_injection_request(params)
        try:
            await self._ws.send(msg)
            # Don't wait for response — fire and forget for injection
        except Exception as e:
            self._authenticated = False
            log.warning("VTS connection lost, will retry: %s", e)

    async def close(self) -> None:
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
