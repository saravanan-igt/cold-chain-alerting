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
  const isLive = status?.has_api_key ?? false;
  const healthScore = assessment?.fleet_health_score ?? 85;
  const condition = assessment?.overall_condition ?? "OPTIMAL";

  const conditionClass =
    condition === "CRITICAL_ATTENTION_NEEDED"
      ? styles.criticalText
      : condition === "ELEVATED_WATCH"
        ? styles.warningText
        : styles.optimalText;

  return (
    <section className={styles.banner} aria-label="Claude AI Fleet Advisory">
      <div className={styles.headerRow}>
        <div className={styles.titleGroup}>
          <h2>
            {status?.provider === "gemini"
              ? "Google Gemini AI Fleet Intelligence"
              : status?.provider === "anthropic"
                ? "Anthropic Claude AI Fleet Intelligence"
                : "Coldline Multi-AI Fleet Intelligence"}
          </h2>
          <span className={isLive ? styles.badgeLive : styles.badgeSim}>
            {status?.provider?.toUpperCase() ?? "AI"} · {status?.model ?? "engine"} ·{" "}
            {isLive ? "Live API" : "Cognitive Physics"}
          </span>
        </div>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.copilotButton}
            onClick={onOpenCopilot}
            aria-label="Open AI Operations Copilot"
          >
            Ask AI Copilot
          </button>
          <button
            type="button"
            className={styles.scanButton}
            onClick={onScan}
            disabled={isScanning}
          >
            {isScanning ? "Evaluating Fleet..." : "Run AI Risk Scan"}
          </button>
        </div>
      </div>

      {assessment && (
        <>
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <span className={labelClass("health")}>Fleet Health Score</span>
              <div className={`${styles.value} ${conditionClass}`}>
                {healthScore}/100
              </div>
              <div className={styles.desc}>
                {condition.replace(/_/g, " ")}
              </div>
            </div>

            <div className={styles.statCard}>
              <span className={styles.label}>Real Excursions</span>
              <div className={`${styles.value} ${assessment.active_critical_alerts > 0 ? styles.criticalText : ""}`}>
                {assessment.active_critical_alerts}
              </div>
              <div className={styles.desc}>Verified Critical Alerts</div>
            </div>

            <div className={styles.statCard}>
              <span className={styles.label}>Predictive Warnings</span>
              <div className={`${styles.value} ${assessment.predictive_warnings > 0 ? styles.warningText : ""}`}>
                {assessment.predictive_warnings}
              </div>
              <div className={styles.desc}>Sub-threshold Drifts</div>
            </div>

            <div className={styles.statCard}>
              <span className={styles.label}>Nominal Trucks</span>
              <div className={`${styles.value} ${styles.optimalText}`}>
                {assessment.normal_operating_trucks}
              </div>
              <div className={styles.desc}>Safe Core Thermal Mass</div>
            </div>
          </div>

          <p className={styles.executiveSummary}>
            <strong>AI Dispatch Briefing:</strong> {assessment.executive_dispatch_summary}
          </p>
        </>
      )}
    </section>
  );
}

function labelClass(name: string): string {
  return styles.label;
}
