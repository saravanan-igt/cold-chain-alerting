"use client";
import { useEffect, useRef, useState } from "react";
import { LoginTemplate } from "@/components/templates/LoginTemplate";
import { OperatorLogin } from "@/components/organisms/OperatorLogin";
import { loginOperator, logoutOperator } from "@/services/operator-auth";
import { StoreProvider } from "@/store/StoreProvider";
import { Dashboard } from "@/features/dashboard/Dashboard";

interface Session {
  id: string;
}

/** Authentication lives in an HTTP-only cookie; each login gets a fresh store. */
export function SessionBoundary() {
  const [session, setSession] = useState<Session | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function signIn(username: string, password: string) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError(null);
    try {
      await loginOperator(username, password, controller.signal);
      if (!controller.signal.aborted) setSession({ id: crypto.randomUUID() });
    } catch (cause) {
      if (!controller.signal.aborted)
        setError(cause instanceof Error ? cause.message : "Unable to sign in.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function signOut() {
    try {
      await logoutOperator();
      setError(null);
      setSession(null);
    } catch {
      setError("Unable to sign out. Please retry.");
    }
  }

  if (!session)
    return (
      <LoginTemplate>
        <OperatorLogin busy={busy} error={error} onSubmit={signIn} />
      </LoginTemplate>
    );
  return (
    <StoreProvider key={session.id}>
      {error && <p role="alert">{error}</p>}
      <Dashboard onSignOut={signOut} />
    </StoreProvider>
  );
}
