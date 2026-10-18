import type { CSSProperties, ReactNode } from "react";
import styles from "./WorkspaceTemplate.module.scss";
export function WorkspaceTemplate({
  accent,
  sidebar,
  header,
  footer,
  children,
}: {
  accent?: string;
  sidebar: ReactNode;
  header: ReactNode;
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      className={styles.workspace}
      style={{ "--customer-accent": accent ?? "#17675e" } as CSSProperties}
    >
      <aside className={styles.sidebar}>{sidebar}</aside>
      <div className={styles.column}>
        {header}
        <main className={styles.main}>
          {children}
          {footer}
        </main>
      </div>
    </div>
  );
}
