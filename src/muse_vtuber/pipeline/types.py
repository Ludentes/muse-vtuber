from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

import numpy as np

T = TypeVar("T")

BANDS: dict[str, tuple[float, float]] = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (7.5, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 44.0),
}

CH_NAMES: list[str] = ["TP9", "AF7", "AF8", "TP10"]

BAND_NAMES: list[str] = list(BANDS.keys())

# Hemisphere groupings for Muse 4-channel layout
LEFT_CHS: list[int] = [0, 1]   # TP9, AF7
RIGHT_CHS: list[int] = [2, 3]  # AF8, TP10
FRONTAL_CHS: list[int] = [1, 2]  # AF7, AF8
TEMPORAL_CHS: list[int] = [0, 3]  # TP9, TP10


class Cadence(Enum):
    FAST = "fast"   # every chunk (~16ms)
    SLOW = "slow"   # every ~1s window


@dataclass
class Event:
    kind: str
    timestamp: float
    confidence: float = 1.0
    channel: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineFrame:
    eeg: np.ndarray | None       # (n_channels, n_samples)
    imu: np.ndarray | None       # (6, n_samples) — accel[0:3] + gyro[3:6]
    timestamp: float
    _results: dict[str, Any] = field(default_factory=dict, repr=False)
    events: list[Event] = field(default_factory=list)

    def set(self, result: Any) -> None:
        """Store a result by its class name."""
        self._results[type(result).__name__] = result

    def get(self, cls: type[T]) -> T | None:
        """Retrieve a typed result, or None if not set."""
        return self._results.get(cls.__name__)

    def has(self, cls: type) -> bool:
        return cls.__name__ in self._results
