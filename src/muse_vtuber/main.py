from __future__ import annotations

import asyncio
import logging
import queue
import signal
import threading
import time

from muse_vtuber.config import AppConfig, parse_cli_args
from muse_vtuber.head_pose import HeadPoseEstimator
from muse_vtuber.outputs.vmc import VMCBlendshapes, VMCOutput, split_head_neck
from muse_vtuber.pipeline.band_power import BandPowerStage
from muse_vtuber.pipeline.base import Pipeline
from muse_vtuber.pipeline.blink import BlinkDetector
from muse_vtuber.pipeline.clench import ClenchDetector, ClenchResult
from muse_vtuber.pipeline.focus import FocusRelaxResult, FocusRelaxStage
from muse_vtuber.pipeline.signal_quality import SignalQualityResult, SignalQualityStage
from muse_vtuber.pipeline.speech import SpeechDetector
from muse_vtuber.pipeline.types import Cadence, PipelineFrame
from muse_vtuber.server import SetupUIServer
from muse_vtuber.source import BrainFlowSource

log = logging.getLogger("muse_vtuber")


def create_pipeline(config: AppConfig) -> Pipeline:
    """Create the processing pipeline with all stages."""
    blink = BlinkDetector()
    blink.guard_speech = False
    stages = [
        SpeechDetector(),
        blink,
        ClenchDetector(),
        BandPowerStage(ema_decay=config.ema_decay),
        FocusRelaxStage(),
        SignalQualityStage(),
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

    # Head tracking
    head_pose = HeadPoseEstimator(
        beta=config.madgwick_beta,
        one_euro_min_cutoff=config.smoothing_min_cutoff,
        one_euro_beta=config.smoothing_beta,
    ) if config.head_tracking_enabled else None

    # Setup UI server
    ui_server: SetupUIServer | None = None
    if config.ui_enabled:
        ui_server = SetupUIServer(port=config.ui_port)
        ui_thread = threading.Thread(target=ui_server.run, daemon=True)
        ui_thread.start()
        log.info("Setup UI server on ws://localhost:%d", config.ui_port)

    # Output sinks
    vmc_output = VMCOutput(config.vmc_host, config.vmc_port) if config.vmc_enabled else None

    # VTube Studio (async, runs in thread)
    vts_queue: queue.Queue | None = None
    if config.vts_enabled:
        from muse_vtuber.outputs.vts import VTSClient
        vts_client = VTSClient(port=config.vts_port)
        vts_queue = queue.Queue(maxsize=1)

        def _vts_thread() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _run() -> None:
                connected = await vts_client.connect()
                if not connected:
                    log.warning("VTube Studio not available")
                    return
                while running:
                    try:
                        # Use run_in_executor so the blocking get doesn't
                        # freeze the event loop (drain task needs to run)
                        data = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: vts_queue.get(timeout=0.1)
                        )
                        await vts_client.inject(**data)
                    except queue.Empty:
                        pass

            loop.run_until_complete(_run())

        vts_thread = threading.Thread(target=_vts_thread, daemon=True)
        vts_thread.start()

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

            # Head tracking from IMU
            bones = None
            if head_pose and imu is not None and imu.shape[1] > 0:
                for sample_idx in range(imu.shape[1]):
                    accel = imu[:3, sample_idx]
                    gyro = imu[3:, sample_idx]
                    head_pose.update(accel, gyro)
                q = head_pose.get_quaternion()
                neck, head = split_head_neck(q)
                bones = [neck, head]

            # Extract and send blendshapes
            blendshapes = extract_blendshapes(frame)

            if vmc_output:
                vmc_output.send_frame(blendshapes=blendshapes, bones=bones)

            if vts_queue is not None:
                vts_data = {
                    "blink": blendshapes.blink,
                    "focus": blendshapes.focus,
                    "relaxation": blendshapes.relaxation,
                    "clench": blendshapes.clench,
                }
                if head_pose and head_pose.initialized:
                    pitch, yaw, roll = head_pose.get_euler_degrees()
                    vts_data["face_angle_x"] = pitch
                    vts_data["face_angle_y"] = yaw
                    vts_data["face_angle_z"] = roll
                try:
                    vts_queue.put_nowait(vts_data)
                except queue.Full:
                    log.debug("VTS queue full, dropping frame")

            # Setup UI: broadcast metrics + events, handle commands
            if ui_server:
                # Broadcast events
                for event in frame.events:
                    ui_server.broadcast_event({
                        "kind": event.kind,
                        "confidence": event.confidence,
                    })

                # Broadcast metrics (~30Hz, throttled by poll_interval)
                sq = frame.get(SignalQualityResult)
                hp_pitch, hp_yaw, hp_roll = (
                    head_pose.get_euler_degrees() if head_pose and head_pose.initialized
                    else (0.0, 0.0, 0.0)
                )
                ui_server.broadcast_metrics({
                    "signal_quality": sq.channel_quality if sq else {},
                    "fit_status": sq.fit_status if sq else "unknown",
                    "head_pose": {"pitch": hp_pitch, "yaw": hp_yaw, "roll": hp_roll},
                    "settle_progress": head_pose.settle_progress if head_pose else 0,
                    "initialized": head_pose.initialized if head_pose else False,
                })

                # Handle commands
                cmd = ui_server.poll_command()
                if cmd:
                    if cmd.get("type") == "recenter" and head_pose:
                        head_pose.recenter()
                        log.info("Recentered head pose (UI command)")
                    elif cmd.get("type") == "set_bias" and head_pose:
                        head_pose.bias_pitch = cmd.get("pitch", 0.0)
                        head_pose.bias_yaw = cmd.get("yaw", 0.0)
                        head_pose.bias_roll = cmd.get("roll", 0.0)
                        log.info("Set bias: pitch=%.1f yaw=%.1f roll=%.1f",
                                 head_pose.bias_pitch, head_pose.bias_yaw, head_pose.bias_roll)

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
