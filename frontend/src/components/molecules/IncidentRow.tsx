import type { Incident } from "@/types/domain";
import { StatusBadge } from "@/components/atoms/StatusBadge";
import { Timestamp } from "@/components/atoms/Timestamp";
import styles from "./IncidentRow.module.scss";
export function IncidentRow({
  incident,
  onSelect,
}: {
  incident: Incident;
  onSelect: (id: string) => void;
}) {
  return (
    <button className={styles.row} onClick={() => onSelect(incident.id)}>
      <span
        aria-hidden="true"
        className={`${styles.icon} ${incident.lifecycle === "recovered" ? styles.recovered : ""}`}
      >
        {incident.lifecycle === "recovered" ? "✓" : "!"}
      </span>
      <span className={styles.summary}>
        <strong>
          {incident.truck_id} <span>Temperature excursion</span>
        </strong>
        <span className={styles.description}>
          Above {incident.rule.threshold_c} °C · qualified{" "}
          <Timestamp value={incident.qualified_at} />
        </span>
        {incident.acknowledgement ? (
          <span className={styles.owner}>
            Acknowledged by {incident.acknowledgement.acknowledged_by}
          </span>
        ) : (
          incident.acknowledgement === null && (
            <span className={`${styles.owner} ${styles.unowned}`}>
              Unacknowledged
            </span>
          )
        )}
      </span>
      <StatusBadge value={incident.lifecycle} />
      <span className={styles.peak}>
        {incident.observed_max_c.toFixed(1)} °C<small>observed peak</small>
      </span>
      <span aria-hidden="true">↗</span>
    </button>
  );
}
