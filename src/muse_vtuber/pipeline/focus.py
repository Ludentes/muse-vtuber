from __future__ import annotations

import math
from dataclasses import dataclass

from muse_vtuber.pipeline.band_power import BandPowerResult
from muse_vtuber.pipeline.base import Stage
from muse_vtuber.pipeline.types import Cadence, PipelineFrame


@dataclass
class FocusRelaxResult:
    """Focus and relaxation metrics, per hemisphere and average."""

    focus_left: float     # signed [-1, 1]
    focus_right: float
    focus_avg: float
    relax_left: float     # signed [-1, 1]
    relax_right: float
    relax_avg: float
    focus_avg_unsigned: float   # [0, 1] for animation
    relax_avg_unsigned: float


def _neurofeedback_ratio(numerator: float, denominator: float) -> float:
    """BFiVRC formula: tanh(1.1 * log(num / denom)). Safe for zero denom."""
    if denominator <= 1e-10 or numerator <= 1e-10:
        return 0.0
    return math.tanh(1.1 * math.log(numerator / denominator))


def _signed_to_unsigned(val: float) -> float:
    """Map [-1, 1] → [0, 1]."""
    return max(0.0, min(1.0, (val + 1.0) / 2.0))


class FocusRelaxStage(Stage):
    """Derive focus/relaxation from band power ratios.

    Focus: tanh(1.1 * log(beta / theta))  — matches BrainFlowsIntoVRChat.
    Relax: tanh(1.1 * log(alpha / theta))  — matches BrainFlowsIntoVRChat.
    """

    name = "focus_relax"
    cadence = Cadence.SLOW

    def process(self, frame: PipelineFrame) -> None:
        bp = frame.get(BandPowerResult)
        if bp is None:
            return

        focus_left = _neurofeedback_ratio(
            bp.band_powers_left.get("beta", 0.0),
            bp.band_powers_left.get("theta", 0.0),
        )
        focus_right = _neurofeedback_ratio(
            bp.band_powers_right.get("beta", 0.0),
            bp.band_powers_right.get("theta", 0.0),
        )
        focus_avg = _neurofeedback_ratio(
            bp.band_powers_avg.get("beta", 0.0),
            bp.band_powers_avg.get("theta", 0.0),
        )

        relax_left = _neurofeedback_ratio(
            bp.band_powers_left.get("alpha", 0.0),
            bp.band_powers_left.get("theta", 0.0),
        )
        relax_right = _neurofeedback_ratio(
            bp.band_powers_right.get("alpha", 0.0),
            bp.band_powers_right.get("theta", 0.0),
        )
        relax_avg = _neurofeedback_ratio(
            bp.band_powers_avg.get("alpha", 0.0),
            bp.band_powers_avg.get("theta", 0.0),
        )

        frame.set(FocusRelaxResult(
            focus_left=round(focus_left, 4),
            focus_right=round(focus_right, 4),
            focus_avg=round(focus_avg, 4),
            relax_left=round(relax_left, 4),
            relax_right=round(relax_right, 4),
            relax_avg=round(relax_avg, 4),
            focus_avg_unsigned=round(_signed_to_unsigned(focus_avg), 4),
            relax_avg_unsigned=round(_signed_to_unsigned(relax_avg), 4),
        ))
