"use client";
import {
  coldchainApi,
  useGetFleetQuery,
  useGetIncidentsQuery,
  POLLING_INTERVAL,
} from "@/services/coldchain-api";
import { apiErrorMessage } from "@/services/errors";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import {
  incidentPageChanged,
  incidentSelected,
  lifecycleChanged,
} from "@/store/dashboard-slice";
import type { LifecycleFilter } from "@/types/domain";

const LIVE_POLLING_INTERVAL = 5_000;
const selectFleet = coldchainApi.endpoints.getFleet.select();

export function useDashboard() {
  const dispatch = useAppDispatch();
  const lifecycle = useAppSelector((state) => state.dashboard.lifecycle);
  const offset = useAppSelector((state) => state.dashboard.incidentOffset);
  // Live simulations change every 10 seconds; poll faster so injected scenarios are visible promptly.
  const live = useAppSelector(
    (state) => selectFleet(state).data?.demo_mode === "live_simulation",
  );
  const polling = {
    pollingInterval: live ? LIVE_POLLING_INTERVAL : POLLING_INTERVAL,
    skipPollingIfUnfocused: true,
  };
  const fleetQuery = useGetFleetQuery(undefined, polling);
  const incidentsQuery = useGetIncidentsQuery({ lifecycle, offset }, polling);
  return {
    fleet: fleetQuery.currentData,
    fleetLoading: fleetQuery.isLoading,
    fleetError: fleetQuery.error
      ? apiErrorMessage(fleetQuery.error)
      : undefined,
    retryFleet: fleetQuery.refetch,
    // currentData prevents the old page/filter from being shown while a new query loads.
    incidents: incidentsQuery.currentData?.items,
    incidentsBusy: incidentsQuery.isFetching,
    incidentsError: incidentsQuery.error
      ? apiErrorMessage(incidentsQuery.error)
      : undefined,
    retryIncidents: incidentsQuery.refetch,
    busy: fleetQuery.isFetching || incidentsQuery.isFetching,
    lifecycle,
    offset,
    onFilter: (value: LifecycleFilter) => dispatch(lifecycleChanged(value)),
    onPage: (value: number) => dispatch(incidentPageChanged(value)),
    onSelect: (id: string) => dispatch(incidentSelected(id)),
  };
}
