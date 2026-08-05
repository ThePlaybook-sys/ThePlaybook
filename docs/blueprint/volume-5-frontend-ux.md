# The Playbook — Volume 5
## Frontend & UX Architecture: Dashboards, Navigation, Components, Notifications, Onboarding, Accessibility

**Version:** v2.0
**Last updated:** 2026-08-05
**Depends on:** Volume 1 (v2.0 — personas, tiers, journeys), Volume 2 (v2.0 — API contracts, scoped event system), Volume 3 (v2.0 — data shapes), Volume 4 (v2.0 — explainability mapping, recommendation states, evidence classification)
**v2.0 note:** Amended per external architecture review — AI Transparency Meter (extends Explainability Panel) and Recommendation Timeline (powered by the new event system) added as components. See `v2.0-amendments-architecture-review.md` §4 for full detail.
**Companion document:** The separate Designer Onboarding Guide (PDF, non-technical) covers the same component list from a visual-design perspective — this volume covers the same ground from an engineering/data-contract perspective. The two should never contradict each other; if the designer's Figma work suggests a change to a component's data needs, that change comes back here first.

---

## 1. How This Volume Closes the Loop

Every prior volume built toward something the user sees. This volume is where that finally happens: Volume 1's personas and journeys become actual screens, Volume 3's tables become actual props and API responses, and Volume 4's 21-agent consensus becomes a recommendation card someone can read in three seconds. Nothing here should introduce a new product decision — this is the volume that renders decisions already made.

---

## 2. Frontend Stack & Architecture

**Framework:** Next.js (App Router) + React, per the master spec. Server Components for anything that doesn't need interactivity (static layout, marketing pages), Client Components for anything stateful (recommendation feed, chat interface, dashboards with live data).

**Data fetching:** Server-side fetch for initial page load (fast first paint, good for the "first recommendation, same session" onboarding requirement from Volume 1 §6), with React Query on the client for anything that needs revalidation — recommendation status changes, market monitoring updates, notification badges.

**Real-time updates:** Supabase Realtime subscriptions for two specific cases where polling would feel laggy: (1) a recommendation's status flipping from `active` to `withdrawn` mid-session because the Market Monitoring Engine caught a change (Volume 3 §7), and (2) live game status updates during an active slate. Everything else uses standard fetch/revalidate — reserve real-time subscriptions for cases where a delay would visibly confuse the user, not as a default pattern everywhere.

**State management:** React Query handles server state (recommendations, user profile, subscription status). Local UI state (modal open/closed, filter selections) uses React's built-in state — no separate global state library needed at this scale; introducing one before it's needed adds complexity Volume 2's "small team" reality (Section 5) doesn't benefit from.

---

## 3. Navigation & Information Architecture

Matches the page list from Volume 1 §10, now with routes and primary data source:

| Route | Purpose | Primary Data Source |
|---|---|---|
| `/dashboard` | Landing view after login — today's recommendation(s) or No Bet Today state | `/v1/recommendations` (Volume 2 §6) |
| `/recommendations` | Full current recommendation feed, filterable | `/v1/recommendations` |
| `/recommendations/[id]` | Full detail + explainability for one recommendation | `/v1/recommendations/{id}/explain` |
| `/games` | Upcoming/live game browser | Sports Intelligence Layer via Gateway |
| `/analytics` | ROI/EV/CLV charts (Section 6) | `ai_performance`, `verified_user_performance` (Volume 3 §6) |
| `/performance` | Personal projected vs. verified performance | `projected_user_performance`, `verified_user_performance` |
| `/ai-insights` | Agent-level performance, calibration | `agent_performance_scores` (Volume 3 §5) |
| `/agent-performance` | Deep-dive per-agent view (Elite feature per Volume 1 §2) | Same, gated by tier |
| `/recommendation-history` | Past recommendations, settled outcomes | `recommendations` where status begins with `settled_` |
| `/market-monitor` | Live feed of market events affecting active recommendations | `market_monitoring_events` (Volume 3 §7) |
| `/settings` | Profile, notification prefs | `user_profiles` |
| `/profile` | Betting DNA, persona | `betting_dna` |
| `/subscription` | Tier, billing | `subscriptions` |
| `/chat` | Natural language interface | `conversations` / `conversation_messages` (Volume 4 §7) |

**Onboarding is not a route in this table on purpose** — per Volume 1 §6, it's a modal/overlay flow layered on top of `/dashboard` on first login, not a separate page a user navigates away from and might abandon mid-flow.

---

