import { useState, useEffect, useRef } from "react";
import { Slider } from "./ui/slider";

interface Props {
  send: (cmd: object) => void;
}

function SensSlider({
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
        min={0.5}
        max={8}
        step={0.5}
        value={[value]}
        onValueChange={(val) => onChange(Array.isArray(val) ? val[0] : val)}
        className="flex-1"
      />
      <span className="text-[10px] font-mono w-8 text-right text-muted-foreground">
        {value.toFixed(1)}x
      </span>
    </div>
  );
}

function WeightSlider({
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
        min={0}
        max={1}
        step={0.05}
        value={[value]}
        onValueChange={(val) => onChange(Array.isArray(val) ? val[0] : val)}
        className="flex-1"
      />
      <span className="text-[10px] font-mono w-8 text-right text-muted-foreground">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

export function SensitivityControls({ send }: Props) {
  const [yaw, setYaw] = useState(4.0);
  const [pitch, setPitch] = useState(1.5);
  const [roll, setRoll] = useState(1.0);
  const [angleWeight, setAngleWeight] = useState(1.0);
  const [eyeWeight, setEyeWeight] = useState(1.0);

  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return; }
    send({ type: "set_sensitivity", yaw, pitch, roll });
  }, [yaw, pitch, roll, send]);

  const weightMounted = useRef(false);
  useEffect(() => {
    if (!weightMounted.current) { weightMounted.current = true; return; }
    send({ type: "set_vts_weight", angle: angleWeight, eye: eyeWeight });
  }, [angleWeight, eyeWeight, send]);

  return (
    <div className="space-y-2">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Sensitivity
      </span>
      <div className="space-y-1.5">
        <SensSlider label="Yaw" value={yaw} onChange={setYaw} />
        <SensSlider label="Pitch" value={pitch} onChange={setPitch} />
        <SensSlider label="Roll" value={roll} onChange={setRoll} />
      </div>
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Head Override
      </span>
      <div className="space-y-1.5">
        <WeightSlider label="Pose" value={angleWeight} onChange={setAngleWeight} />
        <WeightSlider label="Eyes" value={eyeWeight} onChange={setEyeWeight} />
        <div className="text-[9px] text-muted-foreground leading-tight">
          1.0 = IMU · 0.0 = camera
        </div>
      </div>
    </div>
  );
}
