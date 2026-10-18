import styles from "./EmptyState.module.scss";
export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className={styles.empty}>
      <strong>{title}</strong>
      {description && <p>{description}</p>}
    </div>
  );
}
