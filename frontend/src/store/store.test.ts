import { describe, expect, it, vi } from "vitest";
import { coldchainApi } from "@/services/coldchain-api";
import { alpine, nimbus } from "@/test/fixtures";
import { disposeStore, makeStore } from "./store";
import {
  evidencePageChanged,
  incidentClosed,
  incidentPageChanged,
  incidentSelected,
  lifecycleChanged,
} from "./dashboard-slice";

describe("session-scoped Redux and API cache", () => {
  it("deduplicates requests, adds the credential and does not serialize it", async () => {
    const fetcher = vi.fn(async (request: Request) => {
      expect(request.headers.get("X-API-Key")).toBe("test-secret");
      return Response.json(nimbus);
    });
    vi.stubGlobal("fetch", fetcher);
    const store = makeStore({ apiKey: "test-secret" });
    try {
      const first = store.dispatch(coldchainApi.endpoints.getFleet.initiate());
      const second = store.dispatch(coldchainApi.endpoints.getFleet.initiate());
      await Promise.all([first.unwrap(), second.unwrap()]);
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(JSON.stringify(store.getState())).not.toContain("test-secret");
      first.unsubscribe();
      second.unsubscribe();
    } finally {
      disposeStore(store);
    }
  });

  it("isolates customers and discards a late response after sign-out", async () => {
    let resolveOld!: (response: Response) => void;
    const pendingOld = new Promise<Response>((resolve) => {
      resolveOld = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((request: Request) =>
        request.headers.get("X-API-Key") === "nimbus-key"
          ? pendingOld
          : Promise.resolve(Response.json(alpine)),
      ),
    );
    const oldStore = makeStore({ apiKey: "nimbus-key" });
    const newStore = makeStore({ apiKey: "alpine-key" });
    try {
      const oldRequest = oldStore.dispatch(
        coldchainApi.endpoints.getFleet.initiate(),
      );
      disposeStore(oldStore);
      const newRequest = newStore.dispatch(
        coldchainApi.endpoints.getFleet.initiate(),
      );
      expect((await newRequest.unwrap()).tenant).toBe("alpine");
      resolveOld(Response.json(nimbus));
      await oldRequest;
      expect(
        coldchainApi.endpoints.getFleet.select()(oldStore.getState()).data,
      ).toBeUndefined();
      expect(
        coldchainApi.endpoints.getFleet.select()(newStore.getState()).data
          ?.tenant,
      ).toBe("alpine");
    } finally {
      disposeStore(oldStore);
      disposeStore(newStore);
    }
  });

  it("resets paging when filters or selected incidents change", () => {
    const store = makeStore({ apiKey: "key" });
    store.dispatch(incidentPageChanged(40));
    store.dispatch(lifecycleChanged("open"));
    expect(store.getState().dashboard.incidentOffset).toBe(0);
    store.dispatch(incidentSelected("a"));
    store.dispatch(evidencePageChanged(100));
    store.dispatch(incidentSelected("b"));
    expect(store.getState().dashboard.evidenceOffset).toBe(0);
    store.dispatch(incidentClosed());
    expect(store.getState().dashboard.selectedIncidentId).toBeNull();
    disposeStore(store);
  });

  it("encodes bounded list filters and evidence pagination in requests", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        urls.push(request.url);
        return Response.json({ items: [], limit: 20, offset: 20 });
      }),
    );
    const store = makeStore({ apiKey: "key" });
    try {
      await store.dispatch(
        coldchainApi.endpoints.getIncidents.initiate({
          offset: 20,
          lifecycle: "open",
        }),
      );
      await store.dispatch(
        coldchainApi.endpoints.getIncident.initiate({
          id: "incident-1",
          offset: 100,
        }),
      );
      expect(urls[0]).toContain("limit=20&offset=20&lifecycle=open");
      expect(urls[1]).toContain("incidents/incident-1?limit=100&offset=100");
    } finally {
      disposeStore(store);
    }
  });
});
