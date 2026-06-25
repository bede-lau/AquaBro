import type { TankState } from "../types";
import type { Cls } from "../util";
import { doClass, phClass, tempClass } from "../util";

const STATUS_STROKE: Record<Cls, string> = {
  ok: "var(--good)",
  warn: "var(--warn)",
  crit: "var(--crit)",
};

/** A sensor probe on the tank wall. The value reads to the LEFT (over the
 *  tank water) so the sensor cables running right never cross the number. */
function Probe({
  x, y, label, value, cls,
}: { x: number; y: number; label: string; value: string; cls: Cls }) {
  return (
    <g>
      <circle className="node-fill" cx={x} cy={y} r={15} style={{ stroke: STATUS_STROKE[cls] }} />
      <text className="node-sub" x={x} y={y + 3} textAnchor="middle">{label}</text>
      <text className="node-value" x={x - 19} y={y + 4} textAnchor="end">{value}</text>
    </g>
  );
}

interface Props {
  state: TankState | null;
  onOverride: (device: "aerator" | "feed_valve", action: string) => void;
  disabled?: boolean;
}

/**
 * The control loop, drawn: tank → sensor probes → controller → cables out to
 * the two output actuators (aerator pump, feed valve). Live state colours the
 * cables; the pump spins when running. Manual override buttons sit beneath.
 */
export default function ActuatorSchematic({ state, onOverride, disabled }: Props) {
  const t = state?.telemetry;
  const hw = state?.hardware;
  const aeratorOn = hw?.aerator === "ACTIVE";
  const feedLocked = hw?.feed_valve === "LOCKED";

  return (
    <div className="card">
      <div className="card-h">
        <span className="title">Control loop</span>
        <span className="meta">sense → decide → actuate</span>
      </div>

      <div className="schematic-wrap">
        <svg viewBox="0 0 780 330" role="img" aria-label="Tank control loop diagram">
          {/* ── tank ── */}
          <text className="node-label" x="99" y="40" textAnchor="middle">TANK-01</text>
          <rect className="tank-water" x="24" y="52" width="150" height="240" rx="14" />
          <line x1="24" y1="92" x2="174" y2="92" stroke="var(--water)" strokeWidth="1.4" opacity="0.6" />
          <g fill="var(--water-deep)" opacity="0.45">
            <ellipse cx="70" cy="150" rx="13" ry="5" />
            <ellipse cx="120" cy="210" rx="13" ry="5" />
            <ellipse cx="88" cy="255" rx="11" ry="4" />
          </g>
          <text className="node-sub" x="99" y="310" textAnchor="middle">
            {state?.vision ? `${state.vision.fish_count} fish` : "—"}
          </text>

          {/* ── sensor probes on the tank wall ── */}
          <Probe x={174} y={130} label="O₂" value={t ? t.do_level.toFixed(1) : "--"} cls={t ? doClass(t.do_level, state?.sensor_fault) : "ok"} />
          <Probe x={174} y={185} label="pH" value={t ? t.ph_level.toFixed(2) : "--"} cls={t ? phClass(t.ph_level) : "ok"} />
          <Probe x={174} y={240} label="°C" value={t ? t.temp_c.toFixed(0) : "--"} cls={t ? tempClass(t.temp_c) : "ok"} />

          {/* probes → controller (sensors always reading) */}
          <path className="cable live" d="M 189 130 C 245 130, 250 165, 305 165" />
          <path className="cable live" d="M 189 185 C 250 185, 250 175, 305 175" />
          <path className="cable live" d="M 189 240 C 250 240, 250 185, 305 185" />

          {/* ── controller ── */}
          <rect className="controller-box" x="305" y="120" width="150" height="110" rx="10" />
          <text className="node-label" x="380" y="150" textAnchor="middle">AquaBro</text>
          <text className="node-sub" x="380" y="168" textAnchor="middle">controller</text>
          <circle cx="380" cy="195" r="5" fill={aeratorOn || feedLocked ? "var(--water)" : "var(--ink-4)"} />
          <text className="node-sub" x="392" y="199">{state?.fsm_state ?? "—"}</text>

          {/* controller → actuators */}
          <path className={`cable ${aeratorOn ? "live" : "idle"}`} d="M 455 150 C 520 150, 540 120, 600 120" />
          <path className={`cable ${!feedLocked ? "live feed" : "idle"}`} d="M 455 200 C 520 200, 540 250, 600 250" />

          {/* ── aerator pump (spins when ACTIVE) ── */}
          <g>
            <circle className={`actuator-body ${aeratorOn ? "on" : ""}`} cx="640" cy="120" r="30" />
            <g className={`spin ${aeratorOn ? "on" : ""}`} style={{ transformOrigin: "640px 120px" }}>
              <rect x="637" y="92" width="6" height="56" rx="3" fill={aeratorOn ? "var(--water)" : "var(--ink-4)"} />
              <rect x="612" y="117" width="56" height="6" rx="3" fill={aeratorOn ? "var(--water)" : "var(--ink-4)"} />
            </g>
            <text className="node-label" x="640" y="172" textAnchor="middle">Aerator</text>
            <text className="node-sub" x="640" y="187" textAnchor="middle" fill={aeratorOn ? "var(--water-deep)" : "var(--ink-3)"}>
              {aeratorOn ? "running" : "standby"}
            </text>
          </g>

          {/* ── feed valve ── */}
          <g>
            <circle className={`actuator-body ${!feedLocked ? "feed-on" : ""}`} cx="640" cy="250" r="30" />
            <g fill={feedLocked ? "var(--ink-4)" : "var(--feed)"}>
              <circle cx="640" cy="250" r="13" fill="none" stroke={feedLocked ? "var(--ink-4)" : "var(--feed)"} strokeWidth="3" />
              <rect x="636" y="232" width="8" height="14" rx="2" />
              <rect x="636" y="254" width="8" height="14" rx="2" />
            </g>
            <text className="node-label" x="640" y="300" textAnchor="middle">Feed valve</text>
            <text className="node-sub" x="640" y="315" textAnchor="middle" fill={!feedLocked ? "oklch(0.46 0.13 72)" : "var(--ink-3)"}>
              {feedLocked ? "held" : `${Math.round(hw?.feed_rate_pct ?? 0)}% open`}
            </text>
          </g>
        </svg>
      </div>

      <div className="schematic-actions">
        <button
          className={`btn ${aeratorOn ? "ghost" : "primary"}`}
          disabled={disabled}
          onClick={() => onOverride("aerator", aeratorOn ? "STANDBY" : "ACTIVE")}
        >
          {aeratorOn ? "Stop aerator" : "Start aerator"}
        </button>
        <button
          className={`btn ${feedLocked ? "primary" : "feed"}`}
          disabled={disabled}
          onClick={() => onOverride("feed_valve", feedLocked ? "ACTIVE" : "LOCKED")}
        >
          {feedLocked ? "Resume feed" : "Hold feed"}
        </button>
      </div>
    </div>
  );
}
