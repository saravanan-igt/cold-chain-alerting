import { Button } from "@/components/atoms/Button";
import styles from "./Pagination.module.scss";
export function Pagination({
  label = "Showing",
  offset,
  count,
  pageSize,
  total,
  busy,
  onChange,
}: {
  label?: string;
  offset: number;
  count: number;
  pageSize: number;
  total?: number;
  busy: boolean;
  onChange: (offset: number) => void;
}) {
  const hasNext =
    total === undefined ? count === pageSize : offset + count < total;
  return (
    <nav className={styles.pagination} aria-label={`${label} pagination`}>
      <span>
        {label} {offset + (count ? 1 : 0)}–{offset + count}
        {total !== undefined && ` of ${total}`}
      </span>
      <div>
        <Button
          size="sm"
          variant="outline-secondary"
          disabled={offset === 0 || busy}
          onClick={() => onChange(Math.max(0, offset - pageSize))}
        >
          Previous
        </Button>
        <Button
          size="sm"
          variant="outline-secondary"
          disabled={!hasNext || busy || offset + pageSize > 100000}
          onClick={() => onChange(offset + pageSize)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
