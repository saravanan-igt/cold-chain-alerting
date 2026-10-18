import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

// Browsers resolve relative requests; Node's native fetch/Request requires absolute URLs.
const NativeRequest = globalThis.Request;
class BrowserRequest extends NativeRequest {
  constructor(input: string | URL | Request, init?: RequestInit) {
    super(
      typeof input === "string" ? new URL(input, "http://localhost") : input,
      init,
    );
  }
}
beforeEach(() => {
  vi.stubGlobal("Request", BrowserRequest);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
