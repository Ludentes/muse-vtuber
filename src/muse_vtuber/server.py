"""WebSocket server for the setup/calibration UI.

Broadcasts JSON metrics and BCI events to connected browser clients.
Receives commands (recenter, set_bias) from the frontend.

Runs in a separate thread with its own asyncio event loop.

Also provides a static HTTP file server for Live2D model directories.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import queue
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

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


class _CORSHandler(SimpleHTTPRequestHandler):
    """Static file handler with CORS headers for Vite dev proxy.

    Patches .model3.json files to inject HitAreas:[] if missing,
    working around a bug in pixi-live2d-display where setupHitAreas()
    crashes on models without hit area definitions.
    """

    def do_GET(self) -> None:
        # Intercept .model3.json to patch missing HitAreas
        if self.path.endswith(".model3.json"):
            self._serve_patched_model3()
        else:
            super().do_GET()

    def _serve_patched_model3(self) -> None:
        path = self.translate_path(self.path)
        try:
            with open(path, "r") as f:
                data = json.loads(f.read())
        except (FileNotFoundError, json.JSONDecodeError):
            self.send_error(404)
            return

        if "HitAreas" not in data:
            data["HitAreas"] = []
            log.info("Patched %s: injected empty HitAreas", self.path)

        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        log.debug("Model server: %s", format % args)


class ModelFileServer:
    """HTTP static file server for a Live2D model directory.

    Serves files from model_dir on the given port. Runs in a daemon thread.
    """

    def __init__(self, model_dir: str | Path, port: int = 8766):
        self.model_dir = Path(model_dir)
        self.port = port
        self._httpd: HTTPServer | None = None

    def run(self) -> None:
        """Blocking — call from a thread."""
        handler = functools.partial(_CORSHandler, directory=str(self.model_dir))
        self._httpd = HTTPServer(("0.0.0.0", self.port), handler)
        log.info("Model file server on http://0.0.0.0:%d (dir=%s)", self.port, self.model_dir)
        self._httpd.serve_forever()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
