import { ConnectionStatus } from "./components/ConnectionStatus";
import { Live2DAvatar } from "./components/Live2DAvatar";
import { SignalQuality } from "./components/SignalQuality";
import { useMuseStream } from "./hooks/useMuseStream";

function App() {
  const { metrics, lastEvent, connected } = useMuseStream();

  return (
    <div className="dark min-h-screen bg-background text-foreground flex">
      {/* Sidebar */}
      <div className="w-72 border-r border-border p-4 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="text-sm font-semibold">Muse VTuber Setup</h1>
          <ConnectionStatus connected={connected} />
        </div>

        <SignalQuality
          signalQuality={metrics?.signal_quality}
          fitStatus={metrics?.fit_status}
        />

        {/* Head pose readout */}
        {metrics?.initialized && (
          <div className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Head Pose
            </span>
            <div className="grid grid-cols-3 gap-1 text-center">
              {(["pitch", "yaw", "roll"] as const).map((axis) => (
                <div key={axis} className="bg-muted rounded px-2 py-1">
                  <div className="text-[10px] text-muted-foreground uppercase">{axis}</div>
                  <div className="text-sm font-mono">
                    {metrics.head_pose[axis].toFixed(1)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Settle progress */}
        {metrics && !metrics.initialized && (
          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">
              Calibrating... hold still
            </span>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${Math.round(metrics.settle_progress * 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Last BCI event */}
        {lastEvent && (
          <div className="text-xs text-muted-foreground">
            Event: <span className="text-foreground font-medium">{lastEvent.kind}</span>
            {" "}({(lastEvent.confidence * 100).toFixed(0)}%)
          </div>
        )}

        {/* Placeholder for bias controls (Task 6) */}
        <div className="mt-auto text-[10px] text-muted-foreground">
          Bias controls coming next...
        </div>
      </div>

      {/* Main area — Live2D avatar */}
      <div className="flex-1">
        <Live2DAvatar metrics={metrics} lastEvent={lastEvent} />
      </div>
    </div>
  );
}

export default App;
