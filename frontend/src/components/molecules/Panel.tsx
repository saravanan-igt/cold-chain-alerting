import type { ReactNode } from "react";
import styles from "./Panel.module.scss";
export function Panel({
  id,
  title,
  description,
  action,
  children,
}: {
  id: string;
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={styles.panel} id={id} aria-labelledby={`${id}-heading`}>
      <div className={styles.heading}>
        <div>
          <h2 id={`${id}-heading`}>{title}</h2>
          <p>{description}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
