import { useCallback, useState } from "react";
import { BiasControls } from "./components/BiasControls";
import { ConnectionStatus } from "./components/ConnectionStatus";
import { Live2DAvatar } from "./components/Live2DAvatar";
import { SensitivityControls } from "./components/SensitivityControls";
import { SettleOverlay } from "./components/SettleOverlay";
import { SignalQuality } from "./components/SignalQuality";
import { useMuseStream } from "./hooks/useMuseStream";
import type { BciEvent } from "./hooks/useMuseStream";

function App() {
  const { metrics, lastEvent, lastBlink, connected, send } = useMuseStream();
  const [debugBlink, setDebugBlink] = useState<BciEvent | null>(null);

  const triggerDebugBlink = useCallback(() => {
    // New object reference each click so the avatar sees it as a new event
    setDebugBlink({ kind: "blink", confidence: 1.0 });
    // Clear after animation completes so next click creates a fresh reference
    setTimeout(() => setDebugBlink(null), 200);
  }, []);

  // Use debug blink if set, otherwise use real blink
  const activeBlink = debugBlink ?? lastBlink;

  return (
    <div className="dark min-h-screen bg-background text-foreground flex">
      {/* Sidebar */}
      <div className="w-72 border-r border-border p-4 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-sm font-semibold">Muse VTuber Setup</h1>
          <ConnectionStatus connected={connected} />
        </div>

        <SignalQuality
          amplitudeQuality={metrics?.amplitude_quality}
          amplitudeFit={metrics?.amplitude_fit}
          psdQuality={metrics?.psd_quality}
          psdFit={metrics?.psd_fit}
        />

        {/* Head pose readout */}
        {metrics?.initialized && (
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Live Values
            </span>
            <div className="grid grid-cols-3 gap-1 text-center">
              {(["pitch", "yaw", "roll"] as const).map((axis) => (
                <div key={axis} className="bg-muted rounded px-2 py-1">
                  <div className="text-[10px] text-muted-foreground uppercase">{axis}</div>
                  <div className="text-sm font-mono">
                    {(metrics.head_pose?.[axis] ?? 0).toFixed(1)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <BiasControls send={send} />
        <SensitivityControls send={send} />

        {/* Last BCI event */}
        {lastEvent && (
          <div className="text-xs text-muted-foreground">
            Event: <span className="text-foreground font-medium">{lastEvent.kind}</span>
            {" "}({(lastEvent.confidence * 100).toFixed(0)}%)
          </div>
        )}

        <button
          onClick={triggerDebugBlink}
          className="px-3 py-1.5 text-xs bg-muted hover:bg-muted/80 rounded border border-border"
        >
          Debug Blink
        </button>

        <div className="mt-auto text-[10px] text-muted-foreground">
          Start backend: uv run muse-vtuber --synthetic --model /path/to/model
        </div>
      </div>

      {/* Main area — Live2D avatar + settle overlay */}
      <div className="flex-1 relative">
        <Live2DAvatar metrics={metrics} lastEvent={activeBlink} modelFile={metrics?.model_file} />
        {connected && metrics && !metrics.initialized && (
          <SettleOverlay settleProgress={metrics.settle_progress} />
        )}
      </div>
    </div>
  );
}

export default App;
