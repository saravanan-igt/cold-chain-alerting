import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { nimbus, alpine, detail } from "@/test/fixtures";
import { SessionBoundary } from "./SessionBoundary";
import { StrictMode } from "react";

function mockServer() {
  let key: string | null = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(input, init);
      if (new URL(request.url).pathname.endsWith("/session")) {
        if (request.method === "DELETE") {
          key = null;
          return Response.json({});
        }
        const body = await request.json();
        key = body.password === "password" ? body.username : null;
        return Response.json(
          {},
          { status: key === "nimbus-key" || key === "alpine-key" ? 200 : 401 },
        );
      }
      if (key !== "nimbus-key" && key !== "alpine-key")
        return Response.json({}, { status: 401 });
      const url = new URL(request.url);
      if (url.pathname.endsWith("/trucks"))
        return Response.json(key === "nimbus-key" ? nimbus : alpine);
      if (url.pathname.endsWith("/incidents/incident-1"))
        return Response.json(detail);
      const items =
        key === "nimbus-key" && url.searchParams.get("lifecycle") !== "open"
          ? [detail]
          : [];
      return Response.json({ items, limit: 20, offset: 0 });
    }),
  );
}

it("validates login, shows evidence and clears the prior customer on sign-out", async () => {
  mockServer();
  const user = userEvent.setup();
  render(
    <StrictMode>
      <SessionBoundary />
    </StrictMode>,
  );
  await user.type(screen.getByLabelText("Username"), "nimbus-key");
  await user.type(screen.getByLabelText("Password"), "password");
  await user.click(screen.getByRole("button", { name: /Sign in/ }));
  expect(await screen.findByText("Nimbus Freight")).toBeInTheDocument();
  expect(await screen.findByText("Historical telemetry")).toBeInTheDocument();
  await user.click(
    await screen.findByRole("button", { name: /Temperature excursion/ }),
  );
  const dialog = await screen.findByRole("dialog");
  expect(
    await within(dialog).findByText(detail.explanation),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("Incident qualified")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Close" }));
  await user.selectOptions(
    screen.getByLabelText("Filter incident lifecycle"),
    "open",
  );
  expect(
    await screen.findByText("No incidents in this view"),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() =>
    expect(screen.queryByText("Nimbus Freight")).not.toBeInTheDocument(),
  );
  await user.type(screen.getByLabelText("Username"), "alpine-key");
  await user.type(screen.getByLabelText("Password"), "password");
  await user.click(screen.getByRole("button", { name: /Sign in/ }));
  expect(await screen.findByText("Alpine Produce")).toBeInTheDocument();
  expect(screen.getByLabelText("Filter incident lifecycle")).toHaveValue("");
  expect(screen.queryByText("T-01")).not.toBeInTheDocument();
});

it("keeps invalid credentials outside the workspace and allows retry", async () => {
  mockServer();
  const user = userEvent.setup();
  render(<SessionBoundary />);
  await user.type(screen.getByLabelText("Username"), "wrong");
  await user.type(screen.getByLabelText("Password"), "password");
  await user.click(screen.getByRole("button", { name: /Sign in/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Invalid username or password",
  );
  expect(
    screen.queryByRole("button", { name: "Sign out" }),
  ).not.toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /Sign in/ })).toBeEnabled(),
  );
});

it("shows query failure without invented fleet metrics and retries successfully", async () => {
  let fleetRequests = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request =
        input instanceof Request ? input : new Request(input, init);
      if (new URL(request.url).pathname.endsWith("/trucks")) {
        fleetRequests += 1;
        // Authentication succeeds; the initial workspace query fails.
        return fleetRequests === 1
          ? Response.json({}, { status: 503 })
          : Response.json(nimbus);
      }
      return Response.json({ items: [], limit: 20, offset: 0 });
    }),
  );
  const user = userEvent.setup();
  render(<SessionBoundary />);
  await user.type(screen.getByLabelText("Username"), "nimbus-key");
  await user.type(screen.getByLabelText("Password"), "password");
  await user.click(screen.getByRole("button", { name: /Sign in/ }));
  const error = await screen.findByRole("alert");
  expect(error).toHaveTextContent("Unable to load data");
  expect(screen.queryByLabelText("Fleet metrics")).not.toBeInTheDocument();
  await user.click(within(error).getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("Nimbus Freight")).toBeInTheDocument();
  expect(screen.getByLabelText("Fleet metrics")).toBeInTheDocument();
});
