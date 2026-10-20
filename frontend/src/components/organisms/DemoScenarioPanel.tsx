"use client";
import { useState } from "react";
import type {
  DemoScenarioDefinition,
  DemoScenarioRun,
  DemoScenarios,
  Truck,
} from "@/types/domain";
import { Timestamp } from "@/components/atoms/Timestamp";
import { Panel } from "@/components/molecules/Panel";
import styles from "./DemoScenarioPanel.module.scss";

function observed(run: DemoScenarioRun) {
  if (run.observed_incident_id) return "Incident opened";
  if (run.status === "completed") return "No incident";
  if (run.status === "cancelled") return "Cancelled";
  return run.status === "queued" ? "Waiting for simulator" : "Watching…";
}

function verdict(run: DemoScenarioRun) {
  if (run.status !== "completed" || run.expected_incident === null) return "";
  return Boolean(run.observed_incident_id) === run.expected_incident
    ? "As expected"
    : "Mismatch — review";
}

function ScenarioGroup({
  title,
  hint,
  items,
  disabled,
  onStart,
}: {
  title: string;
  hint: string;
  items: DemoScenarioDefinition[];
  disabled: boolean;
  onStart: (scenario: string) => void;
}) {
  return (
    <div className={styles.group}>
      <h3>{title}</h3>
      <p className={styles.hint}>{hint}</p>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={styles.scenario}
          disabled={disabled}
          onClick={() => onStart(item.id)}
        >
          <strong>{item.label}</strong>
          <span>{item.description}</span>
          <small>About {Math.round(item.duration_seconds)} s</small>
        </button>
      ))}
    </div>
  );
}

export function DemoScenarioPanel({
  trucks,
  scenarios,
  starting,
  error,
  onStart,
  onCancel,
}: {
  trucks: Truck[];
  scenarios?: DemoScenarios;
  starting: boolean;
  error?: string;
  onStart: (truckId: string, scenario: string) => void;
  onCancel: (runId: number) => void;
}) {
  const [selected, setSelected] = useState(trucks[0]?.id ?? "");
  const truckId = trucks.some((truck) => truck.id === selected)
    ? selected
    : (trucks[0]?.id ?? "");
  const runs = scenarios?.runs ?? [];
  const catalogue = scenarios?.catalogue ?? [];
  const truck = trucks.find((item) => item.id === truckId);
  const busyTruck = runs.some(
    (run) =>
      run.truck_id === truckId &&
      (run.status === "queued" || run.status === "running"),
  );
  const blocked = !truck || truck.status === "open" || busyTruck || starting;
  return (
    <Panel
      id="demo"
      title="Demo scenario injection"
      description="Inject a genuine or non-genuine temperature pattern into the live simulation. The unchanged detector decides whether an incident opens."
    >
      <div className={styles.body}>
        <label className={styles.picker}>
          Truck
          <select
            value={truckId}
            onChange={(event) => setSelected(event.target.value)}
          >
            {trucks.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · {item.status}
              </option>
            ))}
          </select>
        </label>
        {truck?.status === "open" && (
          <p className={styles.hint}>
            {truck.id} has an open incident. Wait for recovery before injecting
            another scenario.
          </p>
        )}
        {busyTruck && (
          <p className={styles.hint}>
            A scenario is already queued or running for {truckId}.
          </p>
        )}
        <div className={styles.groups}>
          <ScenarioGroup
            title="Genuine excursions"
            hint="Sustained and continuous: the rule should open one incident."
            items={catalogue.filter((item) => item.genuine)}
            disabled={blocked}
            onStart={(scenario) => onStart(truckId, scenario)}
          />
          <ScenarioGroup
            title="Non-genuine patterns"
            hint="Transient, implausible or gap-broken: the rule should not open an incident."
            items={catalogue.filter((item) => !item.genuine)}
            disabled={blocked}
            onStart={(scenario) => onStart(truckId, scenario)}
          />
        </div>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        {runs.length > 0 && (
          <div className="table-responsive">
            <table className={styles.runs}>
              <caption>Recent scenario runs</caption>
              <thead>
                <tr>
                  <th>Requested</th>
                  <th>Truck</th>
                  <th>Scenario</th>
                  <th>Expected</th>
                  <th>Observed</th>
                  <th>Result</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Timestamp value={run.requested_at} />
                    </td>
                    <td>{run.truck_id}</td>
                    <td>
                      {run.label}
                      <small className={styles.kind}>
                        {run.genuine ? "genuine" : "non-genuine"}
                      </small>
                    </td>
                    <td>
                      {run.expected_incident ? "Incident" : "No incident"}
                    </td>
                    <td>{observed(run)}</td>
                    <td
                      className={
                        verdict(run).startsWith("Mismatch")
                          ? styles.mismatch
                          : styles.match
                      }
                    >
                      {verdict(run)}
                    </td>
                    <td>
                      {(run.status === "queued" ||
                        run.status === "running") && (
                        <button
                          type="button"
                          className={styles.cancel}
                          onClick={() => onCancel(run.id)}
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Panel>
  );
}
