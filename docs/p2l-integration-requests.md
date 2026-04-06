# portrait-to-live2d Integration Requests

Requested changes to the `portrait-to-live2d` repo based on architecture
decisions made in muse-vtuber scope (2026-04-05).

---

## 1. Scope clarification: P2L is generation-only

portrait-to-live2d runs **offline**, produces artifacts, then exits.
It never runs at stream time. The runtime is entirely muse-vtuber.

**Artifacts P2L must produce:**
- `character.model3.json` + `.moc3` + textures
- Trained MLP checkpoint: `model.pt` (self-describing dict format — see §3)

**What to remove or reassign:**

The `docs/scenarios/streamer-scenarios.feature` in P2L contains runtime
scenarios that belong in muse-vtuber scope:

| Feature | Current location | Should be |
|---|---|---|
| Feature 1 — Generate model from portrait | P2L ✓ | P2L |
| Feature 2 — Style diversity | P2L ✓ | P2L |
| Feature 3 — Face tracking drives model | P2L | muse-vtuber |
| Feature 4 — BCI signal integration | P2L | muse-vtuber |
| Feature 5 — Add BCI to existing model | P2L | muse-vtuber |
| Feature 6 — Garment variants | P2L ✓ | P2L (generation-time config) |
| Feature 7 — Pipeline performance | P2L ✓ | P2L |

Suggested action: remove Features 3–5 from P2L's feature file, or move them
to `docs/integration/` as reference (not P2L requirements).

---

## 2. External parameter slots (Category C)

The MLP parameter strategy already defines Category C params:
> "Manually Controlled / BCI — fix at default during generation,
>  injected at runtime by external sources."

**Request:** make Category C configurable at generation time, not hardcoded.

A generation config (e.g. `generation.toml`) should accept an `[external_params]`
section that lists params to bake into the generated rig but exclude from MLP
training targets:

```toml
[external_params]
# These are baked into the rig as named parameters.
# The MLP holds them at their default values during data generation.
# At runtime, muse-vtuber injects live values for these.
MuseBlink      = { range = [0.0, 1.0], default = 0.0 }
MuseClench     = { range = [0.0, 1.0], default = 0.0 }
MuseFocus      = { range = [0.0, 1.0], default = 0.0 }
MuseRelaxation = { range = [0.0, 1.0], default = 0.0 }
```

This allows the rig author to decide which external drivers will be used at
stream time without modifying code. The BCI defaults above are the muse-vtuber
standard contract, but any external param source can be added here.

**Why this matters:** if P2L generates a rig without these param names in the
`.model3.json`, muse-vtuber can still inject them (VTS creates custom params
on injection), but the Cubism rigger cannot wire deformers to them without
opening the rig and re-exporting. Baking them in at generation time saves
that manual step.

---

## 3. MLP checkpoint format (already implemented, confirm as standard)

The `humanoid-anime-bs58` checkpoint uses a self-describing dict format:

```python
{
    "state_dict":  ...,         # model weights
    "input_dim":   58,          # 52 blendshapes + 6 pose
    "n_params":    13,          # number of output params
    "param_names": [...],       # list of param IDs in output order
    "epoch":       ...,
    "val_mse":     ...,
}
```

muse-vtuber's `Predictor` auto-detects this format and requires no external
param list. Please treat this as the standard output format for all future
P2L checkpoints. Legacy plain-state_dict format (hiyori_v2) is supported
in muse-vtuber for backward compat but should not be produced by new training
runs.

**Corollary:** the checkpoint `param_names` list should match exactly the param
IDs in the generated `model3.json`. P2L's training pipeline should assert this.

---

## 4. Param manifest artifact (new, optional but recommended)

In addition to the `.pt` checkpoint, P2L could emit a small JSON sidecar:

```json
{
  "mlp_params": ["ParamAngleX", "ParamAngleY", ...],
  "external_params": {
    "MuseBlink":      { "range": [0.0, 1.0], "default": 0.0 },
    "MuseClench":     { "range": [0.0, 1.0], "default": 0.0 },
    "MuseFocus":      { "range": [0.0, 1.0], "default": 0.0 },
    "MuseRelaxation": { "range": [0.0, 1.0], "default": 0.0 }
  },
  "physics_params": ["ParamHairAhoge", "ParamSkirt", ...],
  "checkpoint": "model.pt",
  "input_dim": 58
}
```

This would let muse-vtuber (or any other runtime) load the full rig description
from one place, verify param compatibility, and warn if expected BCI params are
missing from the rig.

Not strictly required (checkpoint is self-describing for MLP params), but useful
for validation and for the Cubism rigger to know what to wire up.

---

## 5. CLAUDE.md scope update

The P2L `CLAUDE.md` should be updated to reflect generation-only scope:

- Remove or move "Shadow Learning" runtime references
- Add a clear statement: "This project produces artifacts (rig + checkpoint).
  The runtime that consumes them is `muse-vtuber`."
- Document the artifact output contract (what files are produced and their formats)
- Add a pointer to muse-vtuber's `docs/p2l-integration-requests.md` for
  the integration contract from the other side

---

## Summary of artifact contract

P2L produces → muse-vtuber consumes:

| Artifact | Format | Required | Notes |
|---|---|---|---|
| `character.model3.json` | Live2D model descriptor | ✓ | Must include external_params by name |
| `character.moc3` | Compiled rig | ✓ | |
| `textures/` | PNG sheets | ✓ | |
| `model.pt` | Self-describing checkpoint dict | ✓ for P2L mode | param_names must match model3.json |
| `rig_manifest.json` | Param manifest sidecar | optional | Enables validation |
