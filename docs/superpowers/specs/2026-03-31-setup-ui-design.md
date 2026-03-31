# Setup & Calibration UI — Design Spec

**Date:** 2026-03-31
**Status:** Draft
**Depends on:** Plan 2 (head tracking) — done

## Problem

Users have no way to verify their Muse 2 headband is fit properly, calibrate head tracking zero-point, or diagnose tracking issues before/during a VTube Studio session. Currently it's trial-and-error: start the bridge, check VTS, wonder why the avatar isn't moving right.

## Solution

A single-page web UI that runs alongside VTube Studio. The Python backend streams data to **both** the browser (WebSocket) and VTS (WebSocket plugin) simultaneously. The UI renders the **same Live2D model** as VTS, driven by BCI data, plus signal quality indicators and bias controls.

## Architecture

```
Muse 2 → BrainFlow → muse-vtuber main loop
                         ├→ Setup UI WebSocket (ws://localhost:8765)
                         │    Binary: EEG (0x01), IMU (0x03)
                         │    JSON: metrics, bci_event
                         ├→ VTube Studio (ws://localhost:8001, plugin API)
                         └→ VMC (udp://127.0.0.1:39539, OSC)
```

Two new subsystems:
1. **Backend WebSocket server** — added to main.py, serves binary sensor frames + JSON metrics
2. **Frontend SPA** — Vite + React + PixiJS + Live2D, served statically or via `pnpm dev`

## Backend: WebSocket Server

### Protocol (matches zyphraexps convention)

**V1: JSON only** (binary frames reserved for future waveform display).

**JSON messages:**
```json
{
  "type": "metrics",
  "signal_quality": { "TP9": 0.85, "AF7": 0.92, "AF8": 0.88, "TP10": 0.78 },
  "fit_status": "good",
  "head_pose": { "pitch": 5.2, "yaw": -3.1, "roll": 0.8 },
  "settle_progress": 0.75,
  "initialized": false
}
```

```json
{
  "type": "bci_event",
  "kind": "blink",
  "confidence": 0.95,
  "timestamp": 1234567890.123
}
```

**Commands from frontend:**
```json
{ "type": "recenter" }
{ "type": "set_bias", "pitch": 5.0, "yaw": 0.0, "roll": -2.0 }
```

### Implementation

New file: `src/muse_vtuber/server.py`

- `asyncio` WebSocket server using the `websockets` library (already a dependency)
- Runs in a **separate thread** with its own event loop (same pattern as VTS client)
- Main loop pushes frames into a `queue.Queue(maxsize=1)` (drop-latest policy)
- Server broadcasts to all connected clients
- Receives commands (recenter, set_bias) and applies them to HeadPoseEstimator

### Signal Quality Computation

New file: `src/muse_vtuber/pipeline/signal_quality.py`

Simple per-channel signal quality metric:
- Compute RMS of high-frequency content (>40Hz) per channel per window
- If HF RMS > threshold → poor contact (high impedance noise)
- Compute variance — flat line (zero variance) = disconnected
- Output: 0.0 (bad) to 1.0 (good) per channel
- Fit status: "good" if all channels > 0.5, "adjust" if any < 0.5, "poor" if any < 0.2

This runs as a SLOW-cadence pipeline stage.

### Bias Application

The `HeadPoseEstimator.get_euler_degrees()` already returns (pitch, yaw, roll). Bias is applied in the main loop before sending to outputs:

```python
pitch_out = pitch + bias_pitch
yaw_out = yaw + bias_yaw
roll_out = roll + bias_roll
```

Bias values are stored on the HeadPoseEstimator instance (thread-safe float assignment). The `set_bias` WebSocket command updates them. Bias applies to **all** outputs (VTS, VMC, and the UI preview).

## Frontend

### Tech Stack

- **Build:** Vite 6 + React 19 + TypeScript
- **UI:** Tailwind CSS 4 + shadcn/ui
- **Live2D:** `@naari3/pixi-live2d-display` (PixiJS v8 + Cubism 5, MIT license)
- **WebSocket:** native `WebSocket` API + reconnect logic

### Layout (Single Page)

```
+-------------------------------------------------------+
|  [Muse VTuber Setup]            [Connected/Disconnected] |
+-------------------------------------------------------+
|                    |                                    |
|   Signal Quality   |        Live2D Avatar              |
|   TP9  [====]  85% |        (PixiJS canvas)            |
|   AF7  [====]  92% |                                    |
|   AF8  [====]  88% |                                    |
|   TP10 [====]  78% |                                    |
|                    |                                    |
|   Fit: GOOD        |                                    |
|                    |                                    |
|   ─────────────── |                                    |
|   Head Tracking    |                                    |
|   Pitch: 5.2      |                                    |
|   Yaw:  -3.1      |                                    |
|   Roll:  0.8      |                                    |
|                    |                                    |
|   ─────────────── |                                    |
|   Bias Adjust      |                                    |
|   Pitch [-----|--] |                                    |
|   Yaw   [-----|--] |                                    |
|   Roll  [-----|--] |                                    |
|   [Reset] [Recenter]|                                   |
|                    |                                    |
|   ─────────────── |                                    |
|   Settle: 75%      |                                    |
|   [Calibrating...] |                                    |
+-------------------------------------------------------+
```

