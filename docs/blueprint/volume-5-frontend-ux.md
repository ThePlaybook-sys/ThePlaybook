# The Playbook — Volume 5
## Frontend & UX Architecture: Dashboards, Navigation, Components, Notifications, Onboarding, Accessibility

**Version:** v5.1
**Last updated:** 2026-09-01
**Depends on:** Volume 1 (v3.1 — personas, tiers, journeys), Volume 3 (v4.24 — the real Phase 5 product/explanation/activation-snapshot/grading schema), Volume 4 (v5.10 — explainability mapping, consensus/agreement-variance semantics, 12-agent committee reality)
**v5.1 note (MINOR):** Phase 6 Milestone 6 (Auth + Onboarding + Account) implemented `/sign-in`, `/onboarding`, `/account`, `/account/how-it-works`, `/auth/callback`, and `/auth/sign-out` against the existing Supabase Auth backend and the existing Phase 2 `GET`/`PATCH /v1/user/profile` and Phase 6 M2 `GET /v1/user/subscription` routes — no new backend route, no second authentication system. Replaces M3's placeholder `pb_session_token` raw-cookie read (which never issued, refreshed, or validated anything itself) with the real `@supabase/ssr` session-cookie architecture, root-entry routing (`/` → `/sign-in`/`/onboarding`/`/today` per sign-in and onboarding-completion state), first-use core-concept education (Confidence/Modeled Probability/EV/No Bet, reopenable from Account), and a persistent nav across all five authenticated destinations. §2 gains the SSR session architecture actually built; §5 gains the onboarding/account/education component contracts; §11 gains the two additive routes (`GET`/`PATCH /v1/user/profile`, both unchanged since Phase 2) M6 is the first frontend milestone to actually consume. See `CHANGELOG.md` v5.1 entry for full reasoning, including the one real STOP-condition analysis this milestone required (DEV email-confirmation configuration could not be directly verified from this sandbox — resolved by building the sign-in/sign-up flow to branch on the real API response rather than assume either configuration, not by guessing).
**v5.0.6 note (PATCH):** Phase 6 Milestone 5 (Track Record) implemented `/track-record` against the existing M2 `GET /v1/track-record` route unchanged — no new backend route or grading algorithm. §5's Track Record Summary type sketch is corrected to match the route's real, already-shipped response shape: `record`/`byRecommendationType` entries carry `mixedSettled` (the sketch omitted it) and each `byRecommendationType` entry carries its own `sampleSize` (the sketch had none) — both real fields `apps/api-gateway/app/track_record.py` has returned since Milestone 2; this is a documentation correction, not a contract change. No win-rate or derived percentage is computed or rendered anywhere in the implementation, per HQ's explicit M5 STOP condition — raw counts only. `byRecommendationType` entries are filtered client-side to `sampleSize > 0` before rendering, which excludes the zero-sample `no_bet`/`bankroll_preservation` phantom entries the route's own `by_type.setdefault(...)` creates for every `NOT_APPLICABLE`-graded product (a real, disclosed quirk of the existing handler, not fixed here — HQ's M5 authorization scoped this milestone to the frontend only). See `CHANGELOG.md` v5.0.6 entry.
**v5.0.5 note (PATCH):** Phase 6 Milestone 4 (History / Time Machine) implemented `/history` and `/history/[displayId]` against the existing M2 reconstruction proxy and M2/M3 detail route — no new backend route. §5's Time Machine section gains an implementation note (below) on the two-read composition and the explicit temporal-integrity handling HQ's M4 authorization required. §11 gains the reconstruction route's real field shape (snake_case, `dataclasses.asdict()` verbatim — distinct from every other route's camelCase). See `CHANGELOG.md` v5.0.5 entry.
**v5.0.4 note (PATCH):** Phase 6 Milestone 3 (Core Recommendation Experience) implemented `/today`, `/recommendations`, and `/recommendations/[displayId]` against M2.1's corrected contract. §2 gains the Server-Component-direct-fetch architecture actually built (`pb_session_token` cookie, `API_GATEWAY_URL`, the `ApiResult<T>` discriminated result type). No component contract or screen-state text in §5/§6 changed — the build matches what was already specified there. See `CHANGELOG.md` v5.0.4 entry.
**v5.0.3 note (PATCH):** Milestone 2.1 (additive contract correction, discovered at the Milestone 3 boundary) adds a `grade` field to the three product read routes in §11, and corrects §5's `RecommendationCardProps` accordingly: `status` stays exactly `'active'|'withdrawn'` (lifecycle, never `'graded'`) and the card's grade state is carried in a separate `grade: {outcome, gradedAt, isCorrection, correctedAt} | null` object, not flat `status`/`outcome`/`isCorrection` fields as originally drafted in v5.0. See `CHANGELOG.md` v5.0.3 entry for full reasoning.
**v5.0.2 note (PATCH):** New §11 documents the six real API routes Phase 6 Milestone 2 shipped (`apps/api-gateway`) — exact routes, tier-gating behavior, data sources, and the neutral-ordering/freshness/Track-Record-scope rules those routes actually enforce, plus a real RLS-policy gap found during implementation and deliberately preserved (not fixed) in the API layer. See `CHANGELOG.md` v5.0.2 entry for full reasoning.
**v5.0.1 note (PATCH):** Phase 6 Milestone 1 (Design System) implemented the §4 token roles this volume deliberately left as candidate structural values pending an implementation pass. Concrete values (palette, Inter as the typeface, exact type/spacing/radius/motion scale) now live in `apps/frontend/app/globals.css` and `apps/frontend/tailwind.config.ts` — those files are the single source of truth for exact values going forward, not this document, to avoid the two drifting apart. §4's role/principle text is unchanged and still governs; only "what number" questions it left open are now answered, in code. See `CHANGELOG.md` v5.0.1 entry and `PROGRESS.md`'s Milestone 1 entry for the full dependency/decision record.
**v5.0 note (MAJOR):** Full structural rewrite. This volume's v1.0–v4.0 body was written before Phase 4/5 built the real product layer (`recommendation_products`/`recommendation_legs`/explanation tables/activation snapshots/lifecycle events/grading tables did not exist yet) and no longer describes the product Phase 4-5 actually built. Replaced by the Phase 6 Product/UX architecture produced across three planning passes (repository archaeology against the real schema/code, two rounds of HQ review) and formally approved as the Phase 6 baseline. Headline changes: a five-destination IA (`/today`, `/recommendations`, `/track-record`, `/history`, `/account`) replaces the original 13-route table; `/chat` is demoted from default-landing-route to a deferred future entry point (no NL Engine or `conversation_messages` was ever built — Volume 4 §7 remains unimplemented); onboarding is dashboard-first, not chat-first, and collects only `jurisdiction_state`; component contracts are rewritten against the real product/leg/explanation schema and a four-layer progressive-disclosure model; the Transparency Meter's agreement formula is corrected to the real `> 0.10` threshold; Notifications is reclassified future (no `notifications` table exists); Track Record is scoped to only what's directly stored or cheaply derivable. The v1.0–v4.0 notes below are left standing as the historical record of this volume's prior design — not deleted, not silently rewritten. See `CHANGELOG.md` v5.0 entry for the full four-field reasoning, and the Engineering Roadmap v4.5 entry for the matching Phase 6 milestone update.
**v4.0 note:** `data_quality` in the AI Transparency Meter (§5) now computed from `daily_game_intelligence`'s concrete per-category metadata (Volume 3 §4.1) instead of vague cache-freshness language. See `CHANGELOG.md` v4.0 entry for full reasoning. **[Superseded by v5.0 — see the corrected Transparency Meter contract in §5 below.]**
**Companion document:** The separate Designer Onboarding Guide/Dashboard UX-UI Design Brief referenced by this volume's prior versions was never located in this repository — confirmed absent across a full repository archaeology pass (2026-08-28). Treat it as an unresolved external artifact gap, not a document to assume exists. If HQ supplies it later, it must be diffed against this v5.0 architecture before being incorporated — this volume is not blocked on it.

