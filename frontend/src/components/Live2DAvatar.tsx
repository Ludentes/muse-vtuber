import { useEffect, useRef, useState } from "react";
import { Application } from "pixi.js";
import { Live2DModel } from "untitled-pixi-live2d-engine/cubism";
import type { MuseMetrics, BciEvent } from "../hooks/useMuseStream";

// Blink animation: close over 50ms, reopen over 100ms
const BLINK_CLOSE_MS = 50;
const BLINK_OPEN_MS = 100;

interface Props {
  metrics: MuseMetrics | null;
  lastEvent: BciEvent | null;
  modelFile?: string;
}

export function Live2DAvatar({ metrics, lastEvent, modelFile }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const blinkRef = useRef({
    active: false,
    startTime: 0,
    lastProcessedEvent: null as BciEvent | null,
  });
  const [error, setError] = useState<string | null>(null);

  // Store metrics and lastEvent in refs so callbacks read current values
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
        const model = await Live2DModel.from(`/model/${modelFile}`, {
          autoFocus: false,
          autoHitTest: false,
          ticker: app.ticker,
          breathDepth: 0,
        });
        if (cancelled) return;

        // Scale to fit canvas using unscaled dimensions from internalModel
        const im = (model as any).internalModel;
        const origW = im?.originalWidth || model.width;
        const origH = im?.originalHeight || model.height;
        const scale = Math.min(
          app.screen.width / origW,
          app.screen.height / origH,
        ) * 0.9;
        model.scale.set(scale);
        model.x = (app.screen.width - origW * scale) / 2;
        model.y = (app.screen.height - origH * scale) / 2;

        app.stage.addChild(model);

        const internalModel = (model as any).internalModel;
        if (internalModel) {
          // Disable built-in animations — we drive all params from Muse
          internalModel.eyeBlink = null;
          internalModel.motionManager.stopAllMotions();
          internalModel.motionManager.update = () => false;

          const cm = internalModel.coreModel;

          // Resolve ALL param indices ourselves.
          // The new library (Cubism 4/5) uses idParamAngleX (CubismIdHandle)
          // instead of angleXParamIndex (number), so we can't rely on
          // library-cached indices. Resolve by name for all Cubism versions.
          const paramIndices: Record<string, number> = {};
          const PARAM_NAMES = [
            "ParamAngleX", "ParamAngleY", "ParamAngleZ",
            "ParamBodyAngleX",
            "ParamEyeBallX", "ParamEyeBallY",
            "ParamEyeLOpen", "ParamEyeROpen",
          ];
          const paramCount = cm.getParameterCount();
          for (let i = 0; i < paramCount; i++) {
            const id = cm.getParameterId(i);
            // Cubism 5: id may be { _id: { s: "Name" } } or plain string
            const name = typeof id === "string" ? id
              : id?._id?.s ?? id?.getString?.()?.s ?? id?.getString?.() ?? "";
            if (PARAM_NAMES.includes(name)) {
              paramIndices[name] = i;
            }
          }

          // Override updateFocus to drive params from Muse data
          internalModel.updateFocus = () => {
            const m = metricsRef.current;
            const evt = lastEventRef.current;

            // Head angles from Muse IMU
            if (m?.initialized && "ParamAngleX" in paramIndices) {
              const { pitch, yaw, roll } = m.head_pose;
              cm.setParameterValueByIndex(paramIndices.ParamAngleX, yaw);
              cm.setParameterValueByIndex(paramIndices.ParamAngleY, pitch);
              cm.setParameterValueByIndex(paramIndices.ParamAngleZ, roll);
              if ("ParamBodyAngleX" in paramIndices) {
                cm.setParameterValueByIndex(paramIndices.ParamBodyAngleX, yaw * 0.3);
              }
            }

            // Blink animation from BCI events
            const blink = blinkRef.current;
            if (
              evt?.kind === "blink" &&
              !blink.active &&
              evt !== blink.lastProcessedEvent
            ) {
              blink.active = true;
              blink.startTime = performance.now();
              blink.lastProcessedEvent = evt;
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

            if ("ParamEyeBallX" in paramIndices) {
              cm.setParameterValueByIndex(paramIndices.ParamEyeBallX, 0);
              cm.setParameterValueByIndex(paramIndices.ParamEyeBallY, 0);
            }
            if ("ParamEyeLOpen" in paramIndices) {
              cm.setParameterValueByIndex(paramIndices.ParamEyeLOpen, eyeOpen);
            }
            if ("ParamEyeROpen" in paramIndices) {
              cm.setParameterValueByIndex(paramIndices.ParamEyeROpen, eyeOpen);
            }
          };
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
    };
  }, [modelFile]);

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
