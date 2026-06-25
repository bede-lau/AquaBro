import { useEffect, useRef } from "react";
import type {
  HardwareState,
  NarrativeLine,
  TankState,
  ToxicityPoint,
  VoiceEvent,
} from "../types";

export interface StreamHandlers {
  onState: (s: TankState) => void;
  onNarrative: (n: NarrativeLine) => void;
  onToxicity: (p: ToxicityPoint) => void;
  onVoice: (v: VoiceEvent) => void;
  onHardware: (h: HardwareState) => void;
}

/** Subscribe to the backend SSE bus. EventSource auto-reconnects on drop. */
export function useStream(handlers: StreamHandlers) {
  const ref = useRef(handlers);
  ref.current = handlers;

  useEffect(() => {
    const es = new EventSource("/api/stream");
    es.onmessage = (e) => {
      let ev: any;
      try {
        ev = JSON.parse(e.data);
      } catch {
        return;
      }
      const h = ref.current;
      switch (ev.type) {
        case "state":
          h.onState(ev.state as TankState);
          break;
        case "narrative":
          h.onNarrative({
            ts: ev.ts,
            level: (ev.level ?? "info") as NarrativeLine["level"],
            text: String(ev.text ?? ""),
          });
          break;
        case "toxicity":
          h.onToxicity({ t: ev.ts, nh3: ev.nh3, threshold: ev.threshold });
          break;
        case "voice":
          h.onVoice({
            provider: ev.provider,
            system_prompt: ev.system_prompt,
            agent_id: ev.agent_id,
            webhook_url: ev.webhook_url ?? "",
          });
          break;
        case "hardware":
          h.onHardware(ev.hardware as HardwareState);
          break;
      }
    };
    return () => es.close();
  }, []);
}
