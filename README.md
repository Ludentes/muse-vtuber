# Muse VTuber Bridge

Bridge BCI hardware (Muse 2 EEG headband) to VTuber avatar software. Translates brain signals and head motion into real-time avatar control via VMC, VTube Studio, and VRChat OSC protocols.

**What it does:** Wear a Muse 2 headband, and your VTuber avatar blinks when you blink, clenches its jaw when you clench, tracks your head movement, and responds to your focus/relaxation levels — all detected from EEG and IMU sensors.

## Features

- **Head tracking** — 6-axis IMU fusion (Madgwick AHRS + One Euro smoothing) for responsive, drift-free head rotation
- **Blink detection** — MAD-based adaptive threshold with 7-layer guard chain (speech, motion, clench, shape, refractory)
- **Jaw clench detection** — Temporal EMG bandpass (20-45Hz) with duration gating
- **Focus & relaxation** — Real-time neurofeedback via beta/theta and alpha/theta ratios
- **Signal quality monitoring** — Per-channel PSD-based electrode fit detection
- **Multiple output protocols** — VMC (UDP/OSC), VTube Studio (WebSocket), VRChat OSC
- **Setup UI** — Browser-based calibration tool with Live2D avatar preview, bias sliders, and signal quality display

## Architecture

```
Muse 2 (Bluetooth)
  │
  ▼
BrainFlowSource ──→ EEG (4ch @ 256Hz) + IMU (6ch @ 52Hz)
  │
  ▼
Pipeline (FAST @ 60Hz)          Pipeline (SLOW @ 1Hz)
  ├─ SpeechDetector               ├─ BandPowerStage (Welch PSD)
  ├─ BlinkDetector                ├─ FocusRelaxStage (β/θ, α/θ)
  └─ ClenchDetector               └─ SignalQualityStage
  │
  ▼
HeadPoseEstimator (Madgwick AHRS → yaw decay → One Euro)
  │
  ▼
Output Sinks (simultaneous)
  ├─ VMC (UDP/OSC) ──→ Warudo, VSeeFace, VMagicMirror
  ├─ VTube Studio (WebSocket) ──→ VTube Studio
  └─ Setup UI (WebSocket) ──→ Browser calibration tool
```

## Requirements

