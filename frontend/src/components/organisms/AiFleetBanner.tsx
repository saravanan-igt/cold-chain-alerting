"use client";

import React from "react";
import type { AiFleetAssessment, AiStatus } from "@/types/domain";
import styles from "./AiFleetBanner.module.scss";

interface AiFleetBannerProps {
  status?: AiStatus;
  assessment?: AiFleetAssessment;
  isScanning: boolean;
  onScan: () => void;
  onOpenCopilot: () => void;
}

export function AiFleetBanner({
  status,
  assessment,
  isScanning,
  onScan,
  onOpenCopilot,
}: AiFleetBannerProps) {
  const condition = assessment?.overall_condition ?? "NO_OPEN_INCIDENTS";

  const conditionClass =
    condition === "ACTIVE_INCIDENTS"
      ? styles.criticalText
      : condition === "DATA_QUALITY_REVIEW"
        ? styles.warningText
        : styles.optimalText;

  return (
    <section className={styles.banner} aria-label="Rules-based fleet summary">
      <div className={styles.headerRow}>
        <div className={styles.titleGroup}>
          <h2>Fleet rule summary</h2>
          <span className={styles.badgeSim}>
            {status?.provider ?? "deterministic_rules"} · no external model calls
          </span>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.copilotButton}
            onClick={onOpenCopilot}
            aria-label="Open operations assistant"
          >
            Ask operations assistant
          </button>
          <button
            type="button"
            className={styles.scanButton}
            onClick={onScan}
            disabled={isScanning}
          >
            {isScanning ? "Refreshing summary..." : "Refresh fleet summary"}
          </button>
        </div>
      </div>

      {assessment && (
        <>
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <span className={styles.label}>Registered trucks</span>
              <div className={`${styles.value} ${conditionClass}`}>
                {assessment.truck_assessments?.length ?? 0}
              </div>
              <div className={styles.desc}>{condition.replace(/_/g, " ")}</div>
              <div className={styles.desc}>No cargo-safety score is calculated</div>
            </div>

            <div className={styles.statCard}>
              <span className={styles.label}>Open incidents</span>
              <div className={`${styles.value} ${assessment.active_critical_alerts > 0 ? styles.criticalText : ""}`}>
                {assessment.active_critical_alerts}
              </div>
              <div className={styles.desc}>Detector state</div>
            </div>

            <div className={styles.statCard}>
              <span className={styles.label}>Pending / telemetry review</span>
              <div className={`${styles.value} ${assessment.predictive_warnings > 0 ? styles.warningText : ""}`}>
                {assessment.predictive_warnings}
              </div>
              <div className={styles.desc}>Pending candidates or stale data</div>
            </div>

            <div className={styles.statCard}>
              <span className={styles.label}>Fresh without open/pending</span>
              <div className={`${styles.value} ${styles.optimalText}`}>
                {assessment.normal_operating_trucks}
              </div>
              <div className={styles.desc}>Not a cargo disposition assessment</div>
            </div>
          </div>

          <p className={styles.executiveSummary}>
            <strong>Telemetry summary:</strong> {assessment.executive_dispatch_summary}
          </p>
        </>
      )}
    </section>
  );
}
