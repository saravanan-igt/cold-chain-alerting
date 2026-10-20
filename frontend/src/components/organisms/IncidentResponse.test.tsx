import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IncidentResponsePanel } from "./IncidentResponsePanel";
import { DemoScenarioPanel } from "./DemoScenarioPanel";
import { detail, nimbus } from "@/test/fixtures";
import type { DemoScenarios } from "@/types/domain";

describe("IncidentResponsePanel", () => {
  it("acknowledges with an audit note", async () => {
    const onAcknowledge = vi.fn();
    render(
      <IncidentResponsePanel
        detail={{ ...detail, lifecycle: "open", acknowledgement: null }}
        acknowledging={false}
        onAcknowledge={onAcknowledge}
      />,
    );
    expect(screen.getByText(/Escalation continues/)).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText(/Note for the audit trail/),
      " Driver contacted ",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Acknowledge incident" }),
    );
    expect(onAcknowledge).toHaveBeenCalledWith("Driver contacted");
  });

  it("shows ownership, timeline and delivery outcomes", () => {
    render(
      <IncidentResponsePanel
        detail={{
          ...detail,
          acknowledgement: {
            acknowledged_by: "dana",
            acknowledged_at: "2026-07-20T08:25:00Z",
            note: "On it",
          },
          timeline: [
            {
              kind: "opened",
              actor: "detector",
              at: "2026-07-20T08:20:00Z",
              details: {},
            },
            {
              kind: "escalated",
              actor: "escalation-policy",
              at: "2026-07-20T08:35:00Z",
              details: { level_index: 0 },
            },
          ],
          notifications: [
            {
              id: 1,
              incident_id: "incident-1",
              event: "incident.opened",
              event_key: "incident.opened",
              channel_id: "ops-webhook",
              channel_type: "webhook",
              status: "dead",
              attempts: 8,
              next_attempt_at: "",
              created_at: "",
              delivered_at: null,
              last_error: "HTTP 400",
            },
          ],
        }}
        acknowledging={false}
        onAcknowledge={vi.fn()}
      />,
    );
    expect(screen.getByText("Acknowledged by dana")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Acknowledge incident" }),
    ).toBeNull();
    expect(screen.getByText(/\(level 1\)/)).toBeInTheDocument();
    expect(screen.getByText("dead")).toBeInTheDocument();
    expect(screen.getByText(/HTTP 400/)).toBeInTheDocument();
  });
});

describe("DemoScenarioPanel", () => {
  const scenarios: DemoScenarios = {
    sample_seconds: 10,
    catalogue: [
      {
        id: "compressor_failure",
        label: "Compressor failure",
        genuine: true,
        expected_incident: true,
        description: "Sustained",
        duration_seconds: 100,
      },
      {
        id: "door_open_spike",
        label: "Door-open spike",
        genuine: false,
        expected_incident: false,
        description: "Short",
        duration_seconds: 60,
      },
    ],
    runs: [
      {
        id: 2,
        truck_id: "T-01",
        scenario: "door_open_spike",
        label: "Door-open spike",
        genuine: false,
        expected_incident: false,
        status: "completed",
        requested_by: "op",
        requested_at: "2026-07-20T08:00:00Z",
        started_at: "2026-07-20T08:00:05Z",
        completed_at: "2026-07-20T08:01:05Z",
        observed_incident_id: null,
        steps: [],
      },
    ],
  };

  it("separates genuine and non-genuine scenarios and starts one", async () => {
    const onStart = vi.fn();
    render(
      <DemoScenarioPanel
        trucks={nimbus.trucks}
        scenarios={scenarios}
        starting={false}
        onStart={onStart}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("Genuine excursions")).toBeInTheDocument();
    expect(screen.getByText("Non-genuine patterns")).toBeInTheDocument();
    expect(screen.getByText("As expected")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /Compressor failure/ }),
    );
    expect(onStart).toHaveBeenCalledWith("T-01", "compressor_failure");
  });

  it("blocks injection while the truck has an open incident", () => {
    render(
      <DemoScenarioPanel
        trucks={[{ ...nimbus.trucks[0], status: "open" }]}
        scenarios={scenarios}
        starting={false}
        onStart={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Compressor failure/ }),
    ).toBeDisabled();
    expect(screen.getByText(/has an open incident/)).toBeInTheDocument();
  });
});
