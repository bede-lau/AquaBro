import { useEffect } from "react";
import type { VoiceEvent } from "../types";

// Short, plain, urgent — spoken aloud + shown.
const EMERGENCY =
  "Critical hypoxia in Tank 1. Oxygen is crashing. " +
  "Aerate now or the fish start dying.";

interface Props {
  voice: VoiceEvent;
  onResolve: (action: "execute" | "cancel") => void;
}

/** Emergency escalation overlay. Speaks the line via the browser's built-in
 *  SpeechSynthesis (no external voice service) and waits for the operator. */
export default function VoiceOverlay({ voice, onResolve }: Props) {
  useEffect(() => {
    try {
      const u = new SpeechSynthesisUtterance(EMERGENCY);
      u.rate = 1; u.pitch = 0.9;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch { /* speech unavailable */ }
  }, [voice]);

  return (
    <div className="voice-overlay">
      <div className="voice-card">
        <h2>⚠ Emergency Situation</h2>
        <p>{EMERGENCY}</p>
        <div className="actions">
          <button className="btn danger" onClick={() => onResolve("execute")}>
            ▶ Aerate now
          </button>
          <button className="btn" onClick={() => onResolve("cancel")}>
            ✕ Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
