import { useEffect, useRef, useState } from "react";
import {
  getState, getTelegramStatus, hardwareOverride, playSfx,
  postChaos, resetAll, setPower, voiceResolve,
} from "./api";
import type { TelegramStatus } from "./api";
import { useStream } from "./hooks/useStream";
import type { HardwareState, NarrativeLine, TankState, ToxicityPoint, VoiceEvent } from "./types";
import { ago } from "./util";
import StatusPill from "./components/StatusPill";
import ActuatorSchematic from "./components/ActuatorSchematic";
import VisionCard from "./components/VisionCard";
import Vitals from "./components/Vitals";
import NarrativeFeed from "./components/NarrativeFeed";
import DemoBar from "./components/DemoBar";
import VoiceOverlay from "./components/VoiceOverlay";

const SEED: NarrativeLine = {
  ts: new Date().toISOString(),
  level: "info",
  text: "AquaBro online — monitoring Tank-01.",
};

export default function App() {
  const [tank, setTank] = useState<TankState | null>(null);
  const [narrative, setNarrative] = useState<NarrativeLine[]>([SEED]);
  const [, setTox] = useState<ToxicityPoint[]>([]);
  const [voice, setVoice] = useState<VoiceEvent | null>(null);
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [now, setNow] = useState(Date.now());
  const seeded = useRef(false);

  useEffect(() => {
    getState().then(setTank).catch(() => {});
    getTelegramStatus().then(setTelegram);
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  useStream({
    onState: (s) => setTank(s),
    onNarrative: (n) => {
      setNarrative((prev) => {
        if (!seeded.current) {
          seeded.current = true;
          return [n];
        }
        return [n, ...prev].slice(0, 100);
      });
    },
    onToxicity: (p) => setTox((prev) => [...prev.slice(-59), p]),
    onVoice: (v) => setVoice(v),
    onHardware: (h) => setTank((prev) => (prev ? { ...prev, hardware: h as HardwareState } : prev)),
  });

  const resolveVoice = async (action: "execute" | "cancel") => {
    setVoice(null);
    try { window.speechSynthesis?.cancel(); } catch { /* noop */ }
    await voiceResolve(action);
    if (action === "execute") playSfx("pump");
  };

  const on = !!tank?.system_on;

  // ── optimistic, low-latency control handlers ──
  const spike = async (cmd: { do?: number; ph?: number; temp_c?: number }) => {
    setTank((prev) => (prev ? {
      ...prev,
      telemetry: {
        ...prev.telemetry,
        is_override: true,
        ...(cmd.ph != null ? { ph_level: cmd.ph } : {}),
        ...(cmd.do != null ? { do_level: cmd.do } : {}),
        ...(cmd.temp_c != null ? { temp_c: cmd.temp_c } : {}),
        timestamp: new Date().toISOString(),
      },
      updated_at: new Date().toISOString(),
    } : prev));
    try { const s = await postChaos(cmd); setTank(s); } catch { /* noop */ }
  };

  const doReset = async () => {
    setNarrative([{ ts: new Date().toISOString(), level: "good", text: "System reset — monitoring resumed." }]);
    setTank((prev) => (prev ? {
      ...prev,
      fsm_state: "NORMAL",
      sensor_fault: false,
      hardware: { aerator: "STANDBY", feed_valve: "ACTIVE", feed_rate_pct: 100 },
      telemetry: prev.telemetry ? { ...prev.telemetry, is_override: false } : prev.telemetry,
      updated_at: new Date().toISOString(),
    } : prev));
    try { const s = await resetAll(); setTank(s); } catch { /* noop */ }
  };

  const power = async (turnOn: boolean) => {
    if (!turnOn) setNarrative([]); // stop ⇒ logs halt + clear
    try { const s = await setPower(turnOn); setTank(s); } catch { /* noop */ }
  };

  const overrideHW = async (device: "aerator" | "feed_valve", action: string) => {
    setTank((prev) => {
      if (!prev) return prev;
      const hw: HardwareState = { ...prev.hardware };
      if (device === "aerator") hw.aerator = action as HardwareState["aerator"];
      else {
        hw.feed_valve = action as HardwareState["feed_valve"];
        hw.feed_rate_pct = action === "LOCKED" ? 0 : 100;
      }
      return { ...prev, hardware: hw, updated_at: new Date().toISOString() };
    });
    playSfx(device === "aerator" ? "pump" : "valve");
    try { await hardwareOverride(device, action, undefined, "portal_manual"); } catch { /* noop */ }
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="mark">Aqua<b>Bro</b></span>
          <span className="tag">RAS site portal</span>
        </div>
        <span className="spacer" />
        <StatusPill tank={tank} telegram={telegram} />
        <span className="pill" title="Site electricity — live draw · cumulative consumed">
          <span className="led" />
          ⚡ {tank ? `${Math.round(tank.power_w)} W · ${tank.energy_wh.toFixed(1)} Wh` : "—"}
        </span>
        <span className="pill">
          <span className="dot-live">updated {ago(tank?.updated_at, now)}</span>
        </span>
      </header>

      <DemoBar powered={on} onPower={power} onSpike={spike} onReset={doReset} />

      {!on && (
        <div className="offline-banner">
          <span className="led" /> System offline — press <b>Start system</b> to resume monitoring and logs.
        </div>
      )}

      <div className={`grid ${on ? "" : "dim"}`}>
        <div className="col-8"><ActuatorSchematic state={tank} onOverride={overrideHW} disabled={!on} /></div>
        <div className="col-4"><VisionCard vision={tank?.vision ?? null} /></div>
        <div className="col-12"><Vitals state={tank} /></div>
        <div className="col-12"><NarrativeFeed lines={narrative} /></div>
      </div>

      {voice && <VoiceOverlay voice={voice} onResolve={resolveVoice} />}
    </div>
  );
}
