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
