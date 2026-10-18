import styles from "./Brand.module.scss";
export function Brand({ tagline = false }: { tagline?: boolean }) {
  return (
    <div className={styles.brand}>
      ❄ coldline{tagline && <span>OPERATIONS INTELLIGENCE</span>}
    </div>
  );
}
