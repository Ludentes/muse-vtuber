"""Send obvious repeating parameters to visually verify VTube Studio connection.

Usage:
    uv run python scripts/test_vts_visual.py

First run: VTube Studio will show a popup asking to approve "Muse VTuber Bridge".
Click Allow. The auth token is saved for future runs.

The model should visibly blink every ~2 seconds and mouth should oscillate.
Press Ctrl+C to stop.
"""
from __future__ import annotations

import asyncio
import math
import time

import pyvts


PLUGIN_NAME = "Muse VTuber Bridge"
PLUGIN_DEVELOPER = "Ludentes"


async def main() -> None:
    plugin_info = {
        "plugin_name": PLUGIN_NAME,
        "developer": PLUGIN_DEVELOPER,
        "authentication_token_path": "./vts_token.txt",
    }

    vts = pyvts.vts(plugin_info=plugin_info)

    print("Connecting to VTube Studio...")
    await vts.connect()

    print("Authenticating (check VTube Studio for approval popup on first run)...")
    await vts.request_authenticate_token()
    await vts.request_authenticate()
    print("Authenticated!\n")

    print("Sending test values using built-in parameters (no binding needed).")
    print("You should see: blink every ~2s, mouth oscillating, smile pulsing")
    print("Press Ctrl+C to stop\n")

    t0 = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0

            # Blink: eyes close for 150ms every 2 seconds
            blink_cycle = t % 2.0
            eye_open = 0.0 if blink_cycle < 0.15 else 1.0

            # Mouth: smooth sine wave (open/close)
            mouth = max(0.0, math.sin(t * 2.0))

            # Smile: slow pulse
            smile = (math.sin(t * 0.5) + 1.0) / 2.0

            # Inject into VTS built-in parameters
            for name, val in [
                ("EyeOpenLeft", eye_open),
                ("EyeOpenRight", eye_open),
                ("MouthOpen", mouth),
                ("MouthSmile", smile),
            ]:
                req = vts.vts_request.requestSetParameterValue(
                    parameter=name,
                    value=val,
                )
                await vts.request(req)

            if eye_open == 0.0:
                print(f"  t={t:.1f}s  BLINK  mouth={mouth:.2f}  smile={smile:.2f}")

            await asyncio.sleep(1 / 30)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nStopped.")
    finally:
        await vts.close()


if __name__ == "__main__":
    asyncio.run(main())
