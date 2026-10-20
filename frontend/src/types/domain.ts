/** Transport contracts shared by data services and presentation components. */
export interface Rule {
  threshold_c: number;
  sustained_minutes: number;
  max_gap_minutes: number;
  recovery_minutes: number;
  version?: string;
}
export type Lifecycle = "open" | "recovered";
export type LifecycleFilter = Lifecycle | "";
export type Freshness = "fresh" | "stale" | "never_seen" | "future";
export type DetectorStatus = "open" | "pending" | "normal" | "unknown";
export interface Truck {
  id: string;
  device_id: string;
  temperature_c: number | null;
  last_observation_at: string | null;
  freshness: Freshness;
  status: DetectorStatus;
  late_count: number;
  rule: Rule;
}
export interface Fleet {
  demo_mode?: "live_simulation" | null;
  tenant: string;
  name: string;
  accent: string;
  as_of: string;
  trucks: Truck[];
}
export interface Incident {
  id: string;
  truck_id: string;
  lifecycle: Lifecycle;
  excursion_started_at: string;
  qualified_at: string;
  recovery_confirmed_at: string | null;
  rule: Rule;
  explanation: string;
  evidence_count: number;
  observed_max_c: number;
  supported_warm_seconds: number;
  telemetry_gap_count: number;
  acknowledgement?: Acknowledgement | null;
  ai_evaluation?: AiAlertEvaluation;
}
export interface Acknowledgement {
  acknowledged_by: string;
  acknowledged_at: string;
  note: string | null;
}
export interface TimelineEvent {
  kind: "opened" | "recovered" | "acknowledged" | "escalated" | string;
  actor: string;
  at: string;
  details: Record<string, unknown>;
}
export type DeliveryStatus = "pending" | "sending" | "delivered" | "dead";
export interface NotificationDelivery {
  id: number;
  incident_id: string;
  event: string;
  event_key: string;
  channel_id: string;
  channel_type: string;
  status: DeliveryStatus;
  attempts: number;
  next_attempt_at: string;
  created_at: string;
  delivered_at: string | null;
  last_error: string | null;
}
export interface DemoScenarioDefinition {
  id: string;
  label: string;
  genuine: boolean;
  expected_incident: boolean;
  description: string;
  duration_seconds: number;
}
export interface DemoScenarioRun {
  id: number;
  truck_id: string;
  scenario: string;
  label: string;
  genuine: boolean | null;
  expected_incident: boolean | null;
  status: "queued" | "running" | "completed" | "cancelled";
  requested_by: string;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
  observed_incident_id: string | null;
  steps: (number | null)[];
}
export interface DemoScenarios {
  sample_seconds: number;
  catalogue: DemoScenarioDefinition[];
  runs: DemoScenarioRun[];
}
export interface Evidence {
  timestamp: string;
  temperature_c: number;
}
export interface IncidentDetail extends Incident {
  evidence: Evidence[];
  evidence_limit: number;
  evidence_offset: number;
  timeline?: TimelineEvent[];
  notifications?: NotificationDelivery[];
  ai_triage?: AiIncidentTriage;
}
export interface IncidentPage {
  items: Incident[];
  limit: number;
  offset: number;
}

export interface AiAlertEvaluation {
  truck_id: string;
  is_real_alert: boolean;
  alert_category: string;
  severity: "CRITICAL" | "HIGH" | "WARNING" | "BENIGN" | "LOW";
  confidence_score: number | null;
  root_cause_hypothesis: string;
  thermal_inertia_analysis: string;
  cargo_spoilage_risk: string;
  suppressed_as_benign: boolean;
  suppress_reason?: string | null;
  recommended_sop_action: string;
  one_line_summary: string;
}

export interface AiIncidentTriage {
  incident_id: string;
  truck_id: string;
  executive_summary: string;
  thermal_forensics: {
    excursion_started_at: string;
    qualified_at: string;
    peak_temperature_c: number;
    supported_warm_minutes: number;
    accumulated_degree_minutes: number | null;
    telemetry_gaps_encountered: number;
    recovery_status: string;
  };
  cargo_impact_assessment: {
    risk_level: string;
    shelf_life_impact: string;
    stability_budget_exceeded: boolean | null;
    inspection_requirement: string;
  };
  sop_action_checklist: string[];
  driver_dispatch_script: string;
}

export interface AiTruckAssessment {
  truck_id: string;
  status: string;
  temperature_c: number | null;
  ai_severity: "CRITICAL" | "HIGH" | "WARNING" | "BENIGN" | "LOW";
  ai_category: string;
  is_real_alert: boolean;
  confidence_score: number | null;
  summary: string;
  recommended_action: string;
}

export interface AiFleetAssessment {
  tenant: string;
  fleet_health_score: number | null;
  overall_condition:
    "NO_OPEN_INCIDENTS" | "ACTIVE_INCIDENTS" | "DATA_QUALITY_REVIEW";
  active_critical_alerts: number;
  predictive_warnings: number;
  normal_operating_trucks: number;
  executive_dispatch_summary: string;
  key_action_items: string[];
  truck_assessments: AiTruckAssessment[];
}

export interface AiChatResponse {
  reply: string;
  relevant_trucks: string[];
  suggested_actions: string[];
}

export interface OperationsMessage {
  role: "user" | "assistant";
  content: string;
  relevantTrucks?: string[];
  suggestedActions?: string[];
}

export interface AiStatus {
  provider: string;
  model: string;
  mode: string;
  has_api_key: boolean;
  capabilities: string[];
}
