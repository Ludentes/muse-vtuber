from __future__ import annotations

import logging
import signal
import time

from muse_vtuber.config import AppConfig, parse_cli_args
from muse_vtuber.outputs.vmc import VMCBlendshapes, VMCOutput
from muse_vtuber.pipeline.band_power import BandPowerStage
from muse_vtuber.pipeline.base import Pipeline
from muse_vtuber.pipeline.blink import BlinkDetector
from muse_vtuber.pipeline.clench import ClenchDetector, ClenchResult
from muse_vtuber.pipeline.focus import FocusRelaxResult, FocusRelaxStage
from muse_vtuber.pipeline.speech import SpeechDetector
from muse_vtuber.pipeline.types import Cadence, PipelineFrame
from muse_vtuber.source import BrainFlowSource

log = logging.getLogger("muse_vtuber")


def create_pipeline(config: AppConfig) -> Pipeline:
    """Create the processing pipeline with all stages."""
    stages = [
        SpeechDetector(),
        BlinkDetector(),
        ClenchDetector(),
        BandPowerStage(ema_decay=config.ema_decay),
        FocusRelaxStage(),
    ]
    return Pipeline(stages=stages)


def extract_blendshapes(frame: PipelineFrame) -> VMCBlendshapes:
    """Extract blendshape values from pipeline frame results."""
    blink_val = 0.0
    for event in frame.events:
        if event.kind == "blink":
            blink_val = 1.0
            break

    clench_result = frame.get(ClenchResult)
    clench_val = 1.0 if (clench_result and clench_result.jaw_clench) else 0.0

    focus_result = frame.get(FocusRelaxResult)
    focus_val = focus_result.focus_avg_unsigned if focus_result else 0.0
    relax_val = focus_result.relax_avg_unsigned if focus_result else 0.0

    return VMCBlendshapes(
        blink=blink_val,
        clench=clench_val,
        focus=focus_val,
        relaxation=relax_val,
    )


def run(config: AppConfig) -> None:
    """Main run loop. Blocking."""
    log.info("Starting Muse VTuber Bridge (board=%s)", config.board_id)

    source = BrainFlowSource(
        board_id=config.board_id,
        mac_address=config.mac_address,
        serial_port=config.serial_port,
    )
    pipeline = create_pipeline(config)

    # Output sinks
    vmc_output = VMCOutput(config.vmc_host, config.vmc_port) if config.vmc_enabled else None

    # Graceful shutdown
    running = True

    def on_signal(sig, _frame):
        nonlocal running
        log.info("Shutting down...")
        running = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    source.start()
    log.info("Connected. Streaming EEG → VMC on %s:%d", config.vmc_host, config.vmc_port)

    poll_interval = 1.0 / 60  # 60Hz poll rate
    slow_cadence_interval = 1.0
    last_slow = time.monotonic()

    try:
        while running:
            eeg = source.poll_eeg()
            imu = source.poll_imu()

            if eeg is None and imu is None:
                time.sleep(poll_interval)
                continue

            now = time.monotonic()
            frame = PipelineFrame(eeg=eeg, imu=imu, timestamp=now)

            # Run FAST stages every poll
            pipeline.run(Cadence.FAST, frame)

            # Run SLOW stages periodically
            if now - last_slow >= slow_cadence_interval:
                pipeline.run(Cadence.SLOW, frame)
                last_slow = now

            # Extract and send blendshapes
            blendshapes = extract_blendshapes(frame)

            if vmc_output:
                vmc_output.send_blendshapes(blendshapes)

            if config.debug and frame.events:
                for event in frame.events:
                    log.info("Event: %s (confidence=%.2f)", event.kind, event.confidence)

            time.sleep(poll_interval)

    finally:
        source.stop()
        log.info("Stopped.")


def cli() -> None:
    """CLI entry point."""
    config = parse_cli_args()
    level = logging.DEBUG if config.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)-15s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    run(config)


if __name__ == "__main__":
    cli()
