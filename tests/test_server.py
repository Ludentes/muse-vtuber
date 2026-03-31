import asyncio
import json
import threading
import time

import pytest
import websockets

from muse_vtuber.server import SetupUIServer

pytestmark = [
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning"),
]

_PORT_COUNTER = 18760


def _next_port():
    global _PORT_COUNTER
    _PORT_COUNTER += 1
    return _PORT_COUNTER


@pytest.fixture
def ws_server():
    port = _next_port()
    server = SetupUIServer(port=port)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for event loop to be ready
    for _ in range(50):
        if server._loop is not None and server._loop.is_running():
            break
        time.sleep(0.05)
    yield server, port
    server.stop()
    thread.join(timeout=2.0)


@pytest.mark.asyncio
async def test_connect_and_receive_metrics(ws_server):
    server, port = ws_server
    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await asyncio.sleep(0.1)  # ensure client is registered
        server.broadcast_metrics({
            "signal_quality": {"TP9": 0.9},
            "fit_status": "good",
            "head_pose": {"pitch": 0, "yaw": 0, "roll": 0},
            "settle_progress": 1.0,
            "initialized": True,
        })
        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
        data = json.loads(msg)
        assert data["type"] == "metrics"
        assert data["signal_quality"]["TP9"] == 0.9


@pytest.mark.asyncio
async def test_receive_command(ws_server):
    server, port = ws_server
    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps({"type": "recenter"}))
        await asyncio.sleep(0.2)
        cmd = server.poll_command()
        assert cmd is not None
        assert cmd["type"] == "recenter"


@pytest.mark.asyncio
async def test_broadcast_event(ws_server):
    server, port = ws_server
    async with websockets.connect(f"ws://localhost:{port}") as ws:
        await asyncio.sleep(0.1)  # ensure client is registered
        server.broadcast_event({
            "kind": "blink",
            "confidence": 0.95,
        })
        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
        data = json.loads(msg)
        assert data["type"] == "bci_event"
        assert data["kind"] == "blink"


def test_no_command_returns_none(ws_server):
    server, _ = ws_server
    assert server.poll_command() is None
