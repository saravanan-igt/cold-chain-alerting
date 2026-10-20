import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiFleetBanner } from "./AiFleetBanner";
import type { AiFleetAssessment, AiStatus } from "@/types/domain";

describe("AiFleetBanner", () => {
  const mockStatus: AiStatus = {
    provider: "deterministic_rules",
    model: "coldline-detector-v1",
    mode: "local",
    has_api_key: false,
    capabilities: ["configured_rule_evaluation"],
  };

  const mockAssessment: AiFleetAssessment = {
    tenant: "nimbus",
    fleet_health_score: null,
    overall_condition: "ACTIVE_INCIDENTS",
    active_critical_alerts: 1,
    predictive_warnings: 1,
    normal_operating_trucks: 3,
    executive_dispatch_summary: "Fleet operational status is stable.",
    key_action_items: ["Monitor T-01"],
    truck_assessments: [],
  };

  it("renders rule summary without inventing a health score", () => {
    render(
      <AiFleetBanner
        status={mockStatus}
        assessment={mockAssessment}
        isScanning={false}
        onScan={vi.fn()}
        onOpenCopilot={vi.fn()}
      />
    );

    expect(screen.getByText("Fleet rule summary")).toBeInTheDocument();
    expect(screen.getByText("No cargo-safety score is calculated")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE INCIDENTS")).toBeInTheDocument();
  });

  it("triggers onScan when scan button is clicked", async () => {
    const handleScan = vi.fn();
    render(
      <AiFleetBanner
        status={mockStatus}
        assessment={mockAssessment}
        isScanning={false}
        onScan={handleScan}
        onOpenCopilot={vi.fn()}
      />
    );

    const btn = screen.getByRole("button", { name: /Refresh fleet summary/i });
    await userEvent.click(btn);
    expect(handleScan).toHaveBeenCalledTimes(1);
  });
});
