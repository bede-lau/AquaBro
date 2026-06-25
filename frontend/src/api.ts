import type { TankState } from "./types";

const BASE = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const getState = () => fetch(`${BASE}/state`).then(json<TankState>);

export const getTelegramStatus = () =>
  fetch(`${BASE}/telegram/status`).then(json<TelegramStatus>).catch(() => null);

export interface TelegramStatus {
  enabled: boolean;
  configured: boolean;
  ready: boolean;
  llm: boolean;
  model: string;
  chat_id: string;
  polling: boolean;
}

export async function postChaos(cmd: {
  do?: number; ph?: number; temp_c?: number; sensor_fault?: boolean;
}): Promise<TankState> {
  return fetch(`${BASE}/chaos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cmd),
  }).then(json<TankState>);
}

export const resetAll = () =>
  fetch(`${BASE}/chaos/reset`, { method: "POST" }).then(json<TankState>);

/** Master power — on tracks + logs; off halts both. */
export const setPower = (on: boolean) =>
  fetch(`${BASE}/system/power`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ on }),
  }).then(json<TankState>);

export const setNarrator = (run: boolean) =>
  fetch(`${BASE}/chaos/narrator`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run }),
  }).then((r) => r.json());

/** Drive an output device. Mirrors POST /api/hardware/override. */
export async function hardwareOverride(
  device: "aerator" | "feed_valve",
  action: string,
  rate_pct?: number,
  reason?: string
) {
  return fetch(`${BASE}/hardware/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device, action, rate_pct, reason }),
  }).then(json);
}

export const voiceResolve = (action: string) =>
  fetch(`${BASE}/voice/resolve?action=${encodeURIComponent(action)}`, {
    method: "POST",
  }).then((r) => r.json());

/** Best-effort SFX (ElevenLabs-generated assets per spec §6.3). No-ops if absent. */
export function playSfx(name: "pump" | "valve") {
  try {
    const a = new Audio(`/sfx/${name}.mp3`);
    a.volume = 0.7;
    a.play().catch(() => {});
  } catch {
    /* asset missing — silent */
  }
}