## 4. Design System Foundations (Engineering Layer)

The Designer Onboarding Guide (companion PDF) covers brand personality decisions (color, type, corner radius, shadows) from a design perspective. This section defines how those decisions get implemented so they stay a single source of truth rather than drifting between Figma and code.

**Implementation: CSS custom properties (design tokens), consumed by Tailwind config.** Every color, spacing value, and radius the designer defines in Figma gets a named token (`--color-brand-primary`, `--radius-card`, `--space-md`) rather than a hardcoded value anywhere in component code. This is the direct technical reason the LEGO/component-library analogy in the designer guide actually holds up in code: changing a token in one place updates every component using it, matching the promise made in that document.

**Typography, icons:** Load via `next/font` for performance (no external font CDN calls at runtime — matters for reliability during high-traffic game windows). Icon set: whichever style the designer locks in (Section 4, Designer Guide) implemented as a single icon component library, not mixed sources.

---

## 5. Component Specifications (Data Contracts)

The Designer Guide lists 26+ components without specifying exact data shape on purpose — that's this section's job. A representative set, matched to what Volume 3/4 actually produce:

### Recommendation Card
```typescript
type RecommendationCardProps = {
  id: string;
  type: 'single' | 'player_prop' | 'same_game_parlay' | 'multi_game_parlay' | 'multiple_singles' | 'no_bet';
  team_or_player?: string;
  bet_details?: BetDetails;      // null when type === handled as No Bet Today state, Section 6
  confidence: number;             // 0-1, from consensus_snapshots
  expected_value: number;
  risk_level: 'low' | 'moderate' | 'high';
  short_explanation: string;      // from explainability_payloads.why_this_recommendation, truncated
  status: 'active' | 'withdrawn' | 'settled_win' | 'settled_loss' | 'settled_push';
  onViewDetails: (id: string) => void;
};
```
Directly implements Volume 4 §8's explainability mapping — `short_explanation` on the card is the entry point, and `onViewDetails` routes to `/recommendations/[id]`, which renders the full nine-question explainability breakdown from that same section.

### Game Card
```typescript
type GameCardProps = {
  home_team: string; away_team: string;
  home_logo_url: string; away_logo_url: string;
  scheduled_start: string;        // ISO timestamp
  status: 'scheduled' | 'live' | 'final';
  primary_line: { spread?: number; total?: number; moneyline?: [number, number] };
  weather_flag?: 'indoor' | 'clear' | 'wind' | 'precipitation';
  injury_flag?: boolean;          // true if any notable injury exists — detail on tap, not shown inline
};
```

### Explainability Panel (new — not in the original component list, needed to implement Volume 4 §8)
```typescript
type ExplainabilityPanelProps = {
  why_this_recommendation: string;
  why_this_bet_type: string;
  why_now: string;
  why_not_alternatives: string;
  strongest_evidence: string;
  biggest_risks: string;
  invalidating_conditions: string;
  contributing_agents: { name: string; weight: number; directional_lean: string }[];
  persona_fit_explanation: string;
};
```
This is a new component beyond the Designer Guide's original list — a direct consequence of Volume 4 §8's explainability mapping requiring a place to live. Flagged explicitly since the Designer Guide didn't anticipate it; the designer should be looped in on this addition before final screen design.

### AI Transparency Meter (v2.0 — extends Explainability Panel)
```typescript
type TransparencyMeterProps = {
  confidence: number;                       // existing, from ExplainabilityPanelProps' source data
  evidence_strength: number;                // 0-1, derived from % of contributing findings classified data_backed (Volume 4 §2.1)
  agent_agreement: number;                  // 0-1, derived from agreement_variance (Volume 4 §4.1), inverted so higher = more agreement
  data_quality: number;                     // 0-1, derived from Sports Intelligence Layer cache freshness at recommendation time
};
```
Added per the external architecture review — shows four dimensions instead of confidence alone, rendered as part of the same Explainability Panel rather than a separate screen, since it's answering the same underlying question ("how much should I trust this") from a different angle. `evidence_strength` and `data_quality` are new derived values with no existing UI home before this addition — flag both to the designer alongside the Explainability Panel itself.

### Recommendation Timeline (v2.0 — powered by Volume 2 §4.5's event system)
```typescript
type RecommendationTimelineProps = {
  recommendation_id: string;
  events: { event_type: string; timestamp: string; detail: string }[];
};
```
Populated by querying the events tied to a `recommendation_id` from Volume 2 §4.5's scoped event system. At MLP stage this means `RecommendationCreated`, `RecommendationUpdated`, and `RecommendationWithdrawn` only — matching the MLP-stage event list in that section, not the full deferred list. This is a case where two review suggestions turned out to be one feature: the event system and this timeline were proposed separately but the timeline is essentially a direct rendering of the event stream, so building one without the other doesn't make sense.

