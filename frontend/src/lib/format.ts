export function timestamp(value: string | null): string {
  return value
    ? `${new Date(value).toISOString().replace("T", " ").slice(0, 19)} UTC`
    : "No observation";
}
export function time(value: string): string {
  return new Date(value).toISOString().slice(11, 16);
}
