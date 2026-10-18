import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { LifecycleFilter } from "@/types/domain";

export interface DashboardState {
  lifecycle: LifecycleFilter;
  incidentOffset: number;
  selectedIncidentId: string | null;
  evidenceOffset: number;
}
const initialState: DashboardState = {
  lifecycle: "",
  incidentOffset: 0,
  selectedIncidentId: null,
  evidenceOffset: 0,
};
const dashboardSlice = createSlice({
  name: "dashboard",
  initialState,
  reducers: {
    lifecycleChanged(state, action: PayloadAction<LifecycleFilter>) {
      state.lifecycle = action.payload;
      state.incidentOffset = 0;
    },
    incidentPageChanged(state, action: PayloadAction<number>) {
      state.incidentOffset = Math.max(0, Math.min(100000, action.payload));
    },
    incidentSelected(state, action: PayloadAction<string>) {
      state.selectedIncidentId = action.payload;
      state.evidenceOffset = 0;
    },
    incidentClosed(state) {
      state.selectedIncidentId = null;
      state.evidenceOffset = 0;
    },
    evidencePageChanged(state, action: PayloadAction<number>) {
      state.evidenceOffset = Math.max(0, Math.min(100000, action.payload));
    },
  },
});
export const {
  lifecycleChanged,
  incidentPageChanged,
  incidentSelected,
  incidentClosed,
  evidencePageChanged,
} = dashboardSlice.actions;
export const dashboardReducer = dashboardSlice.reducer;
