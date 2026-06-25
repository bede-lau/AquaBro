import type { Severity } from "./types";

export type Cls = "ok" | "warn" | "crit";

export const doClass = (dox: number, fault = false): Cls =>
  fault || dox <= 1.5 ? "crit" : dox < 3.0 ? "warn" : "ok";
export const phClass = (ph: number): Cls => (ph >= 8.4 ? "crit" : ph > 8.0 ? "warn" : "ok");
export const tempClass = (t: number): Cls => (t >= 31 ? "crit" : t > 29 ? "warn" : "ok");

/** Ammonia (unionized NH3) safety — the primary fish-killer signal. */
export const nh3Class = (nh3: number, threshold = 0.05, toxic = false): Cls =>
  toxic || nh3 >= threshold ? "crit" : nh3 >= threshold * 0.7 ? "warn" : "ok";

export const sevClass = (s: Severity): Cls =>
  s === "CRITICAL" ? "crit" : s === "WARN" ? "warn" : "ok";

export const FSM_META: Record<string, { cls: Cls; label: string }> = {
  NORMAL: { cls: "ok", label: "All clear" },
  AT_RISK: { cls: "warn", label: "At risk" },
  CRITICAL: { cls: "crit", label: "Critical" },
  MITIGATING: { cls: "crit", label: "Mitigating" },
  RECOVERING: { cls: "warn", label: "Recovering" },
};

/** Plain-English fish-behaviour read from the vision activity index. */
export function activityLabel(a: number | undefined): string {
  if (a == null) return "—";
  if (a > 0.8) return "frantic";
  if (a > 0.55) return "active";
  if (a > 0.25) return "calm";
  return "still";
}

/** HH:MM local clock from an ISO timestamp. */
export function fmtClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
  } catch {
    return "";
  }
}

/** Relative "x s ago" for the last-updated stamp. */
export function ago(iso: string | undefined, nowMs: number): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((nowMs - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  return `${Math.round(s / 60)}m ago`;
}
