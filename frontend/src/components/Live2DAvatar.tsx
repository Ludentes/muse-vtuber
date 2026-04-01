import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";
import { Application } from "pixi.js";
import { Live2DModel } from "@naari3/pixi-live2d-display";
import type { MuseMetrics, BciEvent } from "../hooks/useMuseStream";

// pixi-live2d-display requires window.PIXI for Ticker access (PixiJS v8 doesn't set this)
(window as any).PIXI = PIXI;

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
  const blinkRef = useRef({
    active: false,
    startTime: 0,
    lastProcessedEvent: null as BciEvent | null,
  });
  const [error, setError] = useState<string | null>(null);

  // Store metrics and lastEvent in refs so animation loop doesn't re-mount
  const metricsRef = useRef(metrics);
  const lastEventRef = useRef(lastEvent);
  metricsRef.current = metrics;
  lastEventRef.current = lastEvent;

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

        console.log("Live2D model loaded:", {
          modelWidth: model.width,
          modelHeight: model.height,
          canvasWidth: app.screen.width,
          canvasHeight: app.screen.height,
          containerSize: [container!.clientWidth, container!.clientHeight],
        });

        // Scale to fit canvas
        const scale = Math.min(
          app.screen.width / model.width,
          app.screen.height / model.height,
        ) * 0.9;
        model.scale.set(scale);
        model.x = (app.screen.width - model.width * scale) / 2;
        model.y = (app.screen.height - model.height * scale) / 2;

        console.log("Live2D positioning:", { scale, x: model.x, y: model.y });

        app.stage.addChild(model);
        modelRef.current = model;

        // Build parameter index map
        const coreModel = (model as any).internalModel?.coreModel;
        if (coreModel) {
          paramMapRef.current = buildParamMap(coreModel);
          console.log("Live2D params:", Object.keys(paramMapRef.current).join(", "));
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

  // Drive parameters from metrics + events (runs once, reads refs)
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
      const currentMetrics = metricsRef.current;
      const currentEvent = lastEventRef.current;

      // Head angles from metrics
      if (currentMetrics?.initialized) {
        const { pitch, yaw, roll } = currentMetrics.head_pose;
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

      // Blink animation — track last processed event to avoid re-triggering
      const blink = blinkRef.current;
      if (
        currentEvent?.kind === "blink" &&
        !blink.active &&
        currentEvent !== blink.lastProcessedEvent
      ) {
        blink.active = true;
        blink.startTime = performance.now();
        blink.lastProcessedEvent = currentEvent;
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
  }, []);

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
