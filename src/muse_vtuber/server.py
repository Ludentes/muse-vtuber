"""WebSocket server for the setup/calibration UI.

Broadcasts JSON metrics and BCI events to connected browser clients.
Receives commands (recenter, set_bias) from the frontend.

Runs in a separate thread with its own asyncio event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading

import websockets

log = logging.getLogger("setup_ui")


class SetupUIServer:
    """WebSocket server that bridges the main loop to the browser UI."""

    def __init__(self, port: int = 8765):
        self.port = port
        self._clients: set = set()
        self._command_queue: queue.Queue = queue.Queue(maxsize=32)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: threading.Event = threading.Event()
        self._server = None

    def run(self) -> None:
        """Blocking — call from a thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        async with websockets.serve(self._handler, "0.0.0.0", self.port) as server:
            self._server = server
            log.info("Setup UI server listening on ws://0.0.0.0:%d", self.port)
            while not self._stop_event.is_set():
                await asyncio.sleep(0.1)

    async def _handler(self, ws) -> None:
        self._clients.add(ws)
        log.info("Setup UI client connected (%d total)", len(self._clients))
        try:
            async for message in ws:
                try:
                    cmd = json.loads(message)
                    self._command_queue.put_nowait(cmd)
                except (json.JSONDecodeError, queue.Full):
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            log.info("Setup UI client disconnected (%d total)", len(self._clients))

    def broadcast_metrics(self, data: dict) -> None:
        """Send metrics to all connected clients. Thread-safe."""
        msg = json.dumps({"type": "metrics", **data})
        self._broadcast(msg)

    def broadcast_event(self, data: dict) -> None:
        """Send a BCI event to all connected clients. Thread-safe."""
        msg = json.dumps({"type": "bci_event", **data})
        self._broadcast(msg)

    def _broadcast(self, msg: str) -> None:
        if not self._loop or not self._clients:
            return
        asyncio.run_coroutine_threadsafe(
            self._send_to_all(msg), self._loop
        )

    async def _send_to_all(self, msg: str) -> None:
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send(msg)
            except Exception:
                disconnected.add(ws)
        self._clients -= disconnected

    def poll_command(self) -> dict | None:
        """Non-blocking. Returns a command from the frontend or None."""
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
