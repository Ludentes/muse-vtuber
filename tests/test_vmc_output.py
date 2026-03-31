import pytest

from muse_vtuber.outputs.vmc import VMCOutput, VMCBlendshapes


def test_vmc_output_builds_blendshape_messages():
    """VMC output converts blendshapes to OSC messages."""
    vmc = VMCOutput(host="127.0.0.1", port=0)  # port 0 = don't actually send

    blendshapes = VMCBlendshapes(
        blink=1.0,
        clench=0.5,
        focus=0.7,
        relaxation=0.3,
    )
    messages = vmc.build_blendshape_messages(blendshapes)

    # Should have: 4 Blend/Val + 1 Blend/Apply + 1 OK + 1 T = 7
    addresses = [m.address for m in messages]
    assert "/VMC/Ext/Blend/Val" in addresses
    assert "/VMC/Ext/Blend/Apply" in addresses
    assert "/VMC/Ext/OK" in addresses
    assert "/VMC/Ext/T" in addresses

    # Check blink value
    blink_msgs = [m for m in messages if m.address == "/VMC/Ext/Blend/Val" and m.params[0] == "blink"]
    assert len(blink_msgs) == 1
    assert blink_msgs[0].params[1] == 1.0


def test_vmc_blendshape_names():
    """Blendshape names follow VMC convention."""
    vmc = VMCOutput(host="127.0.0.1", port=0)
    blendshapes = VMCBlendshapes(blink=0.5, clench=0.0, focus=0.0, relaxation=0.0)
    messages = vmc.build_blendshape_messages(blendshapes)
    blend_names = [m.params[0] for m in messages if m.address == "/VMC/Ext/Blend/Val"]
    assert "blink" in blend_names
    assert "muse_clench" in blend_names
    assert "muse_focus" in blend_names
    assert "muse_relaxation" in blend_names
