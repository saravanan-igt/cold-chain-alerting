export async function loginOperator(
  username: string,
  password: string,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coldline-Request": "browser",
    },
    credentials: "same-origin",
    cache: "no-store",
    signal,
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "Invalid username or password."
        : response.status === 429
          ? "Too many attempts. Try again in a minute."
          : "Unable to connect. Check that the backend is running.",
    );
}
export async function logoutOperator(): Promise<void> {
  const response = await fetch("/api/v1/session", {
    method: "DELETE",
    credentials: "same-origin",
    headers: { "X-Coldline-Request": "browser" },
  });
  if (!response.ok) throw new Error("Unable to sign out.");
}
