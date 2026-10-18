import type { Fleet, IncidentDetail } from "@/types/domain";
export const rule = {
  threshold_c: 8,
  sustained_minutes: 10,
  max_gap_minutes: 5,
  recovery_minutes: 5,
  version: "test-v1",
};
export const nimbus: Fleet = {
  tenant: "nimbus",
  name: "Nimbus Freight",
  accent: "#17675e",
  as_of: "2026-10-17T12:00:00Z",
  trucks: [
    {
      id: "T-01",
      device_id: "sensor-T-01",
      temperature_c: 7,
      last_observation_at: "2026-07-20T08:50:00Z",
      freshness: "stale",
      status: "normal",
      late_count: 1,
      rule,
    },
  ],
};
export const alpine: Fleet = {
  tenant: "alpine",
  name: "Alpine Produce",
  accent: "#505eaa",
  as_of: nimbus.as_of,
  trucks: [],
};
export const detail: IncidentDetail = {
  id: "incident-1",
  truck_id: "T-01",
  lifecycle: "recovered",
  rule,
  excursion_started_at: "2026-07-20T08:10:00Z",
  qualified_at: "2026-07-20T08:20:00Z",
  recovery_confirmed_at: "2026-07-20T08:50:00Z",
  explanation: "Three warm observations qualified the incident.",
  evidence_count: 4,
  observed_max_c: 9,
  supported_warm_seconds: 600,
  telemetry_gap_count: 1,
  evidence_limit: 100,
  evidence_offset: 0,
  evidence: [
    { timestamp: "2026-07-20T08:10:00Z", temperature_c: 9 },
    { timestamp: "2026-07-20T08:15:00Z", temperature_c: 9 },
    { timestamp: "2026-07-20T08:20:00Z", temperature_c: 9 },
    { timestamp: "2026-07-20T08:50:00Z", temperature_c: 7 },
  ],
};
