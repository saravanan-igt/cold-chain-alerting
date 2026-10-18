import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiFleetBanner } from "./AiFleetBanner";
import type { AiFleetAssessment, AiStatus } from "@/types/domain";

describe("AiFleetBanner", () => {
  const mockStatus: AiStatus = {
    provider: "anthropic",
    model: "claude-3-5-sonnet",
    mode: "live_claude",
    has_api_key: true,
    capabilities: ["real_alert_detection"],
  };

  const mockAssessment: AiFleetAssessment = {
    tenant: "nimbus",
    fleet_health_score: 92,
    overall_condition: "OPTIMAL",
    active_critical_alerts: 1,
    predictive_warnings: 1,
    normal_operating_trucks: 3,
    executive_dispatch_summary: "Fleet operational status is stable.",
    key_action_items: ["Monitor T-01"],
    truck_assessments: [],
  };

  it("renders Claude AI header and health score", () => {
    render(
      <AiFleetBanner
        status={mockStatus}
        assessment={mockAssessment}
        isScanning={false}
        onScan={vi.fn()}
        onOpenCopilot={vi.fn()}
      />
    );

    expect(screen.getByText(/Claude AI Fleet Intelligence/i)).toBeInTheDocument();
    expect(screen.getByText("92/100")).toBeInTheDocument();
    expect(screen.getByText("OPTIMAL")).toBeInTheDocument();
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

    const btn = screen.getByRole("button", { name: /Run AI Risk Scan/i });
    await userEvent.click(btn);
    expect(handleScan).toHaveBeenCalledTimes(1);
  });
});
