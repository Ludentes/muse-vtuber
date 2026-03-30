import numpy as np
import pytest

from muse_vtuber.source import BrainFlowSource, BCISource


def test_brainflow_source_implements_protocol():
    """BrainFlowSource satisfies BCISource protocol."""
    source = BrainFlowSource(board_id=-1)  # synthetic
    assert isinstance(source, BCISource)


def test_synthetic_board_lifecycle():
    """Start, poll, stop with BrainFlow synthetic board."""
    source = BrainFlowSource(board_id=-1)
    source.start()
    try:
        # Synthetic board generates data immediately
        import time
        time.sleep(0.1)  # let some data accumulate

        eeg = source.poll_eeg()
        assert eeg is not None
        assert eeg.ndim == 2
        assert eeg.shape[0] > 0  # has channels

        assert source.eeg_sample_rate > 0
    finally:
        source.stop()


def test_synthetic_board_imu():
    """Synthetic board may or may not have IMU — poll returns None if not."""
    source = BrainFlowSource(board_id=-1)
    source.start()
    try:
        import time
        time.sleep(0.1)
        # Synthetic board doesn't have IMU preset by default
        imu = source.poll_imu()
        # Either None (no IMU) or (6, n) array
        if imu is not None:
            assert imu.ndim == 2
            assert imu.shape[0] == 6
    finally:
        source.stop()


def test_board_id_from_string():
    """Board ID can be specified as a BrainFlow name string."""
    source = BrainFlowSource(board_id="SYNTHETIC_BOARD")
    assert source.board_id == -1


def test_poll_before_start_returns_none():
    source = BrainFlowSource(board_id=-1)
    assert source.poll_eeg() is None
    assert source.poll_imu() is None
