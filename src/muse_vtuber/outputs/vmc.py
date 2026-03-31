from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.udp_client import SimpleUDPClient

log = logging.getLogger("vmc")


@dataclass
class VMCBlendshapes:
    blink: float = 0.0       # 0-1
    clench: float = 0.0      # 0-1
    focus: float = 0.0       # 0-1
    relaxation: float = 0.0  # 0-1


@dataclass
class VMCBoneTransform:
    """Bone position + rotation for /VMC/Ext/Bone/Pos."""
    bone_name: str
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    rot_x: float = 0.0
    rot_y: float = 0.0
    rot_z: float = 0.0
    rot_w: float = 1.0


def _blend_val(name: str, value: float) -> OscMessage:
    builder = OscMessageBuilder(address="/VMC/Ext/Blend/Val")
    builder.add_arg(name)
    builder.add_arg(float(value))
    return builder.build()


def _blend_apply() -> OscMessage:
    builder = OscMessageBuilder(address="/VMC/Ext/Blend/Apply")
    return builder.build()


def _bone_pos(bone: VMCBoneTransform) -> OscMessage:
    builder = OscMessageBuilder(address="/VMC/Ext/Bone/Pos")
    builder.add_arg(bone.bone_name)
    builder.add_arg(float(bone.pos_x))
    builder.add_arg(float(bone.pos_y))
    builder.add_arg(float(bone.pos_z))
    builder.add_arg(float(bone.rot_x))
    builder.add_arg(float(bone.rot_y))
    builder.add_arg(float(bone.rot_z))
    builder.add_arg(float(bone.rot_w))
    return builder.build()


def _ok() -> OscMessage:
    builder = OscMessageBuilder(address="/VMC/Ext/OK")
    builder.add_arg(1)
    return builder.build()


def _time_msg() -> OscMessage:
    builder = OscMessageBuilder(address="/VMC/Ext/T")
    builder.add_arg(float(time.monotonic()))
    return builder.build()


class VMCOutput:
    """VMC protocol output via UDP/OSC.

    Sends blendshapes for EEG expressions and bone transforms for head tracking.
    Uses python-osc directly (no python-vmcp dependency).
    """

    BLEND_MAP = {
        "blink": "blink",
        "clench": "muse_clench",
        "focus": "muse_focus",
        "relaxation": "muse_relaxation",
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 39539):
        self.host = host
        self.port = port
        self._client: SimpleUDPClient | None = None
        if port > 0:
            self._client = SimpleUDPClient(host, port)

    def build_blendshape_messages(self, blendshapes: VMCBlendshapes) -> list[OscMessage]:
        """Build OSC messages for blendshape frame (without sending)."""
        messages: list[OscMessage] = []
        values = {
            "blink": blendshapes.blink,
            "clench": blendshapes.clench,
            "focus": blendshapes.focus,
            "relaxation": blendshapes.relaxation,
        }
        for internal_name, vmc_name in self.BLEND_MAP.items():
            messages.append(_blend_val(vmc_name, values[internal_name]))
        messages.append(_blend_apply())
        messages.append(_ok())
        messages.append(_time_msg())
        return messages

    def build_bone_messages(self, bones: list[VMCBoneTransform]) -> list[OscMessage]:
        """Build OSC messages for bone transforms."""
        return [_bone_pos(bone) for bone in bones]

    def send_blendshapes(self, blendshapes: VMCBlendshapes) -> None:
        """Send blendshape frame over UDP."""
        if self._client is None:
            return
        for msg in self.build_blendshape_messages(blendshapes):
            self._client.send(msg)

    def send_bones(self, bones: list[VMCBoneTransform]) -> None:
        """Send bone transforms over UDP."""
        if self._client is None:
            return
        for msg in self.build_bone_messages(bones):
            self._client.send(msg)

    def send_frame(
        self,
        blendshapes: VMCBlendshapes | None = None,
        bones: list[VMCBoneTransform] | None = None,
    ) -> None:
        """Send a complete VMC frame (blendshapes + bones + status)."""
        if self._client is None:
            return
        if bones:
            self.send_bones(bones)
        if blendshapes:
            self.send_blendshapes(blendshapes)
