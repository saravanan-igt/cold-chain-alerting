"use client";
import { useState, useMemo } from "react";
import { Timestamp } from "@/components/atoms/Timestamp";
import { QueryFeedback } from "@/components/molecules/QueryFeedback";
import { FleetMetrics } from "@/components/organisms/FleetMetrics";
import { FleetTable } from "@/components/organisms/FleetTable";
import { IncidentList } from "@/components/organisms/IncidentList";
import { WorkspaceHeader } from "@/components/organisms/WorkspaceHeader";
import { WorkspaceNavigation } from "@/components/organisms/WorkspaceNavigation";
import { WorkspaceTemplate } from "@/components/templates/WorkspaceTemplate";
import { AiFleetBanner } from "@/components/organisms/AiFleetBanner";
import { CopilotController } from "@/features/copilot/CopilotController";
import { DemoScenarioController } from "@/features/demo/DemoScenarioController";
import { IncidentDetailController } from "@/features/incidents/IncidentDetailController";
import {
  INCIDENT_PAGE_SIZE,
  useGetAiStatusQuery,
  useGetAiFleetAssessmentQuery,
} from "@/services/coldchain-api";
import { historicalReference, selectFleetSummary } from "./selectors";
import { useDashboard } from "./useDashboard";
import styles from "./Dashboard.module.scss";

export function Dashboard({ onSignOut }: { onSignOut: () => void }) {
  const model = useDashboard();
  const [copilotOpen, setCopilotOpen] = useState(false);

  const { data: aiStatus } = useGetAiStatusQuery();
  const {
    data: aiAssessment,
    isFetching: aiScanning,
    refetch: rescanAi,
  } = useGetAiFleetAssessmentQuery();

  const assessmentsByTruck = useMemo(() => {
    if (!aiAssessment?.truck_assessments) return undefined;
    const map: Record<string, (typeof aiAssessment.truck_assessments)[0]> = {};
    for (const a of aiAssessment.truck_assessments) {
      map[a.truck_id] = a;
    }
    return map;
  }, [aiAssessment]);

  const historical = model.fleet ? historicalReference(model.fleet) : null;
  return (
    <WorkspaceTemplate
      accent={model.fleet?.accent}
      sidebar={<WorkspaceNavigation customer={model.fleet?.name} />}
      header={<WorkspaceHeader busy={model.busy} onSignOut={onSignOut} />}
      footer={
        <footer className={styles.footer}>
          <span>Coldline / Operations workspace</span>
          <span>
            Freshness checked: <Timestamp value={model.fleet?.as_of ?? null} />
          </span>
        </footer>
      }
    >
      <div className={styles.title}>
        <div>
          <p className={styles.eyebrow}>COLD CHAIN, CLEAR SIGNAL</p>
          <h1>
            Fleet overview<span>.</span>
          </h1>
          <p>Sustained excursions. One incident. The evidence to act.</p>
        </div>
        <span className={styles.dateLabel}>All observation times in UTC</span>
      </div>
      <QueryFeedback
        loading={model.fleetLoading}
        error={model.fleetError}
        onRetry={model.retryFleet}
      />
      {model.fleet?.demo_mode === "live_simulation" && (
        <div className={styles.history}>
          <strong>Live simulation</strong>
          <span>
            Synthetic sensor data with current timestamps. Samples every 10
            seconds; demo trigger 30 seconds and recovery 20 seconds. Use the
            scenario panel below to inject genuine or non-genuine patterns.
            Production rules are unchanged.
          </span>
        </div>
      )}
      {historical && (
        <div className={styles.history}>
          <strong>Historical telemetry</strong>
          <span>
            Latest observation: <Timestamp value={historical} />. Freshness is
            evaluated against the current server clock; these readings are not
            live fleet conditions.
          </span>
        </div>
      )}

      <AiFleetBanner
        status={aiStatus}
        assessment={aiAssessment}
        isScanning={aiScanning}
        onScan={rescanAi}
        onOpenCopilot={() => setCopilotOpen(true)}
      />

      {model.fleet && (
        <>
          <FleetMetrics summary={selectFleetSummary(model.fleet)} />
          <FleetTable
            trucks={model.fleet.trucks}
            assessments={assessmentsByTruck}
          />
          {model.fleet.demo_mode === "live_simulation" && (
            <DemoScenarioController trucks={model.fleet.trucks} />
          )}
        </>
      )}
      <IncidentList
        items={model.incidents}
        lifecycle={model.lifecycle}
        offset={model.offset}
        pageSize={INCIDENT_PAGE_SIZE}
        busy={model.incidentsBusy}
        error={model.incidentsError}
        onRetry={model.retryIncidents}
        onFilter={model.onFilter}
        onPage={model.onPage}
        onSelect={model.onSelect}
      />
      <IncidentDetailController />
      <CopilotController
        open={copilotOpen}
        onClose={() => setCopilotOpen(false)}
      />
    </WorkspaceTemplate>
  );
}
