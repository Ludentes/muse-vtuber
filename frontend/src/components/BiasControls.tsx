import { useState, useCallback, useEffect, useRef } from "react";
import { Slider } from "./ui/slider";
import { Button } from "./ui/button";

interface Props {
  send: (cmd: object) => void;
}

function BiasSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono w-8 text-muted-foreground uppercase">{label}</span>
      <Slider
        min={-45}
        max={45}
        step={1}
        value={[value]}
        onValueChange={(val) => onChange(Array.isArray(val) ? val[0] : val)}
        className="flex-1"
      />
      <span className="text-[10px] font-mono w-8 text-right text-muted-foreground">
        {value > 0 ? "+" : ""}{value}
      </span>
    </div>
  );
}

export function BiasControls({ send }: Props) {
  const [pitch, setPitch] = useState(0);
  const [yaw, setYaw] = useState(0);
  const [roll, setRoll] = useState(0);

  // Send bias to backend whenever sliders change (skip initial mount)
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    send({ type: "set_bias", pitch, yaw, roll });
  }, [pitch, yaw, roll, send]);

  const handleRecenter = useCallback(() => {
    send({ type: "recenter" });
  }, [send]);

  const handleReset = useCallback(() => {
    setPitch(0);
    setYaw(0);
    setRoll(0);
  }, []);

  return (
    <div className="space-y-2">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Head Tracking
      </span>

      <div className="space-y-1.5">
        <BiasSlider label="Pitch" value={pitch} onChange={setPitch} />
        <BiasSlider label="Yaw" value={yaw} onChange={setYaw} />
        <BiasSlider label="Roll" value={roll} onChange={setRoll} />
      </div>

      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1 text-xs" onClick={handleRecenter}>
          Recenter
        </Button>
        <Button variant="ghost" size="sm" className="text-xs" onClick={handleReset}>
          Reset bias
        </Button>
      </div>
    </div>
  );
}
