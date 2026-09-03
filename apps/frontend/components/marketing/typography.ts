/**
 * Public Web M2.1 -- the one className every `<Text variant="body">` on
 * a PUBLIC marketing page (`/`, `/how-it-works`, `/features`, `/about`)
 * gets, so the brightened body tone (`text-body-bright`, defined in
 * globals.css/tailwind.config.ts) and its medium weight are applied
 * consistently from a single place rather than copy-pasted at ~25 call
 * sites. The `!` (important) prefix is deliberate and necessary: `Text`'s
 * own `body` variant already ships `text-text-secondary` as part of its
 * base class list (`components/ds/Text.tsx`), a same-specificity Tailwind
 * color utility -- without `!important`, which of the two wins is
 * decided by Tailwind's internal generation order, not by where this
 * className appears in the JSX, which is not something to rely on.
 * `!text-body-bright` sidesteps that ambiguity entirely. Never applied
 * to `heading`/`display`/`label`/`data` variants, and never imported by
 * anything under the authenticated app -- this must not change Command
 * Center typography.
 */
export const MARKETING_BODY_CLASS = "!text-body-bright font-medium";
