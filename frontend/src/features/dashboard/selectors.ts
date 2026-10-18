import { createSelector } from "@reduxjs/toolkit";
import type { Fleet } from "@/types/domain";

// These derive presentation metrics only. All alert decisions stay in Python.
export const selectFleetSummary = createSelector(
  [(fleet: Fleet) => fleet.trucks],
  (trucks) => ({
    monitored: trucks.length,
    active: trucks.filter((truck) => truck.status === "open").length,
    unavailable: trucks.filter(
      (truck) =>
        truck.freshness === "stale" || truck.freshness === "never_seen",
    ).length,
    late: trucks.reduce((total, truck) => total + truck.late_count, 0),
  }),
);

export function historicalReference(fleet: Fleet): string | null {
  const latest = fleet.trucks
    .map((truck) => truck.last_observation_at)
    .filter((value): value is string => value !== null)
    .sort()
    .at(-1);
  return latest &&
    new Date(fleet.as_of).getTime() - new Date(latest).getTime() > 86_400_000
    ? latest
    : null;
}
