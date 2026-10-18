import { Brand } from "@/components/atoms/Brand";
import styles from "./WorkspaceNavigation.module.scss";
export function WorkspaceNavigation({ customer }: { customer?: string }) {
  return (
    <>
      <a
        className={styles.brandLink}
        href="#fleet"
        aria-label="Coldline fleet overview"
      >
        <Brand />
      </a>
      <div className={styles.customer}>
        <span>CUSTOMER WORKSPACE</span>
        <strong>{customer ?? "Connecting…"}</strong>
      </div>
      <nav className={styles.navigation} aria-label="Workspace">
        <a href="#fleet">▦ &nbsp; Fleet overview</a>
        <a href="#incidents">◉ &nbsp; Incident history</a>
      </nav>
      <div className={styles.footer}>
        ● Evidence before escalation
        <p>
          Temperature monitoring
          <br />
          with customer-specific rules
        </p>
      </div>
    </>
  );
}
