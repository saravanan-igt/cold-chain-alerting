"use client";
import { DemoScenarioPanel } from "@/components/organisms/DemoScenarioPanel";
import {
  useCancelDemoScenarioMutation,
  useGetDemoScenariosQuery,
  useStartDemoScenarioMutation,
} from "@/services/coldchain-api";
import { apiErrorMessage } from "@/services/errors";
import type { Truck } from "@/types/domain";

const DEMO_POLLING = { pollingInterval: 5_000, skipPollingIfUnfocused: true };

/** Only mounted for tenants the server labels demo_mode=live_simulation. */
export function DemoScenarioController({ trucks }: { trucks: Truck[] }) {
  const query = useGetDemoScenariosQuery(undefined, DEMO_POLLING);
  const [start, startState] = useStartDemoScenarioMutation();
  const [cancel, cancelState] = useCancelDemoScenarioMutation();
  const failure = startState.error ?? cancelState.error ?? query.error;
  return (
    <DemoScenarioPanel
      trucks={trucks}
      scenarios={query.currentData}
      starting={startState.isLoading}
      error={failure ? apiErrorMessage(failure) : undefined}
      onStart={(truck_id, scenario) => {
        cancelState.reset();
        void start({ truck_id, scenario });
      }}
      onCancel={(id) => {
        startState.reset();
        void cancel(id);
      }}
    />
  );
}
