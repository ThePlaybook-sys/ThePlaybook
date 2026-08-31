/** Shared date formatting for recommendation freshness/grade labels --
 * one place so "Decided ..." and "Result corrected ..." never drift
 * into inconsistent formats across components. */
export function formatDateTime(iso: string | null): string {
  if (!iso) {
    return "";
  }
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
