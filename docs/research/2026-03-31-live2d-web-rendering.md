# Live2D Web Rendering: Libraries, Licensing & Feasibility

**Date:** 2026-03-31
**Goal:** Evaluate whether we can render the same .moc3 Live2D model in a browser for our BCI calibration UI, driven programmatically by JavaScript.

## TL;DR

**Yes, this is fully feasible.** Multiple mature libraries can load .moc3 models in a browser and expose parameter-level control. The same model files that VTube Studio uses can be loaded directly. Licensing is free for indie/personal use (under 10M JPY annual revenue). The recommended approach is `@naari3/pixi-live2d-display` (PixiJS v8 + Cubism 5) or the newer `untitled-pixi-live2d-engine`.

---

## 1. Can VTube Studio's .moc3 Models Be Loaded in a Browser?

**Yes.** VTube Studio models consist of standard Live2D Cubism files:

| File | Purpose |
|------|---------|
| `Model.model3.json` | Index file — references all other files |
| `Model.moc3` | Compiled model data (mesh, deformers) |
| `Model.physics3.json` | Physics simulation parameters |
| `textures/*.png` | Model textures |
| `expressions/*.exp3.json` | Expression presets (optional) |
| `motions/*.motion3.json` | Animation clips (optional) |

All web Live2D libraries load from the `.model3.json` entry point, which is the exact same file VTube Studio uses. No conversion or re-export is needed. You copy the model folder, serve it via HTTP, and load it.

**Important:** Models must be Cubism 3+ (.moc3). Legacy Cubism 2 (.moc) models are a different format, but VTube Studio only supports .moc3, so this is not a concern for us.

---

## 2. Available Libraries

### Tier 1: Production-Ready

#### a) `@naari3/pixi-live2d-display` (Recommended for new projects)
- **npm:** `@naari3/pixi-live2d-display`
- **GitHub:** Fork of guansss/pixi-live2d-display
- **PixiJS:** v8
- **Cubism:** 2.1, 3, 4, **5**
- **License:** MIT
- **Status:** Active fork that adds Cubism 5 + PixiJS v8 support

#### b) `pixi-live2d-display` (Original, most documented)
- **npm:** `pixi-live2d-display`
- **GitHub:** https://github.com/guansss/pixi-live2d-display
- **PixiJS:** v6 only
- **Cubism:** 2.1, 3, 4 (no Cubism 5)
- **License:** MIT
- **Status:** Last release v0.5.0-beta (Dec 2023). Well-documented, many examples.
- **Docs:** Complete Guide wiki, CodePen demos, CodeSandbox examples

#### c) `untitled-pixi-live2d-engine`
- **GitHub:** https://github.com/Untitled-Story/untitled-pixi-live2d-engine
- **PixiJS:** v8
- **Cubism:** 2.1, 3, 4, 5
- **License:** MIT
- **Status:** Active, v1.0.1 released Feb 2026. Supports lip-sync and parallel motions.

#### d) Live2D Official `CubismWebFramework` + `CubismWebSamples`
- **GitHub:** https://github.com/Live2D/CubismWebFramework
- **Rendering:** Raw WebGL (no PixiJS dependency)
- **Cubism:** Up to 5.3
- **Language:** TypeScript (96.7% of codebase)
- **License:** Live2D Open Software License (framework) + Proprietary (Core binary)
- **Status:** Active, R5 beta3_1 released Feb 2026

### Tier 2: Newer/Less Proven

#### e) `live2d-loader`
- **GitHub:** https://github.com/AdingApkgg/live2d-loader
- **Packages:** `@live2d-loader/core`, `@live2d-loader/element`, adapter packages
- **Cubism:** 2, 4/5
- **Rendering:** Built-in WebGL2 (zero deps) or PixiJS 8 renderer
- **License:** MIT
- **Status:** Early stage (10 commits), but clean architecture

#### f) `pixi-live2d-display-lipsyncpatch`
- **npm:** `pixi-live2d-display-lipsyncpatch`
- **PixiJS:** v7
- **Cubism:** 2.1, 3, 4
- **Note:** Adds lip-sync audio features to the original pixi-live2d-display

---

## 3. Programmatic Parameter Control

**Yes, you can drive every Live2D parameter from JavaScript.** This is the core capability we need.

### How It Works (pixi-live2d-display family)

