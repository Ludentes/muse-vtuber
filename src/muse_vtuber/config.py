from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class AppConfig:
    # Device
    board_id: str = "MUSE_2_BOARD"
    mac_address: str = ""
    serial_port: str = ""

    # Processing
    ema_decay: float = 0.04
    window_seconds: float = 1.0

    # VMC output
    vmc_enabled: bool = True
    vmc_host: str = "127.0.0.1"
    vmc_port: int = 39539

    # VRChat OSC output
    osc_enabled: bool = False
    osc_host: str = "127.0.0.1"
    osc_port: int = 9000

    # VTube Studio
    vts_enabled: bool = False
    vts_port: int = 8001

    # Head tracking
    head_tracking_enabled: bool = True
    madgwick_beta: float = 0.8
    smoothing_min_cutoff: float = 0.3
    smoothing_beta: float = 1.5

    # Fusion
    fusion_enabled: bool = False
    openseeface_port: int = 11573
    fusion_alpha: float = 0.96

    # Setup UI
    ui_enabled: bool = True
    ui_port: int = 8765
    model_path: str = ""

    # Face tracking (portrait-to-live2d MLP → VTS)
    face_tracking_enabled: bool = False
    face_tracking_checkpoint: str = ""   # path to .pt checkpoint
    face_tracking_model3: str = ""       # path to .model3.json (for param IDs)
    face_tracking_camera: int = 0

    # OBS ambient effects (EEG → Color Correction filter)
    obs_enabled: bool = False
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    obs_source: str = "EEG_Overlay"
    obs_filter: str = "EEG_Ambient"
    eeg_ws_url: str = "ws://localhost:8765"

    # Debug
    debug: bool = False


def load_config_from_dict(data: dict) -> AppConfig:
    """Load config from parsed TOML dict."""
    cfg = AppConfig()

    device = data.get("device", {})
    cfg.board_id = device.get("board_id", cfg.board_id)
    cfg.mac_address = device.get("mac_address", cfg.mac_address)
    cfg.serial_port = device.get("serial_port", cfg.serial_port)

    processing = data.get("processing", {})
    cfg.ema_decay = processing.get("ema_decay", cfg.ema_decay)
    cfg.window_seconds = processing.get("window_seconds", cfg.window_seconds)

    outputs = data.get("outputs", {})
    vmc = outputs.get("vmc", {})
    cfg.vmc_enabled = vmc.get("enabled", cfg.vmc_enabled)
    cfg.vmc_host = vmc.get("host", cfg.vmc_host)
    cfg.vmc_port = vmc.get("port", cfg.vmc_port)

    osc = outputs.get("osc", {})
    cfg.osc_enabled = osc.get("enabled", cfg.osc_enabled)
    cfg.osc_host = osc.get("host", cfg.osc_host)
    cfg.osc_port = osc.get("port", cfg.osc_port)

    vts = outputs.get("vts", {})
    cfg.vts_enabled = vts.get("enabled", cfg.vts_enabled)
    cfg.vts_port = vts.get("port", cfg.vts_port)

    head = data.get("head_tracking", {})
    cfg.head_tracking_enabled = head.get("enabled", cfg.head_tracking_enabled)
    cfg.madgwick_beta = head.get("madgwick_beta", cfg.madgwick_beta)
    cfg.smoothing_min_cutoff = head.get("smoothing_min_cutoff", cfg.smoothing_min_cutoff)
    cfg.smoothing_beta = head.get("smoothing_beta", cfg.smoothing_beta)

    fusion = data.get("fusion", {})
    cfg.fusion_enabled = fusion.get("enabled", cfg.fusion_enabled)
    cfg.openseeface_port = fusion.get("openseeface_port", cfg.openseeface_port)
    cfg.fusion_alpha = fusion.get("alpha", cfg.fusion_alpha)

    return cfg


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from TOML file, falling back to defaults."""
    if config_path and config_path.exists():
        if tomllib is None:
            raise ImportError("tomli required for Python < 3.11: pip install tomli")
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        return load_config_from_dict(data)

    # Try default location
    default = Path.home() / ".config" / "muse-vtuber" / "config.toml"
    if default.exists() and tomllib:
        with open(default, "rb") as f:
            data = tomllib.load(f)
        return load_config_from_dict(data)

    return AppConfig()


def parse_cli_args(args: list[str] | None = None) -> AppConfig:
    """Parse CLI arguments, layered on top of config file."""
    parser = argparse.ArgumentParser(description="Muse VTuber Bridge")
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    parser.add_argument("--board-id", type=str, help="BrainFlow board ID or name")
    parser.add_argument("--mac", type=str, help="Device MAC address")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic board")
    parser.add_argument("--vmc-port", type=int, help="VMC output port")
    parser.add_argument("--osc", action="store_true", help="Enable VRChat OSC output")
    parser.add_argument("--osc-port", type=int, help="VRChat OSC port")
    parser.add_argument("--vts", action="store_true", help="Enable VTube Studio plugin")
    parser.add_argument("--vts-port", type=int, help="VTube Studio port")
    parser.add_argument("--no-ui", action="store_true", help="Disable setup UI server")
    parser.add_argument("--ui-port", type=int, help="Setup UI WebSocket port")
    parser.add_argument("--model", type=str, help="Path to Live2D model folder")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    parser.add_argument("--face-tracking", action="store_true", help="Enable face tracking → VTS")
    parser.add_argument("--face-checkpoint", type=str, help="Path to MLP .pt checkpoint")
    parser.add_argument("--face-model3", type=str, help="Path to .model3.json for param IDs")
    parser.add_argument("--face-camera", type=int, default=None, help="Webcam index (default 0)")
    parser.add_argument("--obs", action="store_true", help="Enable EEG → OBS ambient effects")
    parser.add_argument("--obs-port", type=int, help="OBS WebSocket port (default 4455)")
    parsed = parser.parse_args(args)

    cfg = load_config(parsed.config)

    if parsed.synthetic:
        cfg.board_id = "SYNTHETIC_BOARD"
    if parsed.board_id:
        cfg.board_id = parsed.board_id
    if parsed.mac:
        cfg.mac_address = parsed.mac
    if parsed.vmc_port:
        cfg.vmc_port = parsed.vmc_port
    if parsed.osc:
        cfg.osc_enabled = True
    if parsed.osc_port:
        cfg.osc_port = parsed.osc_port
    if parsed.vts:
        cfg.vts_enabled = True
    if parsed.vts_port:
        cfg.vts_port = parsed.vts_port
    if parsed.no_ui:
        cfg.ui_enabled = False
    if parsed.ui_port:
        cfg.ui_port = parsed.ui_port
    if parsed.model:
        cfg.model_path = parsed.model
    if parsed.debug:
        cfg.debug = True
    if parsed.face_tracking:
        cfg.face_tracking_enabled = True
    if parsed.face_checkpoint:
        cfg.face_tracking_checkpoint = parsed.face_checkpoint
    if parsed.face_model3:
        cfg.face_tracking_model3 = parsed.face_model3
    if parsed.face_camera is not None:
        cfg.face_tracking_camera = parsed.face_camera
    if parsed.obs:
        cfg.obs_enabled = True
    if parsed.obs_port:
        cfg.obs_port = parsed.obs_port

    return cfg