Left sidebar: signal quality + head angles + controls (~300px).
Main area: Live2D avatar canvas (fills remaining space).

### Components

| Component | Purpose |
|-----------|---------|
| `App.tsx` | Root — WebSocket connection, state management |
| `SignalQuality.tsx` | 4 channel bars + fit status badge |
| `HeadTrackingPanel.tsx` | Live pitch/yaw/roll display |
| `BiasControls.tsx` | 3 sliders (±45deg, 1deg steps) + Reset + Recenter buttons |
| `SettleOverlay.tsx` | Progress bar during calibration (overlays avatar) |
| `Live2DAvatar.tsx` | PixiJS canvas + Live2D model loading + parameter driving |
| `ConnectionStatus.tsx` | Green/red dot + reconnect indicator |

### Live2D Parameter Driving

The frontend receives head pose from WebSocket metrics JSON and drives Live2D directly:

```typescript
const model = await Live2DModel.from('path/to/akari.model3.json');

// Every metrics frame (~60Hz):
const coreModel = model.internalModel.coreModel;
coreModel.setParameterValueById('ParamAngleX', metrics.head_pose.yaw);
coreModel.setParameterValueById('ParamAngleY', metrics.head_pose.pitch);
coreModel.setParameterValueById('ParamAngleZ', metrics.head_pose.roll);

// On blink event:
coreModel.setParameterValueById('ParamEyeLOpen', 0.0);
coreModel.setParameterValueById('ParamEyeROpen', 0.0);
// Ease back to 1.0 over 150ms
```

### Model Loading

Two approaches (support both):
1. **Local file path** — user provides path to VTS model folder, backend serves it via HTTP static files
2. **Bundled default** — ship a small free Live2D model for testing without VTS

For V1: user passes `--model /path/to/akari_vts` CLI flag. The backend runs a simple HTTP static file server (separate port or same port, path-based) that serves the model directory. In development, the Vite dev server proxies `/model/` requests to this backend endpoint. In production, the backend serves both the frontend build and model files. Frontend loads from `/model/akari.model3.json`.

### WebSocket Hook

```typescript
// useMuseStream.ts
function useMuseStream(url: string) {
  // Returns:
  //   metrics: { signal_quality, fit_status, head_pose, settle_progress, initialized }
  //   lastEvent: { kind, confidence, timestamp } | null
  //   connected: boolean
  //   sendCommand: (cmd: object) => void
}
```

For V1, the backend sends **only JSON** (metrics at ~30Hz + events). No binary frames — the backend computes signal quality and head pose server-side. Binary EEG/IMU frames can be added later if we want waveform display.

## Config Changes

Add to `AppConfig`:
```python
# Setup UI
ui_enabled: bool = True
ui_port: int = 8765
model_path: str = ""  # path to Live2D model folder
```

CLI flags:
```
--ui-port PORT     Setup UI WebSocket port (default: 8765)
--model PATH       Path to Live2D model folder for setup UI
--no-ui            Disable setup UI server
```

## File Structure

```
muse-vtuber/
  src/muse_vtuber/
    server.py              # NEW: WebSocket server for setup UI
    pipeline/
      signal_quality.py    # NEW: per-channel signal quality stage
  frontend/
    package.json
    vite.config.ts
    tsconfig.json
    src/
      App.tsx
      main.tsx
      hooks/
        useMuseStream.ts
      components/
        SignalQuality.tsx
        HeadTrackingPanel.tsx
        BiasControls.tsx
        SettleOverlay.tsx
        Live2DAvatar.tsx
        ConnectionStatus.tsx
      lib/
        protocol.ts        # Binary frame decoder (ported from zyphraexps)
```

## Testing Strategy

**Backend:**
- `test_server.py` — WebSocket server sends binary frames, receives commands
- `test_signal_quality.py` — signal quality computation on synthetic data
- Existing tests continue to pass (no changes to pipeline stages)

**Frontend:**
- Manual testing with `--synthetic` mode (no hardware needed)
- Verify Live2D model loads and responds to parameter changes
- Verify bias sliders affect both UI preview and VTS output

## Out of Scope (V1)

- EEG waveform display (future: add if needed for debugging)
- Multiple model support / model picker UI
- Saving/loading bias presets
- PPG/heart rate display
- Recording controls

## Done Criteria

- `uv run muse-vtuber --synthetic --vts --model /path/to/akari_vts --debug` starts backend
- Browser at `http://localhost:5173` shows Live2D avatar
- Avatar head moves with synthetic IMU data
- Signal quality bars show per-channel status
- Bias sliders adjust head tracking in both UI and VTS
- Recenter button resets head pose
- Settle progress shown during calibration period
