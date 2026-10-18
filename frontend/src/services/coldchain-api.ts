import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import type {
  Fleet,
  IncidentDetail,
  IncidentPage,
  LifecycleFilter,
  AiStatus,
  AiFleetAssessment,
  AiIncidentTriage,
  AiAlertEvaluation,
  AiChatResponse,
} from "@/types/domain";

export interface ApiCredentials {
  apiKey?: string;
}
export const INCIDENT_PAGE_SIZE = 20;
export const EVIDENCE_PAGE_SIZE = 100;
export const POLLING_INTERVAL = 15_000;

export const coldchainApi = createApi({
  reducerPath: "coldchainApi",
  tagTypes: ["Fleet", "Incidents", "AiFleet"],
  baseQuery: fetchBaseQuery({
    baseUrl: "/api/v1/",
    cache: "no-store",
    credentials: "same-origin",
    prepareHeaders(headers, { extra }) {
      // Credential belongs to this store's closure, never Redux state/actions.
      const key = (extra as ApiCredentials)?.apiKey;
      if (key) headers.set("X-API-Key", key);
      return headers;
    },
  }),
  keepUnusedDataFor: 30,
  refetchOnReconnect: true,
  refetchOnFocus: true,
  endpoints: (builder) => ({
    getFleet: builder.query<Fleet, void>({
      query: () => "trucks",
      providesTags: ["Fleet"],
    }),
    getIncidents: builder.query<
      IncidentPage,
      { offset: number; lifecycle: LifecycleFilter }
    >({
      query: ({ offset, lifecycle }) => ({
        url: "incidents",
        params: {
          limit: INCIDENT_PAGE_SIZE,
          offset,
          ...(lifecycle && { lifecycle }),
        },
      }),
      providesTags: ["Incidents"],
    }),
    getIncident: builder.query<IncidentDetail, { id: string; offset: number }>({
      query: ({ id, offset }) => ({
        url: `incidents/${encodeURIComponent(id)}`,
        params: { limit: EVIDENCE_PAGE_SIZE, offset },
      }),
    }),
    getAiStatus: builder.query<AiStatus, void>({
      query: () => "ai/status",
    }),
    getAiFleetAssessment: builder.query<AiFleetAssessment, void>({
      query: () => "ai/fleet-assessment",
      providesTags: ["AiFleet"],
    }),
    getAiIncidentTriage: builder.query<AiIncidentTriage, string>({
      query: (incidentId) => `ai/incidents/${encodeURIComponent(incidentId)}/triage`,
    }),
    evaluateAlert: builder.mutation<
      AiAlertEvaluation,
      { truck_id: string; incident_id?: string }
    >({
      query: (body) => ({
        url: "ai/evaluate-alert",
        method: "POST",
        body,
      }),
    }),
    sendAiChat: builder.mutation<
      AiChatResponse,
      { message: string; truck_id?: string; incident_id?: string }
    >({
      query: (body) => ({
        url: "ai/chat",
        method: "POST",
        body,
      }),
    }),
  }),
});

export const {
  useGetFleetQuery,
  useGetIncidentsQuery,
  useGetIncidentQuery,
  useGetAiStatusQuery,
  useGetAiFleetAssessmentQuery,
  useGetAiIncidentTriageQuery,
  useEvaluateAlertMutation,
  useSendAiChatMutation,
} = coldchainApi;
