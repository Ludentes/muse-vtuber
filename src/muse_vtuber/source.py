from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams, BrainFlowPresets

log = logging.getLogger("source")


@runtime_checkable
class BCISource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def poll_eeg(self) -> np.ndarray | None: ...
    def poll_imu(self) -> np.ndarray | None: ...

    @property
    def eeg_sample_rate(self) -> int: ...

    @property
    def imu_sample_rate(self) -> int: ...

    @property
    def has_imu(self) -> bool: ...


def _resolve_board_id(board_id: int | str) -> int:
    """Resolve board_id from int or BrainFlow name string."""
    if isinstance(board_id, int):
        return board_id
    # Try as BoardIds enum name (e.g. "SYNTHETIC_BOARD", "MUSE_2_BOARD")
    name = board_id.upper().replace("-", "_")
    if not name.endswith("_BOARD"):
        name += "_BOARD"
    try:
        return BoardIds[name].value
    except KeyError:
        pass
    # Try direct int parse
    try:
        return int(board_id)
    except ValueError:
        raise ValueError(f"Unknown board_id: {board_id!r}. Use int or BrainFlow name like 'MUSE_2_BOARD'.")


class BrainFlowSource:
    """BrainFlow-backed BCI source. Implements BCISource protocol."""

    def __init__(
        self,
        board_id: int | str = -1,
        mac_address: str = "",
        serial_port: str = "",
    ):
        self.board_id = _resolve_board_id(board_id)
        params = BrainFlowInputParams()
        if mac_address:
            params.mac_address = mac_address
        if serial_port:
            params.serial_port = serial_port
        self._board = BoardShim(self.board_id, params)
        self._streaming = False
        self._eeg_channels: list[int] = []
        self._imu_channels: list[int] = []
        self._has_imu = False

    def start(self) -> None:
        self._board.prepare_session()
        # Discover channels
        self._eeg_channels = BoardShim.get_eeg_channels(self.board_id)

        # Try to enable IMU (auxiliary preset)
        try:
            accel = BoardShim.get_accel_channels(self.board_id, BrainFlowPresets.AUXILIARY_PRESET.value)
            gyro = BoardShim.get_gyro_channels(self.board_id, BrainFlowPresets.AUXILIARY_PRESET.value)
            if accel and gyro:
                self._imu_channels = accel + gyro
                self._has_imu = True
        except Exception:
            self._has_imu = False

        self._board.start_stream()
        self._streaming = True
        log.info("BrainFlow streaming started (board_id=%d)", self.board_id)

    def stop(self) -> None:
        if self._streaming:
            try:
                self._board.stop_stream()
            except Exception:
                log.warning("Error stopping stream", exc_info=True)
            self._streaming = False
        try:
            self._board.release_session()
        except Exception:
            log.warning("Error releasing session", exc_info=True)

    def poll_eeg(self) -> np.ndarray | None:
        if not self._streaming:
            return None
        data = self._board.get_board_data()
        if data.shape[1] == 0:
            return None
        return data[self._eeg_channels]

    def poll_imu(self) -> np.ndarray | None:
        if not self._streaming or not self._has_imu:
            return None
        try:
            data = self._board.get_board_data(preset=BrainFlowPresets.AUXILIARY_PRESET.value)
            if data.shape[1] == 0:
                return None
            return data[self._imu_channels]
        except Exception:
            return None

    @property
    def eeg_sample_rate(self) -> int:
        return BoardShim.get_sampling_rate(self.board_id)

    @property
    def imu_sample_rate(self) -> int:
        if not self._has_imu:
            return 0
        try:
            return BoardShim.get_sampling_rate(self.board_id, BrainFlowPresets.AUXILIARY_PRESET.value)
        except Exception:
            return 0

    @property
    def has_imu(self) -> bool:
        return self._has_imu
