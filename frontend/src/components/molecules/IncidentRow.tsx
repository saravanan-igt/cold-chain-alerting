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
          {incident.ai_evaluation && (
            <span
              style={{
                marginLeft: "8px",
                padding: "2px 6px",
                borderRadius: "4px",
                fontSize: "0.75rem",
                fontWeight: 600,
                background: incident.ai_evaluation.is_real_alert ? "#fef2f2" : "#f0fdf4",
                color: incident.ai_evaluation.is_real_alert ? "#b91c1c" : "#15803d",
                border: `1px solid ${incident.ai_evaluation.is_real_alert ? "#fca5a5" : "#86efac"}`,
              }}
            >
              AI: {incident.ai_evaluation.is_real_alert ? "Genuine Alert" : "Benign"} (
              {Math.round(incident.ai_evaluation.confidence_score * 100)}%)
            </span>
          )}
        </span>
      </span>
      <StatusBadge value={incident.lifecycle} />
      <span className={styles.peak}>
        {incident.observed_max_c.toFixed(1)} °C<small>observed peak</small>
      </span>
      <span aria-hidden="true">↗</span>
    </button>
  );
}