```javascript
import { Live2DModel } from 'pixi-live2d-display'; // or @naari3 fork

// Load model
const model = await Live2DModel.from('/models/MyVTuber/MyVTuber.model3.json');
app.stage.addChild(model);

// Access the internal Cubism model and set parameters directly
const coreModel = model.internalModel.coreModel;

// Set eye openness (0 = closed, 1 = open)
coreModel.setParameterValueById('ParamEyeLOpen', 1.0);
coreModel.setParameterValueById('ParamEyeROpen', 1.0);

// Set head rotation (-30 to 30 degrees typically)
coreModel.setParameterValueById('ParamAngleX', 15.0);
coreModel.setParameterValueById('ParamAngleY', -5.0);
coreModel.setParameterValueById('ParamAngleZ', 0.0);

// Set mouth (0 = closed, 1 = open)
coreModel.setParameterValueById('ParamMouthOpenY', 0.5);

// Blink animation
coreModel.setParameterValueById('ParamEyeLOpen', 0.0); // closed
coreModel.setParameterValueById('ParamEyeROpen', 0.0); // closed
```

### How It Works (Official CubismWebFramework)

```typescript
// Lower-level but more control
const paramId = CubismFramework.getIdManager().getId('ParamAngleX');
this._model.setParameterValueById(paramId, 30.0, 1.0);
this._model.update(); // Apply changes
```

### Standard Live2D Parameters (used by VTube Studio models)

| Parameter ID | Range | Description |
|-------------|-------|-------------|
| `ParamAngleX` | -30 to 30 | Head rotation left/right |
| `ParamAngleY` | -30 to 30 | Head rotation up/down |
| `ParamAngleZ` | -30 to 30 | Head tilt |
| `ParamEyeLOpen` | 0 to 1 | Left eye openness |
| `ParamEyeROpen` | 0 to 1 | Right eye openness |
| `ParamEyeBallX` | -1 to 1 | Eye gaze horizontal |
| `ParamEyeBallY` | -1 to 1 | Eye gaze vertical |
| `ParamBrowLY` | -1 to 1 | Left brow up/down |
| `ParamBrowRY` | -1 to 1 | Right brow up/down |
| `ParamMouthOpenY` | 0 to 1 | Mouth open amount |
| `ParamMouthForm` | -1 to 1 | Mouth shape (smile/frown) |
| `ParamBodyAngleX` | -10 to 10 | Body sway left/right |
| `ParamBodyAngleY` | -10 to 10 | Body lean forward/back |
| `ParamBodyAngleZ` | -10 to 10 | Body tilt |
| `ParamBreath` | 0 to 1 | Breathing animation |

**Note:** These are Live2D "standard" parameter IDs. VTube Studio uses its own parameter names (e.g., `EyeOpenLeft` instead of `ParamEyeLOpen`) in its API, but the underlying Live2D model uses the `Param*` names. When controlling the model directly in the browser, use the `Param*` names.

### Parameter Mapping: VTS API vs Live2D Internal

| VTS Parameter | Live2D Parameter | Range |
|--------------|-----------------|-------|
| `EyeOpenLeft` | `ParamEyeLOpen` | 0-1 |
| `EyeOpenRight` | `ParamEyeROpen` | 0-1 |
| `MouthOpen` | `ParamMouthOpenY` | 0-1 |
| `MouthSmile` | `ParamMouthForm` | -1 to 1 |
| `FaceAngleX` | `ParamAngleX` | -30 to 30 |
| `FaceAngleY` | `ParamAngleY` | -30 to 30 |
| `FaceAngleZ` | `ParamAngleZ` | -30 to 30 |

---

## 4. Licensing

### Live2D Cubism SDK — Free for Indie/Personal Use

The licensing has **two components**:

#### a) Cubism Core (proprietary binary: `live2dcubismcore.min.js`)
- **Required** by ALL libraries (pixi-live2d-display, official SDK, etc.)
- Downloaded from Live2D's SDK package
- Redistributable under the SDK Release License

#### b) SDK Release License (Publication License)
- **Free tier:** Individuals and entities with annual revenue **under 10 million JPY** (~$67,000 USD) are **exempt** from licensing fees
- **Paid tier:** Entities with revenue >= 10M JPY must sign a Publication License Agreement
- **No per-unit fees** for the free tier
- **Web apps are covered** — no platform restrictions

#### Summary for Our Use Case

| Criteria | Status |
|----------|--------|
| Personal/indie use | FREE |
| Annual revenue < 10M JPY | FREE |
| Web browser deployment | Allowed |
| Bundling Core JS in web app | Allowed |
| Using same model as VTS | Allowed (model licensing is separate from SDK licensing) |

**The SDK license covers the rendering engine. Model licensing is between you and the model creator.** If you created or purchased the model, you can use it in both VTS and your web UI.

---

## 5. Open-Source Alternatives

### Inochi2D / Nijigenerate
- **What:** Open-source 2D puppet animation framework
- **Format:** `.inp` files (not compatible with Live2D .moc3)
- **Web support:** No browser renderer exists. Desktop only (D/OpenGL).
- **Verdict:** Not viable for our use case. Different format, no web runtime.

### Other Alternatives (Synfig, enve, etc.)
- These are animation *editors*, not runtime renderers
- None can load .moc3 files
- None have web/browser renderers
- **Verdict:** Not relevant

