"use client";
import { Button } from "@/components/atoms/Button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="route-feedback">
      <h1>Unable to display the workspace</h1>
      <p>Try again. If the issue continues, reload and sign in again.</p>
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