---

## 1. How This Volume Closes the Loop

Every prior volume built toward something the user sees. This volume is where that finally happens: Volume 1's personas and journeys become actual screens, Volume 3's real Phase 5 product/explanation/grading tables become actual props and API responses, and Volume 4's 12-agent committee consensus becomes a recommendation card someone can read in three seconds. Nothing here should introduce new betting intelligence, new recommendation/ranking logic, or new AI reasoning — this is the volume that renders decisions already made elsewhere in the system.

---

## 2. Frontend Stack & Architecture

**Framework:** Next.js 14 (App Router) + React 18 + TypeScript — already the live `apps/frontend` stack, confirmed by repository archaeology. Server Components for anything that doesn't need interactivity, Client Components for stateful screens (recommendation feed, layered detail views).

**Data fetching:** Server-side fetch for initial page load, client-side polling for revalidation — repository archaeology confirmed a real, working polling pattern already exists (`apps/frontend/app/demo/lib/usePolling.ts`: ~3s while a screen is active, ~10s while idle, paused when the tab is hidden) and should be reused/generalized rather than replaced. A data-fetching library (e.g. React Query) is a legitimate Phase 6 M1 dependency decision, not pre-committed here — see the Engineering Roadmap's M1 milestone, which requires recording significant dependency decisions when made.

**Real-time updates: no server-push mechanism exists today.** The v1.0–v4.0 versions of this volume specified Supabase Realtime for two cases (a recommendation flipping to `withdrawn` mid-session, live game status). Repository archaeology (2026-08-28) confirmed neither is implemented, and no code anywhere subscribes to Supabase Realtime. Phase 6 should build the "feels alive" experience through polling + client-side diffing on the existing pattern above, not by assuming real-time infrastructure that isn't there. Supabase Realtime for these two cases remains a legitimate, narrower future addition once real usage justifies it — not a Phase 6 requirement.

**State management:** no state-management library is installed today (confirmed: `apps/frontend/package.json` has zero runtime dependencies beyond Next/React). Local UI state uses React's built-in state; a server-state library, if added in M1, should be recorded as a dependency decision at that time rather than assumed here.

