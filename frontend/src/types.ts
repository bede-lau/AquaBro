// Mirror of backend app/schemas.py (subset the UI consumes).

export type Severity = "INFO" | "WARN" | "CRITICAL";

export interface Telemetry {
  timestamp: string;
  tank_id: string;
  do_level: number;
  ph_level: number;
  temp_c: number;
  is_override: boolean;
}

export interface VisionAssessment {
  activity_index: number;
  lethargy: boolean;
  surface_piping: boolean;
  fish_count: number;
  mean_depth_norm: number;
  fault: boolean;
}

export interface AmbientContext {
  air_temp_c: number | null;
  humidity_pct: number | null;
  description: string;
  recent_feed_mass_g: number;
  source: "openweather" | "mock";
}

export interface ToxicityAssessment {
  tan: number;
  ph: number;
  temp_c: number;
  pka: number;
  nh3_fraction: number;
  nh3_mg_l: number;
  threshold_mg_l: number;
  toxic: boolean;
  slope_per_min: number;
}

export interface RiskAssessment {
  name: string;
  severity: Severity;
  active: boolean;
  evidence: string;
  mitigations: string[];
}

export interface HardwareState {
  aerator: "STANDBY" | "ACTIVE";
  feed_valve: "ACTIVE" | "LOCKED";
  feed_rate_pct: number;
}

export interface TankState {
  fsm_state: string;
  telemetry: Telemetry;
  vision: VisionAssessment | null;
  context: AmbientContext | null;
  toxicity: ToxicityAssessment | null;
  risks: RiskAssessment[];
  hardware: HardwareState;
  sensor_fault: boolean;
  system_on: boolean;
  power_w: number;
  energy_wh: number;
  updated_at: string;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: "Sensor" | "Parameter" | "Risk" | "Hardware";
  state: string;
}
export interface GraphEdge { src: string; dst: string; rel: string; }
export interface CausalGraph { nodes: GraphNode[]; edges: GraphEdge[]; }

export interface ReasoningLine { ts: string; agent: string; message: string; }
export interface ToxicityPoint { t: string; nh3: number; threshold: number; }

export type NarrativeLevel = "info" | "warn" | "critical" | "good";
export interface NarrativeLine { ts: string; level: NarrativeLevel; text: string; }

export interface VoiceEvent {
  provider: string;
  system_prompt: string;
  agent_id: string;
  webhook_url: string;
}
