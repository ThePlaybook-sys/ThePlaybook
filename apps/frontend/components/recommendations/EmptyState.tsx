import { Surface, Text } from "@/components/ds";

export interface EmptyStateProps {
  headline: string;
  body?: string;
}

/**
 * The one honest-state renderer for every "nothing to show" case a
 * recommendation page can hit -- unauthenticated, not found, a real
 * upstream error, or a genuinely empty feed. Never implies "still
 * analyzing" or "loading" (HQ's explicit rule): every caller passes a
 * specific, already-resolved headline rather than this component
 * guessing at one.
 */
export function EmptyState({ headline, body }: EmptyStateProps) {
  return (
    <Surface level="card" className="flex flex-col items-start gap-sm p-lg">
      <Text variant="heading">{headline}</Text>
      {body && <Text variant="body">{body}</Text>}
    </Surface>
  );
}
