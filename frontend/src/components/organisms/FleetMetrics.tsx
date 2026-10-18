import { MetricCard } from "@/components/molecules/MetricCard";
import styles from "./FleetMetrics.module.scss";
export interface FleetSummary {
  monitored: number;
  active: number;
  unavailable: number;
  late: number;
}
export function FleetMetrics({ summary }: { summary: FleetSummary }) {
  return (
    <section className={styles.metrics} aria-label="Fleet metrics">
      <MetricCard
        label="Trucks monitored"
        value={summary.monitored}
        description="Registered to this customer"
      />
      <MetricCard
        label="Open incidents"
        value={summary.active}
        description="Awaiting observed recovery"
        highlighted
      />
      <MetricCard
        label="Telemetry unavailable"
        value={summary.unavailable}
        description="Stale or never observed"
      />
      <MetricCard
        label="Late readings"
        value={summary.late}
        description="Stored without changing live state"
      />
    </section>
  );
}
