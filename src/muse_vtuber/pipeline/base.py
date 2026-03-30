from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from muse_vtuber.pipeline.types import Cadence, PipelineFrame

log = logging.getLogger("pipeline")


class Stage(ABC):
    name: str
    cadence: Cadence

    @abstractmethod
    def process(self, frame: PipelineFrame) -> None: ...


class Pipeline:
    def __init__(self, stages: list[Stage]):
        self.stages = stages

    def run(self, cadence: Cadence, frame: PipelineFrame) -> None:
        for stage in self.stages:
            if stage.cadence != cadence:
                continue
            try:
                stage.process(frame)
            except Exception:
                log.exception("Stage %s failed", stage.name)
