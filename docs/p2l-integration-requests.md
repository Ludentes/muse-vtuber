# portrait-to-live2d Integration Requests

Requested changes to the `portrait-to-live2d` repo based on architecture
decisions made in muse-vtuber scope (2026-04-05).

## Independence principle

Both projects are independently useful and have no hard dependency on each other:

- **P2L** generates rigs for any use case — VTubing, games, web, animation.
  BCI integration is optional. A user with no Muse headband gets a fully working rig.

- **muse-vtuber** works with any Live2D rig loaded in VTS — existing commissioned
  models, Hiyori, HaiMeng, whatever. BCI params are injected as VTS custom params
  regardless of whether the rig has pre-wired deformers. The rig doesn't need to
  come from P2L.

The sections below describe optional enhancements that make the two work better
together when both are used. None are hard requirements.

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

## 2. External parameter slots — optional enhancement (Category C)

The MLP parameter strategy already defines Category C params:
> "Manually Controlled / BCI — fix at default during generation,
>  injected at runtime by external sources."

**Default behaviour (no change needed):** P2L generates a rig with only MLP-driven
and physics params. Works perfectly for non-BCI use cases.

**Enhancement:** a generation config (e.g. `generation.toml`) could accept an
optional `[external_params]` section listing additional params to bake into the
rig but exclude from MLP training targets:

```toml
[external_params]
# Optional. Baked into the rig as named parameters.
# MLP holds them at default during data generation.
# At runtime, any external driver (muse-vtuber or other) injects live values.
MuseBlink      = { range = [0.0, 1.0], default = 0.0 }
MuseClench     = { range = [0.0, 1.0], default = 0.0 }
MuseFocus      = { range = [0.0, 1.0], default = 0.0 }
MuseRelaxation = { range = [0.0, 1.0], default = 0.0 }
```

**Why bother if muse-vtuber works without it:**
muse-vtuber injects BCI params via VTS custom params API — they appear in VTS
regardless of whether the rig declares them. The enhancement is specifically for
Cubism Editor: if the param names exist in the `.model3.json` at rigging time,
the rigger can wire deformers to them. Without pre-baking, a BCI user would need
to open the rig in Cubism, add the params manually, re-export — extra work.

So: baking is a convenience for rigs that will definitely use BCI. Skipping it
is fine for general-purpose rigs.

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

### P2L standalone (no muse-vtuber)
P2L produces a complete rig. User loads it in VTS with iPhone face tracking.
No BCI, no MLP runtime needed.

| Artifact | Required |
|---|---|
| `character.model3.json` + `.moc3` + `textures/` | ✓ always |
| `model.pt` checkpoint | only if user wants MLP face tracking in muse-vtuber |
| BCI params in model3.json | only if user wants pre-wired BCI deformers |
| `rig_manifest.json` | never required, aids validation |

### muse-vtuber standalone (no P2L)
User has any existing rig. muse-vtuber injects BCI params, VTS handles the rest.
No checkpoint, no P2L output needed.

### Full integration (P2L rig + muse-vtuber)
P2L produces rig + checkpoint. muse-vtuber runs in P2L mode.
The tightest integration: MLP drives all face params, muse-vtuber adds BCI,
pre-wired deformers mean no manual VTS param mapping needed.

| Artifact | Notes |
|---|---|
| `character.model3.json` + `.moc3` + `textures/` | standard rig output |
| `model.pt` (self-describing) | `param_names` must match model3.json params |
| BCI params in model3.json | optional but saves manual Cubism Editor work |
| `rig_manifest.json` | optional, enables muse-vtuber startup validation |
