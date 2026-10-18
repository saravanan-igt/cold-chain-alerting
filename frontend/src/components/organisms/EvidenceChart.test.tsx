import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { detail } from "@/test/fixtures";
import { EvidenceChart } from "./EvidenceChart";

it("does not draw false continuity across missing telemetry", () => {
  render(<EvidenceChart detail={detail} />);
  expect(screen.getByRole("img")).toBeInTheDocument();
  expect(screen.getAllByTestId("evidence-segment")).toHaveLength(2);
  expect(screen.getByText("08:20 UTC: 9 °C · qualified")).toBeInTheDocument();
});
