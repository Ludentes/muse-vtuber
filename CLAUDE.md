# Muse VTuber Bridge — Project Instructions

## Stack

- **Runtime**: Python 3.11+, uv (package manager)
- **Hardware**: BrainFlow (BCI abstraction, supports ~40 boards)
- **Signal Processing**: numpy, scipy, BrainFlow DataFilter
- **Output Protocols**: python-osc (VMC + VRChat OSC), websockets (VTube Studio)
- **Testing**: pytest, pytest-asyncio

## Running

```bash
# Install
uv sync --extra dev

# Run with synthetic board (no hardware)
uv run muse-vtuber --synthetic --debug

# Run with real Muse 2
uv run muse-vtuber --mac XX:XX:XX:XX:XX:XX --debug

# Run with fusion (requires OpenSeeFace running separately)
uv run muse-vtuber --mac XX:XX:XX:XX:XX:XX --fusion --debug

# Tests
uv run pytest -v
```

## Key Conventions

- Uses **uv** (not pip, not poetry)
- Uses **conventional commits**: `feat:`, `fix:`, `test:`, `docs:`
- Commit and push after each logical unit of work
- TDD: write failing test → implement → verify pass
- Pipeline stages live in `src/muse_vtuber/pipeline/`
- Output sinks live in `src/muse_vtuber/outputs/`
- All EEG values are in µV
- BrainFlow accelerometer values are in g's (GRAVITY=1.0, not 9.81)

## Testing

- Automated tests use BrainFlow synthetic board (`board_id=-1`) — no hardware needed
- Blink/clench tests use synthetic EEG signals in fixtures, not BrainFlow
- See Plan 0 in `../zyphraexps/docs/superpowers/plans/2026-03-30-muse-vtuber-bridge/00-repo-setup.md` for full testing infrastructure guide

## BrainFlow Gotchas

- `BoardShim.set_log_level(3)` and `DataFilter.set_log_level(3)` to suppress spam
- `remove_environmental_noise` needs `NoiseTypes.FIFTY.value` (int 0), not raw 50
- PSD `nfft` must be power of 2 AND ≤ data length
- Synthetic board (`-1`) has EEG but no IMU preset
- Muse 2 IMU is AUXILIARY_PRESET, not DEFAULT_PRESET

## Operating Modes

muse-vtuber works with any Live2D model in two modes:

### Standard mode (existing / commissioned rig)
VTube Studio handles face tracking natively (iPhone TrueDepth recommended).
muse-vtuber adds BCI params only — no `--face-tracking` flag.

```
Muse 2 → muse-vtuber ──── MuseBlink/MuseClench/MuseFocus/MuseRelaxation ──→ VTS
iPhone  → VTS native  ──── AngleX/Y/Z, EyeLOpen, MouthOpenY, … ──────────→ VTS
```

### P2L mode (portrait-to-live2d generated rig)
VTS still renders the model, but VTS face tracking can only drive ~15 standard
params. The generated rig has 74–107 params; the CartoonAlive MLP drives all
face-derived ones. muse-vtuber runs both in parallel.

```
Webcam → FaceLandmarker → MLP ─── all N face params ──────────────────────→ VTS
Muse 2 → muse-vtuber ──────────── MuseBlink/MuseClench/MuseFocus/… ───────→ VTS
```

Activate with: `--face-tracking --face-checkpoint path/to/model.pt`

The checkpoint is produced by portrait-to-live2d (offline, run once).
The MLP is self-describing: param names and input_dim are embedded in the .pt file.

## BCI Parameter Contract

These are the VTS custom parameters muse-vtuber creates and drives:

| Parameter | Range | Source | Notes |
|---|---|---|---|
| MuseBlink | 0–1 | EEG (blink detection) | 1.0 on blink event |
| MuseClench | 0–1 | EEG (jaw EMG) | 1.0 on jaw clench |
| MuseFocus | 0–1 | EEG theta/beta ratio | Smooth, ~1s lag |
| MuseRelaxation | 0–1 | EEG alpha power | Smooth, ~1s lag |

For P2L-generated rigs: these param names must be baked into the rig and wired
to deformers in Cubism Editor. For standard rigs: they appear in VTS custom params
panel and can be mapped manually in Model Settings.

## Architecture

```
BrainFlowSource (poll thread)
    → PipelineFrame (eeg + imu + timestamp)
    → Pipeline stages:
        SpeechDetector → BlinkDetector → ClenchDetector (FAST cadence)
        BandPowerStage → FocusRelaxStage (SLOW cadence)
    → HeadPoseEstimator (IMU → quaternion)
    → ComplementaryFusion (optional, IMU + OpenSeeFace webcam)
    → Output sinks: VMC (UDP), VRChat OSC (UDP), VTube Studio (WebSocket)

Optional face tracking thread (P2L mode):
    Webcam → FaceLandmarker → CartoonAlive MLP → VTS InjectParameterData
    src/muse_vtuber/outputs/face_tracking.py  (FaceLandmarker → 58-d features)
    src/muse_vtuber/outputs/face_params.py    (MLP → VTS, calibration + smoothing)
    src/muse_vtuber/mlp/                      (model.py + infer.py, no P2L dep)
```

## Ported From zyphraexps

Several components are ported from the parent project (`../zyphraexps/`):
- `pipeline/base.py`, `pipeline/types.py` — Stage/Pipeline framework
- `pipeline/blink.py` — BlinkDetector (from `backend/pipeline/stages/detectors.py`)
- `pipeline/clench.py` — ClenchDetector (same source)
- `pipeline/speech.py` — SpeechDetector (same source)
- `pipeline/band_power.py` — adapted from BandPowerExtractor
- `head_pose.py` — ported from TypeScript (`frontend/src/lib/headPose.ts`)
- `one_euro.py` — ported from TypeScript (`frontend/src/lib/oneEuroFilter.ts`)
- `source.py` — adapted from `backend/acquisition.py`
