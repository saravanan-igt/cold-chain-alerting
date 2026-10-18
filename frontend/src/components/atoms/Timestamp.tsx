import { timestamp } from "@/lib/format";
export function Timestamp({ value }: { value: string | null }) {
  return value ? (
    <time dateTime={value}>{timestamp(value)}</time>
  ) : (
    <span>No observation</span>
  );
}
