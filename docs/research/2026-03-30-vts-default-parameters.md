# VTube Studio Default Tracking Parameters & Injection API

**Date:** 2026-03-30  
**Source:** https://github.com/DenchiSoft/VTubeStudio (API README) + wiki/VTS-Model-Settings

## Key Finding: You CAN Inject Into Default Parameters

The `InjectParameterDataRequest` works with **both default and custom parameters**. From the docs:

> "You can feed in data for any default or custom parameter."

This means injecting values into `EyeOpenLeft`, `MouthOpen`, `MouthSmile` etc. will immediately affect the model without any manual parameter binding, since models are already mapped to these default inputs.

## Parameters We Need

| Parameter | Range | Notes |
|-----------|-------|-------|
| `EyeOpenLeft` | 0-1 | 1 = fully open, 0 = closed (blink) |
| `EyeOpenRight` | 0-1 | 1 = fully open, 0 = closed (blink) |
| `MouthOpen` | 0-1 | How open the mouth is |
| `MouthSmile` | 0-1 | How much smiling |

## Complete Default Parameter List

### Face Position & Angle
- `FacePositionX` — horizontal position
- `FacePositionY` — vertical position
- `FacePositionZ` — distance from camera
- `FaceAngleX` — right/left rotation
- `FaceAngleY` — up/down rotation
- `FaceAngleZ` — lean rotation

### Eyes
- `EyeOpenLeft` — left eye openness
- `EyeOpenRight` — right eye openness
- `EyeLeftX` — left eye gaze horizontal
- `EyeLeftY` — left eye gaze vertical
- `EyeRightX` — right eye gaze horizontal
- `EyeRightY` — right eye gaze vertical

### Mouth & Expression
- `MouthOpen` — mouth openness
- `MouthSmile` — smile amount
- `MouthX` — mouth left/right shift
- `TongueOut` — tongue out (iOS only)
- `CheekPuff` — cheek puff (iOS only)
- `FaceAngry` — angry expression (EXPERIMENTAL)

### Brows
- `Brows` — both brows up/down combined
- `BrowLeftY` — left brow up/down
- `BrowRightY` — right brow up/down

### Voice (microphone-based)
- `VoiceVolume`
- `VoiceFrequency`
- `VoiceA`, `VoiceI`, `VoiceU`, `VoiceE`, `VoiceO`, `VoiceSilence`
- `VoiceVolumePlusMouthOpen` — combined
- `VoiceFrequencyPlusMouthSmile` — combined

### Mouse
- `MousePositionX`
- `MousePositionY`

## InjectParameterDataRequest API

### Request Format

```json
{
  "apiName": "VTubeStudioPublicAPI",
  "apiVersion": "1.0",
  "requestID": "SomeID",
  "messageType": "InjectParameterDataRequest",
  "data": {
    "faceFound": false,
    "mode": "set",
    "parameterValues": [
      {
        "id": "EyeOpenLeft",
        "value": 1.0
      },
      {
        "id": "EyeOpenRight",
        "value": 1.0
      },
      {
        "id": "MouthOpen",
        "weight": 0.8,
        "value": 0.5
      }
    ]
  }
}
```

### Mode Field

Two modes available:

- **`"set"` (default)** — Overrides the parameter value. Only ONE plugin can "set" a given parameter at a time. If another plugin is already controlling it, you get an error.
- **`"add"`** — Adds the injected value to the current parameter value. Multiple plugins can use "add" mode simultaneously on the same parameter. The `"weight"` field is NOT used in add mode. Useful for bonk/throwing effects.

### Weight Field

- Optional float between 0 and 1 (default: 1)
- Only applies in `"set"` mode
- Mixes your value with face tracking: `weight=0.5` means 50% face tracking + 50% API value
- Use case: fade in/out control so the parameter doesn't "jump" when API takes over

### faceFound Field

- Optional boolean
- When set to `true`, tells VTS to consider the user's face as found
- Controls when the "tracking lost" animation plays
- Important for our use case: set to `true` so the model stays active

### Timeout Behavior

- You must re-send data for a parameter **at least once per second**
- If you stop sending, the parameter is considered "lost" and reverts to face tracking or default value
- This means we need a continuous send loop at ~10-30 FPS

## Implications for Muse VTuber Bridge

1. **No custom parameter creation needed** for basic control — just inject directly into `EyeOpenLeft`, `EyeOpenRight`, `MouthOpen`, `MouthSmile`
2. **Set `faceFound: true`** so the model doesn't play tracking-lost animations
3. **Use `mode: "set"`** since we're the sole controller
4. **Send at minimum 1 Hz**, ideally 10-30 Hz for smooth animation
5. **Weight** can be useful for smooth transitions — start at `weight=0` and ramp up to `weight=1` when first connecting
6. For blink: set `EyeOpenLeft`/`EyeOpenRight` to `0.0` during blink, `1.0` when open
7. Custom parameters (e.g., for EEG-specific features like `BrainAlpha`) would need `ParameterCreationRequest` first
