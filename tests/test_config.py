import pytest

from muse_vtuber.config import AppConfig, load_config_from_dict


def test_default_config():
    cfg = AppConfig()
    assert cfg.board_id == "MUSE_2_BOARD"
    assert cfg.vmc_port == 39539
    assert cfg.vmc_enabled is True
    assert cfg.osc_enabled is False


def test_load_from_dict():
    cfg = load_config_from_dict({
        "device": {"board_id": "SYNTHETIC_BOARD", "mac_address": ""},
        "outputs": {
            "vmc": {"enabled": True, "port": 12345},
            "osc": {"enabled": True, "port": 9000},
        },
    })
    assert cfg.board_id == "SYNTHETIC_BOARD"
    assert cfg.vmc_port == 12345
    assert cfg.osc_enabled is True
