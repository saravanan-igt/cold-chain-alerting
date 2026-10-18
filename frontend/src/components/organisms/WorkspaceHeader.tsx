import Spinner from "react-bootstrap/Spinner";
import { Button } from "@/components/atoms/Button";
import styles from "./WorkspaceHeader.module.scss";
export function WorkspaceHeader({
  busy,
  onSignOut,
}: {
  busy: boolean;
  onSignOut: () => void;
}) {
  return (
    <header className={styles.header}>
      <span>
        Operations / <b>Fleet overview</b>
      </span>
      <div>
        {busy && <Spinner size="sm" role="status" aria-label="Updating" />}
        <span>Refreshes every 15s</span>
        <Button variant="outline-secondary" size="sm" onClick={onSignOut}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