### Practical Reality
There is no open-source alternative that can render .moc3 files. The Cubism Core is proprietary and required. However, the wrapper libraries (pixi-live2d-display etc.) are MIT-licensed, and the SDK is free for indie use, so this is not a practical blocker.

---

## 6. Can We Load the SAME Model File as VTube Studio?

**Yes, absolutely.** The workflow:

1. User has a Live2D model folder (e.g., `MyVTuber/`)
2. This folder is loaded into VTube Studio's `Live2DModels/` directory
3. We serve the **same folder** via our web UI's static files or a local HTTP server
4. Browser loads `MyVTuber/MyVTuber.model3.json` -> renders identical model
5. We drive parameters from BCI data via JavaScript
6. VTube Studio simultaneously drives the same model from our bridge via its WebSocket API

**Both renderings use the same .moc3, textures, and physics.** The avatar will look identical.

---

## 7. Recommended Architecture for Calibration UI

```
Browser (Calibration UI)
├── PixiJS v8 + @naari3/pixi-live2d-display
│   └── Loads .model3.json from local server
│   └── Sets Param* values directly on coreModel
│
├── WebSocket to Python backend
│   └── Receives BCI data (blink events, band power, head pose)
│   └── Receives detector states
│
└── UI shows:
    ├── Live2D avatar preview (same model as VTS)
    ├── Blink threshold slider (see effect in real-time)
    ├── Parameter mapping controls
    └── Signal quality indicators
```

### Why This Works
- User loads their VTS model into our calibration UI
- They see real-time preview of how BCI data maps to avatar parameters
- They adjust thresholds/mappings while seeing the avatar respond
- When satisfied, the same mappings are sent to VTS via our bridge
- The avatar in VTS behaves identically

---

## 8. Dependencies & Bundle Size

For a minimal setup:

```
@naari3/pixi-live2d-display  — MIT, ~50KB
pixi.js v8                    — MIT, ~200KB minified
live2dcubismcore.min.js       — Proprietary, ~300KB (loaded separately)
```

Total: ~550KB for the rendering stack. Reasonable for a local calibration tool.

---

## 9. Risks & Gotchas

1. **Cubism Core version mismatch:** The Core JS version must match what the model was exported for. Cubism 5 Core handles Cubism 3/4 models, so use the latest.

2. **Physics simulation differences:** Our browser rendering runs its own physics sim. Results may differ slightly from VTube Studio's physics. For calibration preview this is acceptable.

3. **Texture memory:** Large models with many textures can use significant GPU memory. Not an issue for a single model.

4. **CORS:** If serving model files from a different origin, you need proper CORS headers. Easiest to serve from the same origin as the web UI.

5. **moc3 version cap:** CubismWebFramework currently supports up to moc3 version 4. Version 5 moc3 files (from newest Cubism Editor) will error. Most existing VTuber models are version 3-4.

6. **PixiJS v6 vs v8:** The original `pixi-live2d-display` requires PixiJS v6. The `@naari3` fork and `untitled-pixi-live2d-engine` support v8. Use v8 for new projects.

---

## Sources

- [pixi-live2d-display (GitHub)](https://github.com/guansss/pixi-live2d-display)
- [pixi-live2d-display Complete Guide](https://github.com/guansss/pixi-live2d-display/wiki/Complete-Guide)
- [@naari3/pixi-live2d-display (npm)](https://www.npmjs.com/package/@naari3/pixi-live2d-display)
- [untitled-pixi-live2d-engine (GitHub)](https://github.com/Untitled-Story/untitled-pixi-live2d-engine)
- [live2d-loader (GitHub)](https://github.com/AdingApkgg/live2d-loader)
- [Live2D CubismWebFramework (GitHub)](https://github.com/Live2D/CubismWebFramework)
- [Live2D CubismWebSamples (GitHub)](https://github.com/Live2D/CubismWebSamples)
- [Live2D SDK License](https://www.live2d.com/en/sdk/license/)
- [Live2D SDK About](https://www.live2d.com/en/sdk/about/)
- [Live2D Standard Parameter List](https://docs.live2d.com/en/cubism-editor-manual/standard-parameter-list/)
- [Live2D Parameter Operation (SDK Manual)](https://docs.live2d.com/en/cubism-sdk-manual/parameters/)
- [Live2D SDK for Web in Vite](https://docs.live2d.com/en/cubism-sdk-tutorials/use-sdk-in-js/)
- [VTube Studio: Loading Models](https://github.com/DenchiSoft/VTubeStudio/wiki/Loading-your-own-Models)
- [Understanding Live2D Model Data Files (Medium)](https://medium.com/@vesper_illust/understanding-live2d-model-data-files-for-vtube-studio-0ada080a35b2)
