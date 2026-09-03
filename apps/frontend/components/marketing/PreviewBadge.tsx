export interface PreviewBadgeProps {
  label?: string;
}

/**
 * Public Web M2.2 -- the one visual marker for a launch-vision capability
 * that isn't built yet (intelligent parlays, conversational MANSA,
 * Telegram). Deliberately NOT `StateBadge`: that component's own
 * docstring reserves it exclusively for the settled-outcome/freshness
 * state triad (win/loss/push, confidence-floor pass/fail) -- "never
 * apply --state-* colors directly elsewhere." A product-roadmap marker
 * is a different concept entirely and needs its own visual language, so
 * this uses `--mansa-violet` instead -- already documented as "identity/
 * premium depth, used selectively," which is exactly the register a
 * "coming at launch" marker needs: clearly MANSA-branded, clearly not
 * the cobalt "this is real and active" signal every shipped capability
 * uses elsewhere on these pages.
 */
export function PreviewBadge({ label = "Preview — Coming at Launch" }: PreviewBadgeProps) {
  return (
    <span className="inline-flex items-center rounded-sm border border-mansa-violet/40 bg-mansa-violet/10 px-sm py-xs text-label uppercase tracking-wide text-mansa-violet">
      {label}
    </span>
  );
}
