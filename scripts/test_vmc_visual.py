"""Send obvious repeating blendshapes to visually verify VMC connection.

Usage:
    uv run python scripts/test_vmc_visual.py [--port 39539]

The model should visibly blink every ~2 seconds and open/close mouth.
Press Ctrl+C to stop.
"""
from __future__ import annotations

import math
import time
import sys

from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.udp_client import SimpleUDPClient


def blend_val(client: SimpleUDPClient, name: str, value: float) -> None:
    b = OscMessageBuilder(address="/VMC/Ext/Blend/Val")
    b.add_arg(name)
    b.add_arg(float(value))
    client.send(b.build())


def blend_apply(client: SimpleUDPClient) -> None:
    b = OscMessageBuilder(address="/VMC/Ext/Blend/Apply")
    client.send(b.build())


def main() -> None:
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 39539
    client = SimpleUDPClient("127.0.0.1", port)
    print(f"Sending test blendshapes to 127.0.0.1:{port}")
    print("You should see: blink every ~2s, mouth oscillating, Joy expression pulsing")
    print("Press Ctrl+C to stop\n")

    t0 = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0

            # Blink: 1.0 for 150ms every 2 seconds
            blink_cycle = t % 2.0
            blink = 1.0 if blink_cycle < 0.15 else 0.0

            # Mouth: smooth sine wave (open/close)
            mouth = max(0.0, math.sin(t * 2.0))

            # Joy: slow pulse
            joy = (math.sin(t * 0.5) + 1.0) / 2.0

            # Send all — using VRM standard names
            blend_val(client, "Blink", blink)
            blend_val(client, "Blink_L", blink)
            blend_val(client, "Blink_R", blink)
            blend_val(client, "A", mouth)          # mouth open (vowel A)
            blend_val(client, "Joy", joy)
            blend_val(client, "O", mouth * 0.3)    # slight O shape
            blend_apply(client)

            if blink > 0:
                print(f"  t={t:.1f}s  BLINK  mouth={mouth:.2f}  joy={joy:.2f}")
            elif int(t) % 2 == 0 and t % 1.0 < 0.02:
                print(f"  t={t:.1f}s  blink=0  mouth={mouth:.2f}  joy={joy:.2f}")

            time.sleep(1 / 60)  # 60 FPS
    except KeyboardInterrupt:
        # Send zeros to reset
        for name in ("Blink", "Blink_L", "Blink_R", "A", "Joy", "O"):
            blend_val(client, name, 0.0)
        blend_apply(client)
        print("\nStopped. Reset all blendshapes to 0.")


if __name__ == "__main__":
    main()
