"use client";
import { skipToken } from "@reduxjs/toolkit/query";
import { IncidentDetailDialog } from "@/components/organisms/IncidentDetailDialog";
import {
  EVIDENCE_PAGE_SIZE,
  POLLING_INTERVAL,
  useAcknowledgeIncidentMutation,
  useGetIncidentQuery,
} from "@/services/coldchain-api";
import { apiErrorMessage } from "@/services/errors";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { evidencePageChanged, incidentClosed } from "@/store/dashboard-slice";

export function IncidentDetailController() {
  const dispatch = useAppDispatch();
  const id = useAppSelector((state) => state.dashboard.selectedIncidentId);
  const offset = useAppSelector((state) => state.dashboard.evidenceOffset);
  const query = useGetIncidentQuery(id ? { id, offset } : skipToken, {
    pollingInterval: POLLING_INTERVAL,
    skipPollingIfUnfocused: true,
  });
  const [acknowledge, ackState] = useAcknowledgeIncidentMutation();
  return (
    <IncidentDetailDialog
      open={id !== null}
      detail={query.currentData}
      busy={query.isFetching}
      error={query.error ? apiErrorMessage(query.error) : undefined}
      offset={offset}
      pageSize={EVIDENCE_PAGE_SIZE}
      onClose={() => {
        ackState.reset();
        dispatch(incidentClosed());
      }}
      onPage={(value) => dispatch(evidencePageChanged(value))}
      onRetry={() => {
        if (id) void query.refetch();
      }}
      acknowledging={ackState.isLoading}
      acknowledgeError={
        ackState.error ? apiErrorMessage(ackState.error) : undefined
      }
      onAcknowledge={(note) => {
        if (id) void acknowledge({ id, note: note || undefined });
      }}
    />
  );
}
