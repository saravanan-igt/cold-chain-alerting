import { useState, type FormEvent } from "react";
import Form from "react-bootstrap/Form";
import Alert from "react-bootstrap/Alert";
import { Button } from "@/components/atoms/Button";
import styles from "./OperatorLogin.module.scss";

export function OperatorLogin({
  busy,
  error,
  onSubmit,
}: {
  busy: boolean;
  error: string | null;
  onSubmit: (username: string, password: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!busy && username.trim() && password)
      onSubmit(username.trim(), password);
  }
  return (
    <div className={styles.login}>
      <p className={styles.eyebrow}>YOUR OPERATIONS WORKSPACE</p>
      <h2>Welcome aboard.</h2>
      <p className={styles.muted}>Sign in to your customer workspace.</p>
      {error && (
        <Alert variant="danger" role="alert">
          {error}
        </Alert>
      )}
      <Form onSubmit={submit} aria-busy={busy}>
        <Form.Label htmlFor="username">Username</Form.Label>
        <Form.Control
          id="username"
          required
          value={username}
          disabled={busy}
          placeholder="e.g. nimbus.demo"
          onChange={(event) => setUsername(event.target.value)}
          autoComplete="username"
        />
        <Form.Label className="mt-3" htmlFor="password">
          Password
        </Form.Label>
        <Form.Control
          id="password"
          type="password"
          required
          value={password}
          disabled={busy}
          placeholder="Enter your password"
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
        />
        <Button
          type="submit"
          className="mt-4 w-100"
          disabled={busy || !username.trim() || !password}
        >
          {busy ? "Signing in..." : "Sign in"}
        </Button>
      </Form>
      <p className={styles.note}>
        Use the credentials provided by your administrator or local demo terminal.
      </p>
    </div>
  );
}
