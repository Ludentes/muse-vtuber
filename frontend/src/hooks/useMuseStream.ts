import { useCallback, useRef, useState } from "react";
import useWebSocket, { ReadyState } from "react-use-websocket";

export interface MuseMetrics {
  signal_quality: Record<string, number>;
  fit_status: "good" | "adjust" | "poor" | "unknown";
  head_pose: { pitch: number; yaw: number; roll: number };
  settle_progress: number;
  initialized: boolean;
  model_file: string;
}

export interface BciEvent {
  kind: string;
  confidence: number;
}

const WS_URL = `ws://${window.location.hostname}:8765`;

export function useMuseStream() {
  const [metrics, setMetrics] = useState<MuseMetrics | null>(null);
  const [lastEvent, setLastEvent] = useState<BciEvent | null>(null);
  const lastEventTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const { readyState, sendJsonMessage } = useWebSocket(WS_URL, {
    onMessage: (event) => {
      if (typeof event.data !== "string") return;
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "metrics") {
          setMetrics(msg as MuseMetrics);
        } else if (msg.type === "bci_event") {
          setLastEvent({ kind: msg.kind, confidence: msg.confidence });
          // Clear event after 500ms so UI can flash
          clearTimeout(lastEventTimer.current);
          lastEventTimer.current = setTimeout(() => setLastEvent(null), 500);
        }
      } catch (err) {
        console.warn("Malformed WS message:", event.data, err);
      }
    },
    shouldReconnect: () => true,
    reconnectInterval: 2000,
  });

  const send = useCallback(
    (cmd: object) => sendJsonMessage(cmd),
    [sendJsonMessage],
  );

  return {
    metrics,
    lastEvent,
    connected: readyState === ReadyState.OPEN,
    send,
  };
}