### Charts
Recharts-based (per available frontend libraries), fed directly from the query patterns implied by Volume 3 §6's three separate performance tables — **the chart layer must keep AI performance, projected performance, and verified performance as separate chart series or separate charts entirely, never blended into one line,** mirroring the database-level separation for the same reason (Volume 3 §6): blending them visually would misrepresent verified results as validated by more data than it actually is.

---

## 6. Key Screen States

### No Bet Today vs. Bankroll Preservation (Volume 4 §12 — two distinct states, not one empty state)
Both need dedicated, non-generic UI treatment per Volume 1 §7's Journey 1 finding that this is the highest-churn-risk moment in the product:
- **No Bet Today** (single game/market didn't clear the confidence floor): show the explainability panel anyway — the "why not" reasoning is the actual product experience here, not an apology.
- **Bankroll Preservation** (broad market conditions unfavorable): a different message entirely — framed at the portfolio level ("today's slate doesn't offer a favorable risk/reward setup") rather than about any single game.

### Onboarding Flow (Volume 1 §6, four steps)
Implemented as a full-screen modal sequence over `/dashboard`, ending in the first real recommendation (or one of the two states above) rendered live, in the same session — this is a hard product requirement, not a nice-to-have, so the engineering task list should treat "first recommendation renders before onboarding modal closes" as a defined completion criterion, not an afterthought.

---

## 7. Notifications & SMS

Resolves the notification schema gap noted at the end of Volume 3.

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

**Responsive breakpoints:** mobile-first, given Persona B (Volume 1's Casual Weekend Bettor) is likely checking recommendations on their phone during a live Sunday slate. Dashboard and recommendation feed need to work well at narrow widths before desktop polish — the reverse priority of how these projects often default.

**Accessibility baseline:** WCAG 2.1 AA as the floor — sufficient color contrast (especially important given the dark, premium-financial palette direction from the Designer Guide, which can easily under-contrast if not checked), keyboard navigation through the recommendation feed and chat interface, and screen-reader labels on all icon-only buttons (filter icons, notification bell, etc.) since the component list leans icon-heavy per the Designer Guide's icon-style requirement.

---

## 9. Cross-Volume Consistency Check (End-of-Blueprint Review)

With all five volumes complete, this is the review the versioning system (Section-level changelog discipline across Volumes 1–4) was built to support. Checked for contradictions:

- **Pricing tiers (Vol 1) ↔ RLS enforcement (Vol 3) ↔ rate limiting (Vol 2):** consistent — tier is the single source of truth in `subscriptions`, referenced identically in all three places.
- **"No Bet Today" as a valid, celebrated output (Vol 1) ↔ schema representation (Vol 3) ↔ consensus logic (Vol 4) ↔ UI treatment (Vol 5):** consistent — it's a first-class `recommendation_type` value end to end, never an absence of data.
- **Elite "priority agent compute" (Vol 1 pricing language) ↔ concrete mechanism (Vol 4 §4.3):** consistent, and now has a real technical definition instead of vague marketing language.
- **Performance attribution separation (master spec) ↔ Vol 3 three-table schema ↔ Vol 5 charting rule (Section 5):** consistent all the way through — this was checked specifically because it's the master spec's most emphatic "never mix these" instruction, and it holds at every layer.

No contradictions found requiring a MAJOR version bump across the set. All five volumes are internally consistent as of this v1.0 pass.

---

## 10. What's Still Open (Honest Accounting)

- The 0.55 confidence threshold and ±10% weight cap (Volume 4) are launch defaults pending backtesting — will trigger a MINOR bump to Volume 4 once real numbers exist, and Volume 5's UI copy around confidence should be reviewed at that point too.
- The Explainability Panel component (Section 5) is new relative to the original Designer Guide component list — loop the designer in before final screen designs lock.
- Legal/compliance review (Volume 1 §10) is still a pre-launch to-do, not yet resolved by any volume.
- Pre-launch backtesting (Volume 4 §11) is scoped but not yet executed.

---

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05, Volume 5 added. **All five volumes of the initial blueprint pass are now complete.** Updated to v2.0, 2026-08-05, per external architecture review — AI Transparency Meter and Recommendation Timeline (§5) integrated as full component specs, not just noted in the version header.
