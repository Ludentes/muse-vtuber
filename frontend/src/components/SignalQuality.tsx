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

type FitStatus = "good" | "adjust" | "poor" | "unknown";

function fitVariant(status: FitStatus) {
  if (status === "good") return "default" as const;
  if (status === "adjust") return "secondary" as const;
  return "destructive" as const;
}

function QualityBars({
  label,
  quality,
  fitStatus,
}: {
  label: string;
  quality?: Record<string, number>;
  fitStatus?: FitStatus;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        <Badge
          variant={fitVariant(fitStatus ?? "unknown")}
          className="text-[10px] px-1.5 py-0"
        >
          {fitStatus ?? "---"}
        </Badge>
      </div>

      {CHANNELS.map((ch) => {
        const q = quality?.[ch] ?? 0;
        return (
          <div key={ch} className="flex items-center gap-2">
            <span
              className="text-[10px] font-mono w-8 text-right"
              style={{ color: CH_COLORS[ch] }}
            >
              {ch}
            </span>
            <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
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
  );
}

interface Props {
  amplitudeQuality?: Record<string, number>;
  amplitudeFit?: FitStatus;
  psdQuality?: Record<string, number>;
  psdFit?: FitStatus;
}

export function SignalQuality({ amplitudeQuality, amplitudeFit, psdQuality, psdFit }: Props) {
  return (
    <div className="space-y-3">
      <QualityBars
        label="Amplitude"
        quality={amplitudeQuality}
        fitStatus={amplitudeFit}
      />
      <QualityBars
        label="PSD Ratio"
        quality={psdQuality}
        fitStatus={psdFit}
      />
    </div>
  );
}
