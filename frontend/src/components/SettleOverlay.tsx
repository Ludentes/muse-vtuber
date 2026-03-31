interface Props {
  settleProgress: number;
}

export function SettleOverlay({ settleProgress }: Props) {
  if (settleProgress >= 1) return null;

  const secondsLeft = Math.ceil((1 - settleProgress) * 5);

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10 bg-background/60">
      <div className="text-center">
        <p className="text-muted-foreground text-lg mb-2">Calibrating — hold still</p>
        <p className="text-foreground text-4xl font-bold font-mono">{secondsLeft}s</p>
        <div className="mt-3 w-48 h-1.5 bg-muted rounded-full mx-auto overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-200"
            style={{ width: `${settleProgress * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
