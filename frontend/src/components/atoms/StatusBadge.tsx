import type { DetectorStatus, Freshness, Lifecycle } from "@/types/domain";
import styles from "./StatusBadge.module.scss";
type Status = DetectorStatus | Freshness | Lifecycle;
export function StatusBadge({ value }: { value: Status }) {
  return (
    <span className={`${styles.badge} ${styles[value] ?? ""}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
