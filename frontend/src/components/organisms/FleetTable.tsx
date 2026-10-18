import Badge from "react-bootstrap/Badge";
import Table from "react-bootstrap/Table";
import type { Truck, AiTruckAssessment } from "@/types/domain";
import { StatusBadge } from "@/components/atoms/StatusBadge";
import { Timestamp } from "@/components/atoms/Timestamp";
import { Panel } from "@/components/molecules/Panel";
import { EmptyState } from "@/components/molecules/EmptyState";
import styles from "./FleetTable.module.scss";

export function FleetTable({
  trucks,
  assessments,
}: {
  trucks: Truck[];
  assessments?: Record<string, AiTruckAssessment>;
}) {
  return (
    <Panel
      id="fleet"
      title="Fleet watch"
      description="Latest accepted observation and Claude AI thermal diagnosis for each truck"
      action={
        <Badge bg="light" text="dark">
          {trucks.length} trucks
        </Badge>
      }
    >
      {trucks.length ? (
        <div className="table-responsive">
          <Table className={styles.table}>
            <thead>
              <tr>
                <th>Truck / stream</th>
                <th>Last temperature</th>
                <th>Last observation</th>
                <th>Telemetry</th>
                <th>Detector</th>
                <th>Rule</th>
                <th>Claude AI Diagnosis</th>
              </tr>
            </thead>
            <tbody>
              {trucks.map((truck) => {
                const ai = assessments?.[truck.id];
                return (
                  <tr key={truck.id}>
                    <td>
                      <strong>{truck.id}</strong>
                      <small>Authoritative stream</small>
                    </td>
                    <td className={styles.temperature}>
                      {truck.temperature_c === null
                        ? "—"
                        : `${truck.temperature_c.toFixed(1)} °C`}
                    </td>
                    <td>
                      <Timestamp value={truck.last_observation_at} />
                    </td>
                    <td>
                      <StatusBadge value={truck.freshness} />
                    </td>
                    <td>
                      <StatusBadge value={truck.status} />
                    </td>
                    <td>
                      &gt; {truck.rule.threshold_c} °C /{" "}
                      {truck.rule.sustained_minutes} min
                    </td>
                    <td>
                      {ai ? (
                        <div>
                          <Badge
                            bg={
                              ai.ai_severity === "CRITICAL"
                                ? "danger"
                                : ai.ai_severity === "WARNING"
                                  ? "warning"
                                  : "success"
                            }
                          >
                            {ai.ai_category.replace(/_/g, " ")}
                          </Badge>
                          <div
                            style={{
                              fontSize: "0.75rem",
                              color: "#4a5568",
                              marginTop: "3px",
                              lineHeight: "1.25",
                            }}
                          >
                            {ai.summary}
                          </div>
                        </div>
                      ) : (
                        <span style={{ color: "#a0aec0", fontSize: "0.8rem" }}>
                          Nominal
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </div>
      ) : (
        <EmptyState title="No trucks are registered for this customer." />
      )}
    </Panel>
  );
}
