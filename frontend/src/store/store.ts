import { configureStore } from "@reduxjs/toolkit";
import { coldchainApi, type ApiCredentials } from "@/services/coldchain-api";
import { dashboardReducer } from "./dashboard-slice";

// Factory, not a singleton: neither SSR requests nor customer sessions share state.
export function makeStore(credentials: ApiCredentials = {}) {
  return configureStore({
    reducer: {
      dashboard: dashboardReducer,
      [coldchainApi.reducerPath]: coldchainApi.reducer,
    },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware({
        thunk: { extraArgument: credentials },
      }).concat(coldchainApi.middleware),
    // Query metadata can contain headers. Do not expose credentials to DevTools.
    devTools: false,
  });
}
export type AppStore = ReturnType<typeof makeStore>;
export type RootState = ReturnType<AppStore["getState"]>;
export type AppDispatch = AppStore["dispatch"];
export function disposeStore(store: AppStore) {
  for (const query of store.dispatch(
    coldchainApi.util.getRunningQueriesThunk(),
  ))
    query.abort();
  store.dispatch(coldchainApi.util.resetApiState());
}
