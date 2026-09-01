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

/**
 * Milestone 7.1 -- relative phrasing for the Command Center's source-
 * freshness line ("Data refreshed 4 min ago"), distinct from
 * `formatDateTime` (used for a recommendation's own "Decided ..."
 * timestamp). `now` is injectable so tests are deterministic rather
 * than depending on the real clock. Falls back to an absolute date
 * past a week old rather than an increasingly meaningless "12 days ago".
 */
export function formatRelativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) {
    return "";
  }
  const then = new Date(iso).getTime();
  const diffMs = now.getTime() - then;
  if (diffMs < 0) {
    return formatDateTime(iso);
  }
  const diffMinutes = Math.floor(diffMs / 60_000);
  if (diffMinutes < 1) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} hr ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
  }
  return formatDateTime(iso);
}
