import type { ReactNode } from "react";
import { Brand } from "@/components/atoms/Brand";
import styles from "./LoginTemplate.module.scss";
export function LoginTemplate({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <section className={styles.brand}>
        <Brand tagline />
        <h1>
          Protect the cargo.
          <br />
          Quiet the noise.
        </h1>
        <p>
          Evidence-led temperature monitoring for the people keeping the cold
          chain moving.
        </p>
        <div className={styles.principles}>
          <span>01 &nbsp; Observe</span>
          <span>02 &nbsp; Qualify</span>
          <span>03 &nbsp; Resolve</span>
        </div>
      </section>
      <main className={styles.form}>{children}</main>
    </div>
  );
}
