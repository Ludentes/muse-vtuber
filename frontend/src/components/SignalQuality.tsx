import { Badge } from "./ui/badge";

const CHANNELS = ["TP9", "AF7", "AF8", "TP10"] as const;

const CH_COLORS: Record<string, string> = {
  TP9: "#ef4444",   // red
  AF7: "#f59e0b",   // amber
  AF8: "#22c55e",   // green
  TP10: "#3b82f6",  // blue
};

function qualityColor(q: number): string {
  if (q >= 0.7) return "#22c55e";
  if (q >= 0.4) return "#f59e0b";
  return "#ef4444";
}

interface Props {
  signalQuality?: Record<string, number>;
  fitStatus?: string;
}

export function SignalQuality({ signalQuality, fitStatus }: Props) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Signal Quality
        </span>
        <Badge
          variant={fitStatus === "good" ? "default" : fitStatus === "adjust" ? "secondary" : "destructive"}
          className="text-[10px] px-1.5 py-0"
        >
          {fitStatus ?? "---"}
        </Badge>
      </div>

      <div className="space-y-1.5">
        {CHANNELS.map((ch) => {
          const q = signalQuality?.[ch] ?? 0;
          return (
            <div key={ch} className="flex items-center gap-2">
              <span
                className="text-[10px] font-mono w-8 text-right"
                style={{ color: CH_COLORS[ch] }}
              >
                {ch}
              </span>
              <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.round(q * 100)}%`,
                    backgroundColor: qualityColor(q),
                  }}
                />
              </div>
              <span className="text-[10px] font-mono w-8 text-muted-foreground">
                {Math.round(q * 100)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
