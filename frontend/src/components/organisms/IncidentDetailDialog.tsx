import Modal from "react-bootstrap/Modal";
import Table from "react-bootstrap/Table";
import type { IncidentDetail } from "@/types/domain";
import { StatusBadge } from "@/components/atoms/StatusBadge";
import { Timestamp } from "@/components/atoms/Timestamp";
import { Pagination } from "@/components/molecules/Pagination";
import { QueryFeedback } from "@/components/molecules/QueryFeedback";
import { EvidenceChart } from "./EvidenceChart";
import styles from "./IncidentDetailDialog.module.scss";

export function IncidentDetailDialog({
  detail,
  open,
  busy,
  error,
  offset,
  pageSize,
  onClose,
  onPage,
  onRetry,
}: {
  detail?: IncidentDetail;
  open: boolean;
  busy: boolean;
  error?: string;
  offset: number;
  pageSize: number;
  onClose: () => void;
  onPage: (offset: number) => void;
  onRetry: () => void;
}) {
  return (
    <Modal
      show={open}
      onHide={onClose}
      size="lg"
      centered
      aria-labelledby="incident-detail-title"
    >
      <Modal.Header closeButton>
        <Modal.Title id="incident-detail-title">
          {detail?.truck_id ?? "Incident"} · Decision evidence
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className={styles.body}>
        <QueryFeedback
          loading={!detail && busy}
          error={error}
          onRetry={onRetry}
        />
        {detail && (
          <>
            <StatusBadge value={detail.lifecycle} />
            <p className={styles.explanation}>{detail.explanation}</p>
            <dl className={styles.facts}>
              <div>
                <dt>Excursion began</dt>
                <dd>
                  <Timestamp value={detail.excursion_started_at} />
                </dd>
              </div>
              <div>
                <dt>Recovery confirmed</dt>
                <dd>
                  {detail.recovery_confirmed_at ? (
                    <Timestamp value={detail.recovery_confirmed_at} />
                  ) : (
                    "Not yet confirmed"
                  )}
                </dd>
              </div>
              <div>
                <dt>Supported warm intervals (sum)</dt>
                <dd>{detail.supported_warm_seconds / 60} minutes</dd>
              </div>
              <div>
                <dt>Gaps after opening</dt>
                <dd>{detail.telemetry_gap_count}</dd>
              </div>
            </dl>

            {detail.ai_evaluation && (
              <div className={styles.aiPanel}>
                <h3>
                  <span>Claude AI Diagnostic Verdict</span>
                  <span
                    className={
                      detail.ai_evaluation.is_real_alert
                        ? styles.aiBadgeReal
                        : styles.aiBadgeBenign
                    }
                  >
                    {detail.ai_evaluation.is_real_alert
                      ? "Genuine Alert"
                      : "Benign Event"}{" "}
                    ({Math.round(detail.ai_evaluation.confidence_score * 100)}%)
                  </span>
                </h3>
                <p style={{ margin: "8px 0", fontSize: "13px" }}>
                  <strong>Classification:</strong>{" "}
                  {detail.ai_evaluation.alert_category.replace(/_/g, " ")} ·{" "}
                  <strong>Cargo Spoilage Risk:</strong>{" "}
                  {detail.ai_evaluation.cargo_spoilage_risk}
                </p>
                <p style={{ margin: "6px 0", fontSize: "12px", color: "#334155" }}>
                  <strong>Root Cause:</strong>{" "}
                  {detail.ai_evaluation.root_cause_hypothesis}
                </p>
                <p style={{ margin: "6px 0", fontSize: "12px", color: "#334155" }}>
                  <strong>Thermal Inertia:</strong>{" "}
                  {detail.ai_evaluation.thermal_inertia_analysis}
                </p>

                {detail.ai_triage && (
                  <>
                    <h4
                      style={{
                        fontSize: "13px",
                        fontWeight: 700,
                        margin: "14px 0 6px 0",
                        color: "#17675e",
                      }}
                    >
                      Driver Dispatch Communication Script
                    </h4>
                    <div className={styles.scriptBox}>
                      {detail.ai_triage.driver_dispatch_script}
                    </div>
                    <button
                      type="button"
                      className={styles.copyBtn}
                      onClick={() => {
                        if (detail.ai_triage?.driver_dispatch_script) {
                          navigator.clipboard?.writeText(
                            detail.ai_triage.driver_dispatch_script
                          );
                        }
                      }}
                    >
                      Copy Driver Script
                    </button>

                    <h4
                      style={{
                        fontSize: "13px",
                        fontWeight: 700,
                        margin: "14px 0 6px 0",
                        color: "#17675e",
                      }}
                    >
                      Recommended Operations SOP Actions
                    </h4>
                    <ul className={styles.sopList}>
                      {detail.ai_triage.sop_action_checklist.map((step, sIdx) => (
                        <li key={sIdx}>{step}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}

            <h3>Observed temperature</h3>
            <EvidenceChart detail={detail} />
            <p className={styles.note}>
              Points show observations. Lines are omitted across gaps longer
              than {detail.rule.max_gap_minutes} minutes. Threshold:{" "}
              {detail.rule.threshold_c} °C. Rule version: {detail.rule.version}.
            </p>
            <Table size="sm">
              <thead>
                <tr>
                  <th>Observation (UTC)</th>
                  <th>Temperature</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {detail.evidence.map((row) => (
                  <tr key={row.timestamp}>
                    <td>
                      <Timestamp value={row.timestamp} />
                    </td>
                    <td>{row.temperature_c.toFixed(1)} °C</td>
                    <td>
                      {row.timestamp === detail.qualified_at
                        ? "Incident qualified"
                        : row.timestamp === detail.recovery_confirmed_at
                          ? "Recovery confirmed"
                          : row.temperature_c > detail.rule.threshold_c
                            ? "Above threshold"
                            : "At or below threshold"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
        <Pagination
          label="Evidence"
          offset={offset}
          count={detail?.evidence.length ?? 0}
          pageSize={pageSize}
          total={detail?.evidence_count}
          busy={busy || !!error}
          onChange={onPage}
        />
      </Modal.Body>
    </Modal>
  );
}
