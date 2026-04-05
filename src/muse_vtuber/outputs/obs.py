"""BCI → OBS ambient effects bridge.

Connects to ZyphraExps EEG backend (ws://localhost:8765), reads metrics,
drives an OBS Color Correction filter via obs-websocket v5.

Prerequisite (one-time OBS setup):
  1. Add a Color Correction filter to a source (e.g. solid-color overlay).
  2. Name the source: "EEG_Overlay"  (configurable via obs_source)
  3. Name the filter: "EEG_Ambient"  (configurable via obs_filter)
  4. Enable obs-websocket: Tools → obs-websocket Settings, port 4455.

Mapping:
  relaxation  (0–1) → saturation 1.5 → 0.0  (relaxed = desaturated/dreamy)
  concentration(0–1)→ hue_shift  0   → +25  (focused = cool blue tint)
  jaw_clench (bool) → brightness +0.3 pulse for 200ms
  heart_rate  (bpm) → gamma 0 → +0.15 at effort (>80 bpm)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import websockets
import obsws_python as obs

log = logging.getLogger(__name__)

_CLENCH_PULSE_SEC = 0.2
_UPDATE_HZ = 20


class ObsBridge:
    def __init__(
        self,
        eeg_url: str = "ws://localhost:8765",
        obs_host: str = "localhost",
        obs_port: int = 4455,
        obs_password: str = "",
        source: str = "EEG_Overlay",
        filter_name: str = "EEG_Ambient",
    ) -> None:
        self._eeg_url = eeg_url
        self._obs_cfg = dict(host=obs_host, port=obs_port, password=obs_password)
        self._source = source
        self._filter = filter_name

        self._concentration: float = 0.0
        self._relaxation: float = 0.0
        self._heart_rate: float = 70.0
        self._clench_until: float = 0.0

    async def _eeg_reader(self) -> None:
        while True:
            try:
                async with websockets.connect(self._eeg_url) as ws:
                    log.info("obs: connected to EEG backend %s", self._eeg_url)
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except (ValueError, TypeError):
                            continue
                        if msg.get("type") != "metrics":
                            continue
                        self._ingest(msg)
            except (OSError, websockets.ConnectionClosed) as e:
                log.warning("obs: EEG WS lost (%s), retrying in 3s", e)
                await asyncio.sleep(3)

    def _ingest(self, msg: dict) -> None:
        brain = msg.get("brain") or {}
        self._concentration = float(brain.get("concentration", self._concentration))
        self._relaxation = float(brain.get("relaxation", self._relaxation))
        ppg = msg.get("ppg") or {}
        if (bpm := ppg.get("heart_rate_bpm")) is not None:
            self._heart_rate = float(bpm)
        imu = msg.get("imu") or {}
        if imu.get("jaw_clench"):
            self._clench_until = time.time() + _CLENCH_PULSE_SEC

    def _compute_settings(self) -> dict:
        return {
            "saturation": round(1.5 - self._relaxation * 1.5, 3),
            "hue_shift": round(self._concentration * 25.0, 2),
            "brightness": 0.3 if time.time() < self._clench_until else 0.0,
            "gamma": round(max(0.0, (self._heart_rate - 80.0) / 400.0), 4),
        }

    async def _obs_writer(self) -> None:
        interval = 1.0 / _UPDATE_HZ
        cl = obs.ReqClient(**self._obs_cfg)
        log.info(
            "obs: writing '%s'→'%s' at %dHz",
            self._source, self._filter, _UPDATE_HZ,
        )
        try:
            while True:
                t0 = asyncio.get_event_loop().time()
                try:
                    cl.set_source_filter_settings(
                        source_name=self._source,
                        filter_name=self._filter,
                        filter_settings=self._compute_settings(),
                        overlay=True,
                    )
                except Exception as e:
                    log.warning("obs: OBS write failed: %s", e)
                await asyncio.sleep(max(0.0, interval - (asyncio.get_event_loop().time() - t0)))
        finally:
            cl.disconnect()

    async def run(self) -> None:
        await asyncio.gather(self._eeg_reader(), self._obs_writer())