**Server-side data fetching (Milestone 3, superseded by Milestone 6's real session architecture):** `/today`, `/recommendations`, and every other authenticated Server Component fetch directly from api-gateway over `API_GATEWAY_URL` (`http://api-gateway.railway.internal:8080` on dev) -- no client-side proxy route and no CORS configuration, since these pages are read-only display, unlike `/demo`'s interactive-tool proxy pattern. Every fetch helper returns a discriminated `ApiResult<T>` (`ok`/`unauthenticated`/`not_found`/`error`, `apps/frontend/app/lib/api-types.ts`) so a page never conflates an empty result with a still-loading or error state.

**Real session architecture (Milestone 6):** M3's placeholder `pb_session_token` raw-cookie read (which never issued, refreshed, or validated anything itself -- its own docstring said so explicitly) is replaced by `@supabase/ssr`'s standard Next.js App Router pattern: `apps/frontend/app/lib/supabase/server.ts` (Server Components/Actions/Route Handlers) and `client.ts` (the one browser-side Supabase client, used only for `auth.*` calls -- this codebase never queries Supabase tables directly from the browser, every data read/write still goes through api-gateway). `middleware.ts` calls `supabase.auth.getUser()` on every navigable request -- deliberately `getUser()`, not `getSession()`, since it round-trips to Supabase Auth to revalidate the token rather than trusting whatever the cookie currently claims, catching a stale/tampered/expired session at the edge. `app/lib/api.ts`'s `callGateway` now reads the access token from the SSR session (`getSession().data.session.access_token`) instead of a bespoke cookie -- api-gateway's own contract is unchanged either way, it only ever wanted `Authorization: Bearer <supabase access token>` and lets `get_current_user` be the sole authority on validity. Root-entry routing (`/`) is a pure, independently-tested function (`resolveRootDestination`, `app/lib/auth.ts`) composed with two real reads (`auth.getUser()`, `GET /v1/user/profile`) -- signed-out → `/sign-in`; signed-in with `onboarding_completed_at` null → `/onboarding`; otherwise → `/today`.

---

## 3. Navigation & Information Architecture (v5.0 — superseded from the original 13-route table)

**Approved Phase 6 IA — five primary destinations, evidence-based against the real Phase 5 schema and the actual data the backend can serve today:**

| Route | Purpose | Primary Data Source |
|---|---|---|
| `/today` | **Default landing route.** Command-center digest — today's verdict (recommendation or passing state), a compact view of any additional recommendations, a light bridge to recent history | `recommendation_products`/`recommendation_legs` for the current slate, `master_refresh_runs` (freshness) |
| `/recommendations` | Full current recommendation feed | `recommendation_products`/`recommendation_legs` |
| `/recommendations/[displayId]` | Full detail across four progressive-disclosure layers | Product/legs + `recommendation_product_explanations`/`recommendation_leg_explanations` + `recommendation_agent_outputs` + `consensus_snapshots` |
| `/track-record` | The Playbook's own performance, honestly scoped to sample size | `recommendation_product_grade_events`/`recommendation_leg_grade_events` aggregation only — see §6 |
| `/history` | Past (graded/withdrawn) recommendations | Same grade-event tables |
| `/history/[displayId]` | Time Machine — the bettor-facing historical reconstruction | `reconstruct_recommendation_product()` (ai-orchestrator, already built and live-proven — Phase 5 Milestone 5.3), exposed via a new thin read route in Phase 6 |
| `/account` | Profile, tier/subscription status (read-only), a link into `/account/how-it-works`, sign-out | `user_profiles`, `subscriptions` (own row only, RLS-scoped) |
| `/account/how-it-works` | Reopenable core-concept education (Milestone 6) -- Confidence/Modeled Probability/EV/No Bet, the recommendation process, links to `/history` and `/track-record` | Static copy only, no data read beyond the auth check |
| `/onboarding` | First-session flow (Milestone 6) -- first-use education plus the one required field (`jurisdiction_state`), ends by depositing the user in `/today` | `user_profiles` via the existing `PATCH /v1/user/profile` |
| `/sign-in` | Signed-out entry point (Milestone 6) -- email/password sign-in and account creation via Supabase Auth directly, no second auth system | Supabase Auth only, no api-gateway call |

**`/chat` is deferred, not cut.** The v3.0 chat-first positioning (Volume 1 §1) remains the long-term product vision, but repository archaeology (2026-08-28) confirmed `conversation_messages` was never built and no NL Engine exists anywhere in the codebase — the entire backend this route would depend on is unimplemented. Building `/chat` UI now would be a non-functional shell. Phase 6 designs its future placement (nav slot, how it will eventually share data with `/today`) without building it; it becomes a functional route only once a dedicated NL Engine milestone exists. Dashboard and chat must read from the same underlying explanation-layer data when chat is eventually built — never become separate sources of truth.

**Routes removed relative to the original v1.0–v4.0 table, and why:** `/analytics`, `/ai-insights`, `/agent-performance` folded into `/recommendations/[displayId]`'s deepest layer and `/track-record` — `agent_performance_scores` has no live consumer and Elite per-agent deep-dive content lives in the recommendation detail's Layer 4, not a separate screen. `/performance` folded into `/track-record`, scoped down — `projected_user_performance`/`verified_user_performance` have zero writers anywhere in the codebase (no bet-slip verification pipeline exists), so a dedicated screen for them would launch permanently empty; this is future capability, not cut. `/market-monitor` removed — `market_monitoring_events` has no Phase 6 UI need identified against real backend capability. `/settings` and `/profile` folded into `/account`. `/subscription` folded into `/account`'s read-only tier display — no billing flow is in Phase 6 scope.

**Onboarding is dashboard-first (corrected from both prior versions of this table).** The v1.0–v3.0 body text said onboarding layers over `/dashboard`; the v3.0/roadmap language later said it layers over `/chat` instead, and the two were never reconciled. Resolved: onboarding leads into `/today` (chat has no backend to layer over). Onboarding is architected as its own route (`/onboarding`) rather than tightly coupled to one host screen, so it can be re-pointed if chat's landing-route status changes later without a rebuild.

**Milestone 6 implementation note:** `components/auth/AuthForm.tsx` (client) is the one sign-in/create-account form -- a two-tab (Sign In / Create Account) email+password form calling Supabase Auth directly (`signInWithPassword`/`signUp`), never a second auth system. `components/onboarding/OnboardingForm.tsx` (client, plain local state + a direct call to the `completeOnboarding` Server Action -- not `useFormState`/`useFormStatus`, which require a `react-dom` build this project's plain npm dependency doesn't export outside Next's own build pipeline; functionally identical, same pattern as `AuthForm`). `components/education/CoreConcepts.tsx` renders the four required concepts (Confidence, Modeled Probability, EV, No Bet) with a `compact` prop -- reused verbatim by both onboarding's first-use pass and `/account/how-it-works`, never two separate copies of the same copy. `components/account/AccountSummary.tsx` takes `subscription: ApiResult<SubscriptionData>` (not the unwrapped data) so an unauthenticated/error subscription read is never silently rendered as "no active subscription" -- each `ApiResult` kind gets its own honest branch, matching every other M3-M5 component's discriminated-result convention. `components/nav/AppNav.tsx` (server component, no active-route highlighting to avoid introducing client JS for a cosmetic detail) is the one persistent nav across `/today`, `/recommendations`, `/history`, `/track-record`, `/account` -- without it those five destinations were only reachable by typing a URL directly.

**Telegram future-proofing (HQ's explicit M6 requirement, not built this milestone):** no `telegram_user_id`/external-identity table exists yet and none is added here. The existing identity model already satisfies "don't force a second user later" without any schema change: `auth.users` (Supabase-managed) is the one canonical user id, `user_profiles.id` is a 1:1 FK to it, and every future external channel (a `telegram_identities` table, when that milestone is authorized) would simply FK to the same `auth.users.id` -- no redesign required, no code written toward it here.

---

## 4. Design System Foundations — Quant Broadcast / Desk Open (v5.0)

**Visual direction, approved by HQ:** Quant Broadcast — a deliberate combination of Quant Terminal (disciplined hierarchy, premium dark foundation, restrained accent system, strong numerical presentation) and Broadcast Desk (unmistakable sports identity, editorial typography, controlled motion/status energy). Explicitly not a Bloomberg-with-logos clone, not a generic SaaS dashboard, not a sportsbook/casino imitation, and not an endless grid of identical cards. The target reaction: "this feels like a serious sports intelligence command center," not "this looks like betting software."

**Approved execution: "Desk Open."** Of three stylistic executions explored within the Quant Broadcast direction — "Wire Desk" (leaner, closer to pure Quant Terminal restraint), "Desk Open" (the deliberate midpoint — bold headline/data typography on a disciplined dark foundation, a narrow but visible team-identity channel, motion reserved for real state transitions), and "Broadcast Prime" (more consumer-media energy, higher drift risk toward a sportsbook look) — HQ approved **Desk Open** as the system-wide direction. Wire Desk's restraint may still inform the deepest, densest transparency views (recommendation detail Layer 4); Broadcast Prime's energy is not part of the approved system.

**Implementation: CSS custom properties (design tokens), consumed by Tailwind config** — every color, spacing value, and radius gets a named token rather than a hardcoded value in component code, so changing a token in one place updates every consuming component. Token roles (structural, not final brand values — final palette/scale numbers are an M1 implementation decision, not committed in this document):
- **Typography roles:** `display` (verdict headlines), `data-numeral` (confidence/EV/price — tabular figures), `heading`, `body`, `label`/`meta`.
- **Spacing/radius:** a single consistent base-unit scale (replacing the ad hoc per-file inline styles found in the current `/demo` code); radius kept minimal/restrained — enough to distinguish card boundaries, not enough to read as a rounded consumer-app aesthetic.
- **Surface levels:** page / card / elevated-detail — gives the recommendation detail's four-layer progressive disclosure (§5) a real spatial hierarchy.
- **Color roles:** primary/secondary/meta text; one primary accent; a state triad (positive/negative/neutral — win/loss/push, confidence-floor pass/fail, freshness) kept structurally separate from a narrow team-identity color channel, so a team's brand color can never be mistaken for a state signal.
- **Motion:** communicates real state change only (a value updating on poll, a card transitioning to graded) — no continuous/ambient animation, since no server-push mechanism exists to justify implying continuous "live" activity (§2).

**Typography, icons:** Load via `next/font`. Icon set: a single consistent icon system used sparingly for state/category markers, not as a primary content carrier — numbers and text carry this product's actual information.

**Accessibility:** WCAG 2.1 AA floor (unchanged from prior versions of this section) — contrast must be deliberately verified given the dark foundation, not assumed.

---

## 5. Component Specifications (Data Contracts) — v5.0, rewritten against the real Phase 5 schema

The original component list (26+, Designer Guide reference) was written before Phase 5's product/leg/explanation/activation-snapshot layer existed. This section is rewritten against what that layer actually produces, and against a four-layer progressive-disclosure model rather than the original nine-question flat table.

### Recommendation Card
```typescript
type RecommendationCardProps = {
  displayId: string;                // recommendation_products.display_id
  recommendationType: 'single' | 'player_prop' | 'multiple_singles' | 'no_bet' | 'bankroll_preservation';
  // same_game_parlay/multi_game_parlay are schema-supported but structurally inactive — no
  // correlation/joint-probability logic exists anywhere; do not build parlay card variants
  selection?: { market: 'moneyline' | 'spread' | 'total' | 'prop'; team_or_player: string; line?: number };
  price?: { americanOdds: number };
  confidence?: number;               // recommendation_legs.final_aggregate_confidence, 0-1
  expectedValue?: number;            // recommendation_legs.ev_per_dollar
  oneLineSummary: string;            // recommendation_product_explanations.why_this_shape, headline-trimmed
  decidedAt: string;                 // recommendation_activation_snapshots.activated_at — see freshness note below
  status: 'active' | 'withdrawn';    // lifecycle only — see Milestone 2.1 grade note below, never overloaded with 'graded'
  grade: {                           // Milestone 2.1 — null for an ungraded product
    outcome: 'WIN' | 'LOSS' | 'PUSH' | 'VOID_NO_ACTION' | 'NOT_APPLICABLE' | 'MIXED_SETTLED';
    gradedAt: string;                 // original grade event's computed_at
    isCorrection: boolean;            // true renders a distinct "result corrected [date]" sub-label, never a silent badge swap
    correctedAt: string | null;       // the correction event's own computed_at, set only when isCorrection is true
  } | null;
  onOpen: (displayId: string) => void;
};
```
Layer 1 only — the fields visible before a user opens a recommendation. `no_bet`/`bankroll_preservation` variants render at equal visual weight to an active recommendation (§6) — they have no `selection`/`price`/`confidence`/`expectedValue`, and `oneLineSummary` carries the passing verdict's own reason. **Freshness note (Correction 2/HQ Final Decision 10):** `decidedAt` (`recommendation_activation_snapshots.activated_at`) is recommendation freshness and must never be labeled "updated"/"refreshed"/"last confirmed" — those words are reserved for source/intelligence freshness (`master_refresh_runs.completed_at`), a separate concept shown at the page level, not on the card. **Grade note (Milestone 2.1):** lifecycle status (`active`/`withdrawn`) and grade state are independent dimensions — a withdrawn product's `grade` may still be non-null, and an active product is very commonly `grade: null` (ungraded). `grade.outcome` is the API's already-resolved CURRENT outcome from the append-only correction chain (`recommendation_product_grade_events`) — the frontend never reconstructs that chain or derives `MIXED_SETTLED` from individual legs itself.

**No artificial ranking (HQ Final Decision 1).** No persisted cross-product rank/priority field exists anywhere in the schema (`recommendation_legs.leg_order` exists only for legs bundled inside one `multiple_singles` product, not across separate per-game recommendations). When exactly one qualifying recommendation exists for a slate, it may receive single-item hero treatment. When multiple exist, they render as an unordered semantic set — display order may use a neutral key (game start time, or `decidedAt`) but must never imply intelligence ranking, and no card may be labeled "top pick," "best bet," "#1," or equivalent.

### Recommendation Detail — four progressive-disclosure layers
```typescript
type RecommendationDetailProps = {
  layer1: RecommendationCardProps;   // same shape as the card, expanded
  layer2?: {
    strongestEvidence: string;                          // recommendation_leg_explanations.strongest_evidence
    biggestRisks: string;                                // .biggest_risks
    contributingAgents: { name: string; role: string }[]; // names/roles only — no raw output at this layer
    dataLimitation?: string;                              // shown only if material to this specific recommendation
  };
  layer3?: {
    whyNotOtherShapes: string;          // recommendation_product_explanations.why_not_other_shapes
    rejectedAlternatives: { candidateKey: string; marketType: string; selection: string; reasons: string[] }[];
    wouldChangeMindIf?: string;         // verbatim quote from the top supporting agent; null when none exists — never synthesized
    dataLimitations: string;            // full disclosure at this layer, regardless of materiality
  };
  layer4?: {
    agentContributions: { agentName: string; confidence: number; directionalLean: string; weightApplied: number }[];
    provenance: { modelName: string; provider: string; usedFallback: boolean; promptName: string; promptVersion: number }[];
    consensus: { aggregateConfidence: number; agreementVariance: number; finalAggregateConfidence: number; belowConfidenceFloor: boolean };
  };
};
```
Layer 4's `agentContributions` must be derived from live data on every render, never a hardcoded roster or count — the implemented committee is 12 agents, not the 22 Volume 4 §1 originally specified (Volume 1 v3.1, Volume 4 v5.10). Provenance (model/prompt/weight detail) lives only at Layer 4, never surfaced by default. `agreementVariance`'s threshold is `> 0.10` (Volume 4 v5.2), not the original, structurally-unreachable `0.25` this section previously implied via the Transparency Meter below.

### Time Machine (History Detail)
```typescript
type HistoryJourneyProps = {
  stages: {
    whatWeRecommended: { product: RecommendationCardProps; legs: RecommendationCardProps[] };
    whatWeKnew: { strategyVersion: string; activatedAt: string; agentSnapshot?: RecommendationDetailProps['layer4'] };  // provenance nested here, not default-visible
    whyWeLikedIt: RecommendationDetailProps['layer2'] & RecommendationDetailProps['layer3'];
    whatChanged: { hasChanges: boolean; lifecycleEvents: { eventType: 'ACTIVATED' | 'WITHDRAWN' | 'SOFT_DELETED'; timestamp: string; reason?: string }[] };
    whatHappened: { status: 'awaiting_reconciliation' | 'graded'; gradeHistory: { outcome: string; gradedAt: string; isCorrection: boolean }[] };
    finalResultReview: { status: 'awaiting_result' | 'result_available' | 'review_available'; review?: { outcomeSummary: string; whyItWonOrLost: string; learningNotes?: string } };
  };
};
```
**All six stages are structurally stable and always render (HQ Final Decision 3)** — a stage is never silently removed because it has no content; `whatChanged` with no lifecycle event beyond `ACTIVATED` renders "No material changes recorded," and `finalResultReview` renders its own honest waiting/available state rather than disappearing. Backed by `reconstruct_recommendation_product()` (ai-orchestrator, live-proven, Phase 5 Milestone 5.3) — this function already composes all of the above by FK read; Phase 6 needs only a thin route exposing it, not new reconstruction logic.

**Milestone 4 implementation note (v5.0.5):** built as `/history` (index) and `/history/[displayId]` (Time Machine), composing two already-authoritative reads rather than one combined endpoint -- `GET /v1/recommendations/{displayId}` (M2/M3, supplies `whatWeRecommended`/`whatWeKnew`/`whyWeLikedIt`) and `GET /v1/recommendations/{displayId}/reconstruction` (M2 proxy to the function above, supplies `whatChanged`/`whatHappened`/`finalResultReview`). No new backend route or reconstruction logic was added. **Temporal integrity (a new, explicit HQ M4 rule, stricter than this section's original text):** `whatWeRecommended` never renders the product's current `status`/`grade` fields even though the same `RecommendationCardProps`-shaped object carries them -- those are current/post-decision facts, deliberately withheld from the identity-only Stage 1 rendering; withdrawal appears only in `whatChanged` (as a real `WITHDRAWN` lifecycle event, if reconstruction actually has one), grading only in `whatHappened`/`finalResultReview` (from reconstruction's own append-only grade/review history, never the live `grade` field). All six stages render simultaneously (not "one stage expanded at a time" as originally sketched) with per-stage `<details>` disclosures for deep provenance content (Stage 2's committee snapshot, Stage 5's per-leg grading) -- a deliberate refinement once "dense technical information does not dominate the initial view" (HQ's M4 wording) was implemented against real content, not a contradiction of the stepper concept itself.

### AI Transparency / Consensus Summary (replaces the original Transparency Meter — Layer 4 only)
```typescript
type ConsensusSummaryProps = {
  aggregateConfidence: number;
  agreementVariance: number;        // threshold: > 0.10 (Volume 4 v5.2), not the original 0.25
  belowConfidenceFloor: boolean;
  dataLimitations: string[];        // e.g. sharp money / public betting / referee tendencies — permanently unavailable, disclosed, never shown as zero/neutral
};
```
The original `evidence_strength`/`data_quality` dimensions (v2.0) are not carried forward as separate 0-1 scores — no code in the implemented pipeline computes either as a standalone value; both are represented instead through the honest per-field data-limitation disclosures already produced by `app.features.explainability` (Volume 4 §8). Rendered qualitatively at Layer 4, with underlying numbers available on request — never as a headline metric.

### Track Record Summary
```typescript
type TrackRecordCounts = { win: number; loss: number; push: number; voidNoAction: number; mixedSettled: number };

type TrackRecordSummaryProps = {
  sampleSize: number;                                        // count of graded recommendation_products — CATEGORY A
  record: TrackRecordCounts;                                 // product-level outcome tally — CATEGORY B
  byRecommendationType: Record<string, TrackRecordCounts & { sampleSize: number }>;  // CATEGORY B
  sampleStatus: 'zero' | 'low' | 'mature';
};
```
**Implementation note (Milestone 5, v5.0.6):** the shape above is `GET /v1/track-record`'s real response (unchanged since Milestone 2) — this corrects the pre-M5 sketch, which omitted `mixedSettled` from both `record` and `byRecommendationType`, and omitted the per-type `sampleSize`. Both are real fields the route has always returned; only this document's sketch was out of date. `/track-record`'s `TrackRecordSummary` component filters `byRecommendationType` to entries with `sampleSize > 0` before rendering — the route's handler creates a zero-sample entry for every recommendation type that appears in a graded row, including `no_bet`/`bankroll_preservation` (which are graded `NOT_APPLICABLE` and never tallied), so an unfiltered render could show a `{win:0, loss:0, ...}` row for those two types that reads as a losing streak. This is a frontend-only filter, not a backend change — HQ's M5 authorization scoped this milestone to the presentation layer. No win-rate or other derived percentage is computed anywhere in this component; the API returns none, so none is shown (HQ's explicit M5 STOP condition) — raw counts only, with `sampleSize`/`sampleStatus` always visible ahead of the record itself so a low sample can never read as an established performance history.

**Unit of observation is the recommendation PRODUCT, never the leg (HQ Final Decision 2).** "N graded recommendations" means N graded `recommendation_products`; a `multiple_singles` product's individual legs are never counted into this denominator. If leg-level performance is ever shown, it must use its own explicitly-labeled component ("Individual Picks"/"Legs") with its own separate denominator — never blended into this one. **Explicitly excluded from this component and from Phase 6 entirely:** units, ROI, EV realization, CLV, modeled-probability calibration, projected-user performance, verified-user performance — all Category C (no live writer/computation exists for any of them). No placeholder charts for these in the production UI.

### Charts
A charting library is a Phase 6 M1 dependency decision (record it when made — see §2). **The separation rule survives unchanged regardless of library:** AI performance, projected performance, and verified performance must remain separate series/charts, never blended into one line — moot for Phase 6's actual scope today, since `projected_user_performance`/`verified_user_performance` have zero writers (§3), but binding the moment those become real.

---

## 6. Key Screen States (v5.0)

### No Bet Today vs. Bankroll Preservation — first-class product outcomes, not empty states
Both are mechanically distinct, real `recommendation_type` values (`no_bet` per-game, `bankroll_preservation` slate-wide with source-product provenance via `recommendation_activation_snapshot_source_products`) and must receive equal visual weight to an active recommendation — never a smaller/grayed-out card, never "no data available" framing. Headline reads as a decision (e.g. "The Playbook Is Passing Today"), followed immediately by the real reason from `recommendation_product_explanations.why_this_shape`. No language that pressures the user to find a bet anyway.
- **No Bet Today** (single game/market didn't clear the confidence floor): show the full explanation anyway — the "why not" reasoning is the actual product experience here.
- **Bankroll Preservation** (broad market conditions unfavorable): framed at the slate level, not about any single game. A count of underlying source products may be shown only if repository inspection at implementation time confirms a reliable one-to-one mapping to unique games for that specific product shape — do not derive a "games reviewed" figure from an assumption; omit the count or use accurate terminology if that mapping isn't guaranteed.

### Unavailable-data UX
Honest disclosure (sharp money, public betting, referee tendencies, CLV, unsupported historical variance — all permanently unavailable per Volume 4 §8's `ALWAYS_UNAVAILABLE_DISCLOSURE`) must never be represented as zero or neutral. But a missing input becomes a visible dashboard element only when it materially affects the specific recommendation/explanation being shown, or when the user opts into deeper transparency (Layer 3/4) — not a permanent banner. There is a difference between honest disclosure and making the product's limitations the product.

### Tier / Entitlement UX
RLS silently filters tier-gated rows entirely — an under-tiered user's client never receives them and never receives their `min_required_tier` value either, so the row's absence carries no "why." Phase 6 exposes only the authenticated user's own `subscriptions.tier`/`status` (thin, RLS-scoped read) for account display. **No locked-content/paywall UI** ("Upgrade to see this Elite recommendation," inferred upgrade prompts) is built — that would require inventing a new existence-check mechanism, which is new business logic, out of scope. The product simply renders whatever recommendations the authenticated user is actually authorized to receive.

### Onboarding Flow — dashboard-first (corrected, v5.0)
Prior versions of this section said onboarding layers over `/dashboard` (v1.0–v2.0 body text) or `/chat` (later v3.0/roadmap language) without ever reconciling the two. **Resolved: onboarding is dashboard-first** — it collects only `jurisdiction_state` (the one field the existing `PATCH /v1/user/profile` contract actually requires; this document makes no legal-necessity claim beyond that contract) and deposits the user into `/today` on completion. The other profile fields the original four-step flow collected (`risk_tolerance`, `preferred_unit_size`/`optional_bankroll`, `persona_classification`, `betting_experience`, `primary_goal`, `max_parlay_legs`) have no current product consumer — no personalized-stake writer or parlay logic exists yet to act on them — and move to `/account` as optional, later settings rather than first-session friction. Onboarding is built as its own route, not tightly coupled to one host screen, so it can be re-pointed at `/chat` later without a rebuild once an NL Engine exists.

---

## 7. Notifications & SMS — FUTURE CAPABILITY, not Phase 6 scope (v5.0)

Repository archaeology (2026-08-28) confirmed no `notifications` table exists in any migration — the schema below remains a proposal, never built. Explicitly out of Phase 6: no notification UI, no preference toggles with nothing to write to. This section is retained as the design intent for a future notifications milestone.

```sql
create table notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel text check (channel in ('push','sms','email','in_app')),
  notification_type text check (notification_type in
    ('new_recommendation','recommendation_withdrawn','market_alert','no_bet_today','postgame_review_ready')),
  content text,
  linked_recommendation_id uuid references recommendations(id),
  sent_at timestamptz,
  read_at timestamptz,
  created_at timestamptz default now()
);
```

**SMS via Twilio**, reserved for time-sensitive events only (new recommendation, market alert on an active bet) — not every notification type, to avoid the product feeling spammy on a channel users can't easily mute per-category the way they can with in-app notifications. In-app and push cover the rest. Twilio conversation flow should reuse the same NL Engine intent classification from Volume 4 §7 — a user replying to an SMS recommendation alert with "give me something safer" should route through the same pipeline as typing it in the `/chat` web interface, not a separate SMS-only logic path.

---

## 8. Responsive & Accessibility Requirements

**Responsive breakpoints (v5.0 — split by content, not one blanket mobile-first rule):** mobile-priority for `/today`, recommendation cards, and Layers 1–2 of the detail view, given Persona B (Volume 1's Casual Weekend Bettor) is likely checking recommendations on their phone during a live Sunday slate; desktop-optimized for Layers 3–4, Time Machine's full reconstruction, and Track Record's denser views, which carry real data density that degrades badly if forced mobile-first. One responsive system, not two parallel component trees — density/layout adapts per breakpoint within each component.

**Accessibility baseline:** WCAG 2.1 AA as the floor — sufficient color contrast (especially important given the dark, premium-financial palette direction from the Designer Guide, which can easily under-contrast if not checked), keyboard navigation through the recommendation feed and chat interface, and screen-reader labels on all icon-only buttons (filter icons, notification bell, etc.) since the component list leans icon-heavy per the Designer Guide's icon-style requirement.

---

## 9. Cross-Volume Consistency Check (v5.0 re-review)

Re-checked against the real Phase 4-5 implementation (2026-08-28), not just the other volumes' text:

- **Pricing tiers (Vol 1 v3.1) ↔ RLS enforcement (Vol 3 v4.24) ↔ tier UX (§6):** consistent — `subscriptions.tier` is the single source of truth; Phase 6 renders only what RLS actually returns, no inferred paywall logic layered on top.
- **"No Bet Today"/Bankroll Preservation as valid, celebrated outputs (Vol 1) ↔ schema (Vol 3 §5A) ↔ consensus logic (Vol 4) ↔ UI treatment (§6):** consistent — both are first-class `recommendation_type` values end to end.
- **Elite "priority agent compute" (Vol 1) ↔ concrete mechanism (Vol 4 §4.3, corrected threshold `> 0.10`):** consistent — §5's Consensus Summary component now reflects the corrected value, not the original unreachable `0.25`.
- **12-agent reality (Vol 4 §8 v5.6, Vol 1 v3.1) ↔ this volume's component contracts (§5):** now consistent — §5's `agentContributions` is explicitly required to derive from live data, never a hardcoded count.
- **Performance attribution separation (Vol 3 §6) ↔ Track Record scope (§5/§6):** consistent, and now correctly scoped down — units/ROI/EV/CLV/calibration/projected/verified performance are Category C (no writer exists), excluded from Phase 6 rather than assumed available.

**One contradiction found and resolved by this pass:** onboarding's host screen (`/dashboard` per v1.0-v2.0 text vs. `/chat` per later v3.0/roadmap language) was never reconciled prior to this review — resolved in §6 as dashboard-first.

---

## 10. What's Still Open (Honest Accounting, v5.0)

- The 0.55 confidence threshold (Volume 4) remains a launch default pending backtesting; the ±10% adaptive-weighting guardrail is confirmed still propose-only (Volume 4 v5.9) — neither is Phase 6 scope.
- Chat (`/chat`, the NL Engine, `conversation_messages`) remains fully unbuilt — deferred, not cut (§3). Its future placement is designed, not implemented, in Phase 6.
- The Dashboard UX/UI Design Brief / Designer Onboarding Guide referenced by this volume's prior versions remains an unresolved external artifact gap — never located in this repository (see the header note above).
- Legal/compliance review (Volume 1 §10) is still a pre-launch to-do, not yet resolved by any volume.
- Pre-launch backtesting (Volume 4 §11) is scoped but not yet executed.
- `user_recommendation_selections` (personalized Kelly stake/risk display) has schema but zero writers — explicitly carried forward as an unplaced future capability (HQ Final Decision 5 on Phase 6 planning), not assigned to any phase as of this version. Phase 6 may show existing recommendation-level risk fields only, never compute or approximate a personalized stake.
- Authoritative cross-product recommendation ordering/display sort (when multiple recommendations exist on one slate) was flagged as genuinely open during Phase 6 planning (Pass 3 §8) and needs an explicit HQ decision before `/today`/`/recommendations` display-order is finalized — no rank field is persisted anywhere in the schema today.

---

## 11. API Read Contracts (Phase 6 Milestone 2 -- v5.0.2; grade field added by Milestone 2.1 -- v5.0.3; reconstruction shape documented by Milestone 4 -- v5.0.5)

Every route below is a thin, read-only exposure of already-existing Phase 1-5 data/logic (`apps/api-gateway`) -- none computes a probability, EV, stake, ranking, or new explainability. Auth: bearer JWT via the existing `get_current_user` dependency on every route.

| Route | Purpose | Tier-gating | Data source |
|---|---|---|---|
| `GET /v1/recommendations/today` | Today's cards (§2), including `grade` | Per-row, mirrors `recommendation_products_tier_gated_select` | `recommendation_products`/`recommendation_legs`, `games`, `master_refresh_runs`, activation snapshots, `recommendation_product_grade_events` |
| `GET /v1/recommendations` | Broader feed (`since`/`until`/`limit`), including `grade` | Same | Same |
| `GET /v1/recommendations/{displayId}` | Layers 1-4 detail (§5), including `grade` | Same (404, not 403, when ungated) | + explanations, `recommendation_agent_outputs`, `agents`, `consensus_snapshots` |
| `GET /v1/recommendations/{displayId}/reconstruction` | Time Machine | Same | Proxies `ai-orchestrator`'s internal wrapper around `reconstruct_recommendation_product` (Milestone 5.3) -- reused verbatim, never rebuilt here |
| `GET /v1/track-record` | Sample size + product-level W/L/P/V + type breakdown (§6) -- A/B metrics only | Applied to the underlying grade-event aggregation itself (a free user's aggregate never reflects Elite-only rows) | `recommendation_product_grade_events` (latest per product, correction-aware) |
| `GET /v1/user/subscription` | Own tier/status only | N/A (own row) | `subscriptions` |
| `GET /v1/user/profile` | Own profile row (Phase 2 Milestone 4, first consumed by a frontend page in M6) | N/A (own row) | `user_profiles`, raw row verbatim (`response.json()[0]`) -- snake_case, not renormalized to camelCase, the same real-contract-not-renormalized pattern already documented for the reconstruction route above |
| `PATCH /v1/user/profile` | Onboarding completion (Phase 2 Milestone 4). M6's form sends only `jurisdiction_state`; every other optional field on the route's own schema is left unset | N/A (own row) | `user_profiles`, sets `onboarding_completed_at` server-side |

**Neutral ordering (HQ Final Decision 1):** game-scoped cards order by `games.scheduled_start`; slate-scoped cards (no single game) fall back to `recommendation_activation_snapshots.activated_at`. Never EV or confidence. No response field is named or implies "primary"/"top"/"best" -- multiple same-day recommendations are an unordered-by-intelligence set with a neutral chronological display order.

**Freshness (HQ Final Decision 10):** `decidedAt` on every card is `activated_at` -- recommendation decision time. Source/intelligence freshness (`master_refresh_runs.completed_at`) is a separate, page-level concept this API doesn't attach to individual cards. No response anywhere uses a generic `updatedAt`.

**Track Record scope, precisely (HQ Final Decision 2/5):** `sampleSize`/`record` count `WIN`/`LOSS`/`PUSH`/`VOID_NO_ACTION`/`MIXED_SETTLED` only -- `NOT_APPLICABLE` (no_bet/bankroll_preservation) and `PENDING_MISSING_DATA` are excluded entirely, not zero-filled. `MIXED_SETTLED` (the real, wired `multiple_singles` product-level outcome) is its own bucket, never folded into `win`/`loss`. The unit of observation is always the product, via de-duplication on the latest `computed_at` per `recommendation_product_id` (so a correction supersedes, never double-counts). `sampleStatus` (`zero`/`low`/`mature`) uses a disclosed n=30 threshold -- a conventional statistical minimum, not a Blueprint-derived value; open to revision. Units/ROI/EV/CLV/calibration/projected/verified performance remain absent -- no live writer exists for any of them.

**Grade contract (Milestone 2.1):** the three product routes above (`/today`, `/recommendations`, `/{displayId}`) each carry an additive `grade` field, `null` for an ungraded product, otherwise `{outcome, gradedAt, isCorrection, correctedAt}` sourced from `recommendation_product_grade_events`. `recommendation_products.status` is unchanged and never carries a `'graded'` value -- lifecycle status and grade state are independent dimensions. The current-outcome resolution reuses the exact rule already established by `GET /v1/track-record` (this same table's correction chain is append-only, so the latest row by `computed_at` is authoritative) -- no second resolution algorithm was written. Per-leg grade exposure was inspected and not added: no field in this volume's approved card or four-layer detail contracts reads a per-leg outcome, and `MIXED_SETTLED` is already the authoritative product-level value the API returns verbatim, never derived from legs by the frontend.

**Reconstruction route field shape (Milestone 4):** unlike every other route in this table, `GET /v1/recommendations/{displayId}/reconstruction` returns `dataclasses.asdict(ReconstructedProduct)` verbatim (ai-orchestrator, `app.orchestration.reconstruction`) -- raw snake_case Supabase column names, not the camelCase convention every other route follows. HQ's M2 close-out "PUBLIC CONTRACT COUPLING NOTE" applies: this shape is a declared public contract, not refactored for casing consistency. Top level: `product`, `activation_snapshot`, `strategy_version`, `product_explanation`, `legs[]` (each `{leg_order, leg, explanation, grade_history[], current_grade, weighting_evidence[]}`), `source_products[]` (bankroll_preservation only), `user_selection`, `lifecycle_events[]`, `product_grade_history[]`, `current_product_grade`, `postgame_reviews[]`. Every history array is oldest-first and never collapsed -- a correction is a new row, the original is never removed. `apps/frontend/app/lib/api-types.ts` mirrors this exactly (`Reconstruction*` types).

**A real gap in the underlying RLS policy, found and preserved, not fixed:** `recommendation_products_tier_gated_select` only special-cases `min_required_tier in ('free','pro','elite')` -- a hypothetical `'syndicate'` value (schema-permitted, never set by any code) would be denied to every caller, including a syndicate subscriber, since neither the `free` branch nor either `exists` sub-clause matches it. `app.entitlement.tier_permits` (api-gateway) mirrors this literally rather than "fixing" it, since fixing it in the API would expose more than the database's own real policy currently does. Dormant today; flagged for whoever eventually assigns `min_required_tier='syndicate'` to a row.

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05, Volume 5 added. **All five volumes of the initial blueprint pass are now complete.** Updated to v2.0, 2026-08-05, per external architecture review — AI Transparency Meter and Recommendation Timeline (§5) integrated as full component specs, not just noted in the version header. Updated to v3.0, 2026-08-05 — `/chat` as default landing route (§3) and chat-context Recommendation Card rendering (§5) integrated directly. Updated to v4.0, 2026-08-06 — `data_quality` (§5) tied to the concrete metadata convention, per the internal markdown-consistency review. Updated to v5.0, 2026-08-28 — full structural rewrite against the real Phase 4-5 product/explanation/grading schema and the three-pass, HQ-approved Phase 6 Product/UX architecture; see the v5.0 header note and `CHANGELOG.md` v5.0 entry for full reasoning. Updated to v5.0.3, 2026-08-31 — Milestone 2.1 additive grade contract correction; see the v5.0.3 header note and `CHANGELOG.md` v5.0.3 entry. Updated to v5.0.4, 2026-08-31 — Milestone 3 (Core Recommendation Experience) implementation; see the v5.0.4 header note and `CHANGELOG.md` v5.0.4 entry. Updated to v5.0.5, 2026-08-31 — Milestone 4 (History / Time Machine) implementation; see the v5.0.5 header note and `CHANGELOG.md` v5.0.5 entry.
