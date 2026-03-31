import { useEffect, useRef, useState } from "react";
import { Application } from "pixi.js";
import { Live2DModel } from "@naari3/pixi-live2d-display";
import type { MuseMetrics, BciEvent } from "../hooks/useMuseStream";

// Live2D parameter names
const PARAM_ANGLE_X = "ParamAngleX";
const PARAM_ANGLE_Y = "ParamAngleY";
const PARAM_ANGLE_Z = "ParamAngleZ";
const PARAM_EYE_L_OPEN = "ParamEyeLOpen";
const PARAM_EYE_R_OPEN = "ParamEyeROpen";

// Blink animation: close over 50ms, reopen over 100ms
const BLINK_CLOSE_MS = 50;
const BLINK_OPEN_MS = 100;

interface Props {
  metrics: MuseMetrics | null;
  lastEvent: BciEvent | null;
  modelFile?: string;
}

interface ParamMap {
  [name: string]: number; // param name → index
}

function buildParamMap(coreModel: any): ParamMap {
  const map: ParamMap = {};
  const count: number = coreModel.getParameterCount();
  for (let i = 0; i < count; i++) {
    const id = coreModel.getParameterId(i);
    // CubismId has a getString() method
    const name = id?.getString?.() ?? id?.toString?.() ?? `param_${i}`;
    map[name] = i;
  }
  return map;
}

export function Live2DAvatar({ metrics, lastEvent, modelFile }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const modelRef = useRef<Live2DModel | null>(null);
  const paramMapRef = useRef<ParamMap>({});
  const blinkRef = useRef({ active: false, startTime: 0, lastEventKind: "" });
  const [error, setError] = useState<string | null>(null);

  // Initialize PixiJS + load model
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !modelFile) return;

    let cancelled = false;

    async function init() {
      const app = new Application();
      await app.init({
        background: 0x111111,
        resizeTo: container!,
        antialias: true,
      });

      if (cancelled) {
        app.destroy();
        return;
      }

      container!.appendChild(app.canvas as HTMLCanvasElement);
      appRef.current = app;

      try {
        const model = await Live2DModel.from(`/model/${modelFile}`);
        if (cancelled) return;

        // Scale to fit canvas
        const scale = Math.min(
          app.screen.width / model.width,
          app.screen.height / model.height,
        ) * 0.9;
        model.scale.set(scale);
        model.x = (app.screen.width - model.width * scale) / 2;
        model.y = (app.screen.height - model.height * scale) / 2;

        app.stage.addChild(model);
        modelRef.current = model;

        // Build parameter index map
        const coreModel = (model as any).internalModel?.coreModel;
        if (coreModel) {
          paramMapRef.current = buildParamMap(coreModel);
        }
      } catch (err) {
        console.error("Live2D model load failed:", err);
        setError("Failed to load Live2D model. Is --model set?");
      }
    }

    init();

    return () => {
      cancelled = true;
      if (appRef.current) {
        appRef.current.destroy(true);
        appRef.current = null;
      }
      modelRef.current = null;
    };
  }, [modelFile]);

  // Drive parameters from metrics + events
  useEffect(() => {
    let raf: number;

    function animate() {
      const model = modelRef.current;
      const coreModel = (model as any)?.internalModel?.coreModel;
      if (!coreModel) {
        raf = requestAnimationFrame(animate);
        return;
      }

      const pmap = paramMapRef.current;

      // Head angles from metrics
      if (metrics?.initialized) {
        const { pitch, yaw, roll } = metrics.head_pose;
        if (PARAM_ANGLE_X in pmap) {
          coreModel.setParameterValueByIndex(pmap[PARAM_ANGLE_X], yaw);
        }
        if (PARAM_ANGLE_Y in pmap) {
          coreModel.setParameterValueByIndex(pmap[PARAM_ANGLE_Y], pitch);
        }
        if (PARAM_ANGLE_Z in pmap) {
          coreModel.setParameterValueByIndex(pmap[PARAM_ANGLE_Z], roll);
        }
      }

      // Blink animation
      const blink = blinkRef.current;
      if (lastEvent?.kind === "blink" && !blink.active) {
        blink.active = true;
        blink.startTime = performance.now();
      }

      let eyeOpen = 1.0;
      if (blink.active) {
        const elapsed = performance.now() - blink.startTime;
        if (elapsed < BLINK_CLOSE_MS) {
          eyeOpen = 1.0 - elapsed / BLINK_CLOSE_MS;
        } else if (elapsed < BLINK_CLOSE_MS + BLINK_OPEN_MS) {
          eyeOpen = (elapsed - BLINK_CLOSE_MS) / BLINK_OPEN_MS;
        } else {
          eyeOpen = 1.0;
          blink.active = false;
        }
      }

      if (PARAM_EYE_L_OPEN in pmap) {
        coreModel.setParameterValueByIndex(pmap[PARAM_EYE_L_OPEN], eyeOpen);
      }
      if (PARAM_EYE_R_OPEN in pmap) {
        coreModel.setParameterValueByIndex(pmap[PARAM_EYE_R_OPEN], eyeOpen);
      }

      raf = requestAnimationFrame(animate);
    }

    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [metrics, lastEvent]);

  return (
    <div ref={containerRef} className="w-full h-full relative">
      {!modelFile && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">No model configured. Start backend with --model flag.</p>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}
    </div>
  );
}