- **Python 3.11+**
- **uv** (Python package manager) — [install](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 18+** and **pnpm** (for the setup UI frontend)
- **Muse 2** headband (or use `--synthetic` for testing without hardware)

## Installation

```bash
# Clone
git clone <repo-url>
cd muse-vtuber

# Install Python dependencies
uv sync --extra dev

# Install frontend dependencies (optional, for setup UI)
cd frontend && pnpm install && cd ..
```

## Quick Start

### With Synthetic Board (no hardware)

```bash
# Terminal 1 — backend
uv run muse-vtuber --synthetic --debug

# Terminal 2 — setup UI (optional)
cd frontend && pnpm dev
# Open http://localhost:5173
```

### With Real Muse 2

```bash
# Find your Muse 2 MAC address (e.g., via bluetoothctl)
uv run muse-vtuber --mac 00:55:DA:B3:9D:XX --debug
```

### With VTube Studio

1. Open VTube Studio, enable the API plugin (Settings > API > Start)
2. Run the bridge with `--vts`:

```bash
uv run muse-vtuber --mac 00:55:DA:B3:9D:XX --vts --debug
```

3. Accept the authentication prompt in VTube Studio (first time only; token is saved to `~/.config/muse-vtuber/vts_token.txt`)

### With Setup UI + Live2D Preview

The setup UI lets you verify headband fit, calibrate head tracking, and preview the avatar in-browser.

```bash
# Terminal 1 — backend with model path
uv run muse-vtuber --mac 00:55:DA:B3:9D:XX --vts \
  --model "/path/to/Live2DModels/your_model" --debug

# Terminal 2 — frontend dev server
cd frontend && pnpm dev
```

Open http://localhost:5173 to see the setup UI with:
- Per-channel signal quality bars and fit status
- Live head pose angles (pitch, yaw, roll)
- Live2D avatar preview driven by BCI data
- Bias sliders (±45 degrees) for pitch/yaw/roll offset
- Recenter button to reset head tracking origin
- Settle/calibration progress overlay

The `--model` path should point to a directory containing a `.model3.json` file (same format as VTube Studio models).

## Configuration

### CLI Arguments

```
uv run muse-vtuber --help

Options:
  --config PATH       Path to config.toml
  --board-id ID       BrainFlow board ID or name (default: MUSE_2_BOARD)
  --mac ADDRESS       Device Bluetooth MAC address
  --synthetic         Use synthetic board (no hardware needed)
  --vmc-port PORT     VMC output port (default: 39539)
  --osc               Enable VRChat OSC output
  --osc-port PORT     VRChat OSC port (default: 9000)
  --vts               Enable VTube Studio plugin
  --vts-port PORT     VTube Studio API port (default: 8001)
  --no-ui             Disable setup UI WebSocket server
  --ui-port PORT      Setup UI WebSocket port (default: 8765)
  --model PATH        Path to Live2D model directory
  --debug             Enable debug logging
```

### Config File

Place a `config.toml` at `~/.config/muse-vtuber/config.toml` or pass `--config path/to/config.toml`.

```toml
[device]
board_id = "MUSE_2_BOARD"
mac_address = "00:55:DA:B3:9D:XX"

[processing]
ema_decay = 0.04

[outputs.vmc]
enabled = true
host = "127.0.0.1"
port = 39539

[outputs.vts]
enabled = true
port = 8001

[head_tracking]
enabled = true
madgwick_beta = 0.8           # Higher = more responsive, lower = smoother
smoothing_min_cutoff = 0.3    # One Euro filter min cutoff
smoothing_beta = 1.5          # One Euro filter speed coefficient
```

CLI arguments override config file values.

## Output Protocols

### VMC (Virtual Motion Capture)

Enabled by default. Sends OSC messages over UDP to port 39539.

**Compatible apps:** Warudo, VSeeFace, VMagicMirror, VNyan, and other VMC-compatible receivers.

**Blendshapes sent:**
| Blendshape | Source | Range |
|---|---|---|
| `Blink` | Blink detector | 0 or 1 |
| `muse_clench` | Jaw clench detector | 0 or 1 |
| `muse_focus` | Beta/theta ratio | 0.0 – 1.0 |
| `muse_relaxation` | Alpha/theta ratio | 0.0 – 1.0 |

**Bones sent:**
| Bone | Source |
|---|---|
| `Head` (60% weight) | IMU head tracking |
| `Neck` (40% weight) | IMU head tracking |

### VTube Studio

Enabled with `--vts`. Connects via WebSocket to the VTube Studio API.

**Custom parameters created:**
| Parameter | Source | Range |
|---|---|---|
| `MuseBlink` | Blink detector | 0 – 1 |
| `MuseClench` | Jaw clench detector | 0 – 1 |
| `MuseFocus` | Beta/theta ratio | 0 – 1 |
| `MuseRelaxation` | Alpha/theta ratio | 0 – 1 |

**Built-in parameters injected:**
| Parameter | Source |
|---|---|
| `FaceAngleX` | Head yaw (degrees) |
| `FaceAngleY` | Head pitch (degrees) |
| `FaceAngleZ` | Head roll (degrees) |

### VRChat OSC

Enabled with `--osc`. Sends OSC messages to VRChat's OSC input (default port 9000).

## Pipeline Stages

### FAST cadence (~60Hz)

| Stage | What it detects | Method |
|---|---|---|
| **SpeechDetector** | Sustained temporal EMG (talking/humming) | High-frequency RMS with adaptive baseline |
| **BlinkDetector** | Eye blinks | MAD-based adaptive threshold, 7-layer guard chain |
| **ClenchDetector** | Jaw clenching | 20-45Hz bandpass RMS with duration gate |

### SLOW cadence (~1Hz)

| Stage | What it computes | Method |
|---|---|---|
| **BandPowerStage** | Delta/theta/alpha/beta/gamma power | Welch PSD with EMA smoothing |
| **FocusRelaxStage** | Focus (beta/theta) and relaxation (alpha/theta) | Log-ratio with tanh normalization |
| **SignalQualityStage** | Per-channel electrode quality + fit status | PSD ratio (EEG band vs noise) + flat-line detection |

### Head Tracking

The `HeadPoseEstimator` runs outside the pipeline, processing IMU data directly:

1. **Madgwick AHRS** — Fuses accelerometer + gyroscope into orientation quaternion
2. **Axis remap** — Muse frame (X=forward, Y=right, Z=up) to VRM frame (X=right, Y=up, Z=forward)
3. **Velocity-gated yaw decay** — 30%/s drift correction when still, 2%/s when moving
4. **One Euro filter** — Adaptive smoothing: heavy at rest, light during fast motion
5. **Recenter** — Stores current orientation as "looking straight ahead"

## Testing

```bash
# Run all tests (no hardware needed)
uv run pytest -v

# Run specific test module
uv run pytest tests/test_blink.py -v

# Run with coverage
uv run pytest --cov=muse_vtuber -v
```

All tests use BrainFlow's synthetic board or synthetic EEG fixtures — no Muse 2 hardware required.

## Project Structure

```
muse-vtuber/
├── src/muse_vtuber/
│   ├── main.py              # Entry point, main loop orchestration
│   ├── source.py            # BrainFlow hardware abstraction
│   ├── config.py            # CLI args + TOML config loading
│   ├── server.py            # WebSocket + HTTP servers for setup UI
│   ├── head_pose.py         # Madgwick AHRS + One Euro smoothing
│   ├── one_euro.py          # Adaptive quaternion low-pass filter
│   ├── pipeline/
│   │   ├── base.py          # Stage/Pipeline abstract framework
│   │   ├── types.py         # PipelineFrame, Event, Cadence, bands
│   │   ├── speech.py        # Speech detection (temporal EMG)
│   │   ├── blink.py         # Blink detection (frontal MAD)
│   │   ├── clench.py        # Jaw clench detection (bandpass RMS)
│   │   ├── band_power.py    # Frequency band power (Welch PSD)
│   │   ├── focus.py         # Focus/relaxation neurofeedback
│   │   └── signal_quality.py # Electrode fit quality
│   └── outputs/
│       ├── vmc.py           # VMC protocol (UDP/OSC)
│       └── vts.py           # VTube Studio WebSocket plugin
├── frontend/                # Setup/calibration UI (React + Live2D)
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/      # SignalQuality, Live2DAvatar, BiasControls
│   │   └── hooks/           # useMuseStream (WebSocket client)
│   ├── package.json
│   └── vite.config.ts
├── tests/                   # 66+ automated tests
├── scripts/                 # Manual debugging/visualization
├── docs/                    # Research and design specs
└── pyproject.toml
```

## Hardware Notes

### Muse 2 Specifications

| Sensor | Channels | Sample Rate |
|---|---|---|
| EEG | 4 (TP9, AF7, AF8, TP10) | 256 Hz |
| Accelerometer | 3 (x, y, z) in g's | 52 Hz |
| Gyroscope | 3 (x, y, z) in deg/s | 52 Hz |

### Safety

- **Never kill the process while the Muse is connected** — this forces a BLE disconnect that may require power-cycling the headband
- Always use Ctrl+C for graceful shutdown (SIGINT is handled)

### Supported Boards

Any BrainFlow-compatible board can be used by passing its board ID:

```bash
uv run muse-vtuber --board-id MUSE_S_BOARD    # Muse S
uv run muse-vtuber --board-id SYNTHETIC_BOARD  # Synthetic (testing)
uv run muse-vtuber --board-id 0               # Cyton board
```

See [BrainFlow supported boards](https://brainflow.readthedocs.io/en/stable/SupportedBoards.html) for the full list. Note that non-Muse boards may not have IMU data, so head tracking will be unavailable.

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest -v

# Type check frontend
cd frontend && npx tsc --noEmit

# Build frontend for production
cd frontend && pnpm build
```

### Conventions

- **uv** for Python package management
- **pnpm** for frontend package management
- **Conventional commits:** `feat:`, `fix:`, `test:`, `docs:`
- EEG values in microvolts (uV), accelerometer in g's (1.0 = gravity)

## License

MIT
