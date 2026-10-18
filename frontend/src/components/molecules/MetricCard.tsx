import styles from "./MetricCard.module.scss";
export function MetricCard({
  label,
  value,
  description,
  highlighted = false,
}: {
  label: string;
  value: number;
  description: string;
  highlighted?: boolean;
}) {
  return (
    <article
      className={`${styles.card} ${highlighted ? styles.highlighted : ""}`}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{description}</small>
    </article>
  );
}
