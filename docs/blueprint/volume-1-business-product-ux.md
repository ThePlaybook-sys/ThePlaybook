# The Playbook — Volume 1
## Business, Product Vision, User Experience, Pricing, Customer Journeys

**Version:** v3.0
**Last updated:** 2026-08-05
**Status:** Foundational — downstream volumes inherit these decisions
**Depends on:** Master Prompt (source spec)
**v3.0 note:** Chat-first positioning confirmed in §1 — `/chat` is now the default landing surface, dashboard is the reference library. See `v3.0-amendments-conversational-intelligence.md` §1 for full reasoning.
**Read next:** Volume 2 (System Architecture) once this is locked

---

## 1. Executive Summary

The Playbook is an AI Betting Operating System, not a picks app. The distinction matters commercially: picks apps compete on win rate and get commoditized fast; operating systems compete on trust, transparency, and long-term measurable ROI, which is a much harder moat to copy. Every decision in this volume optimizes for that positioning.

The business only works if two things are true simultaneously:
1. The AI is honest enough to say "No Bet Today" often, even though that's the moment users are most tempted to churn.
2. The product makes that honesty feel like value, not withholding.

Everything below — pricing, onboarding, personas, journeys — is built around solving that tension.

**Conversational-first, dashboard-second (v3.0).** The primary experience is texting an elite analyst, not opening a dashboard. The dashboard still exists — recommendation history, analytics, settings, all of it — but it's the reference library, not the front door. This isn't a new principle so much as a sharpening of one that was already implicit: an "operating system" people actually use daily looks and feels like a conversation, not a spreadsheet with a chat feature bolted on. Volume 5 reflects this directly — `/chat` is the default landing route post-login, not `/dashboard`.

---

## 2. Business Model

**Recommendation: Subscription-first, not pay-per-pick.**

Pay-per-pick (à la carte) rewards volume, not accuracy — it pressures the AI Orchestrator to generate recommendations even on low-conviction days, which directly contradicts the "No Bet Today" principle in the master spec. A subscription removes that incentive conflict entirely: the platform gets paid the same whether it recommends five bets or zero, so there's no commercial pressure fighting the AI's honesty. This is the single most important business-model decision in the blueprint, because it's the thing that keeps every other module honest.

### 2.1 Tier Structure

| Tier | Price (recommend) | Who it's for | Unlocks |
|---|---|---|---|
| **Free / Scout** | $0 | Trial, lead gen | Daily consensus summary only (no individual agent breakdown), 1 sport, delayed line data (15 min), no bet slip verification |
| **Playbook Pro** | $39–49/mo | Core paying user | Full recommendation engine, all agents, explainability, real-time lines, all launch sports, Betting DNA profile, bet slip OCR |
| **Playbook Elite** | $99–149/mo | Serious/high-volume bettor | Everything in Pro + parlay construction tools, portfolio projection engine, priority agent compute (faster/deeper reasoning passes), early access to new sports, direct access to postgame review detail on every agent |
| **Playbook Syndicate** (future) | Custom/annual | Small groups, content creators, semi-pro | Multi-seat, API access to recommendation feed, white-label dashboard option |

Annual pricing at ~2 months free is the standard SaaS lever and should apply to Pro/Elite from launch — it converts your best users into 12-month retained revenue immediately and smooths cash flow, which matters more than optimizing per-user margin at this stage.

### 2.2 Why Not Freemium-Heavy or Ad-Supported
Ads create a second incentive to keep users engaged/betting more, which again fights the "No Bet Today" principle. Don't introduce a second stakeholder (advertisers) whose interests conflict with the user's. Free tier exists purely as a funnel, capped hard enough that it can't substitute for Pro.

### 2.3 Trust as the Real Product
Because win % is explicitly not the north star metric, the pricing page and onboarding copy need to say that out loud, early, before a user ever sees a recommendation. This is a differentiation move — most competitors lead with win rate because it's an easy (and easily gamed) number. Leading with "we optimize for long-term ROI and will tell you when not to bet" is a harder sell on day one but is the entire basis for retention past month two, when the novelty of any picks service normally wears off.

---

## 3. Target Users & Personas

Three personas, ordered by revenue priority.

### Persona A — "The Disciplined Grinder" (primary target)
Bets consistently, tracks results informally (spreadsheet or memory), frustrated by tout services that never explain reasoning, wants to get better at the process, not just get picks. This is the person who will actually read the Explainability Engine's output. Highest LTV, most likely to upgrade to Elite, most likely to refer others. **Design the core product for this person first.**

### Persona B — "The Casual Weekend Bettor"
Bets NFL Sundays, maybe a same-game parlay for fun, low bankroll, low sophistication, easily overwhelmed by too much data. This person needs the natural-language interface to genuinely work — they will type "give me something safe for $20" and bounce immediately if the response reads like a stats sheet. Free/Pro tier target.

### Persona C — "The Numbers Person"
Comes from a fantasy sports, options-trading, or data-analyst background (this persona will resonate with your own trading interests). Wants the portfolio projection engine, wants to see agent-level performance scores, wants CLV data. This person upgrades to Elite fastest but churns fastest too if the numbers don't hold up under scrutiny — they will fact-check the reproducibility claims. Treat this persona as your QA layer: if The Playbook can survive Persona C's scrutiny, it can survive anyone's.

**Recommendation:** Build onboarding to detect which persona a user is within the first session (see Section 6) and adjust default UI density accordingly rather than making every user configure it manually.

---

## 4. Core Product Principles (Non-Negotiable)

These carry forward into every other volume. Any future architectural decision that violates one of these should be flagged as a conflict, not silently implemented.

1. **"No Bet Today" is a valid, frequent, celebrated output** — not a fallback or an error state. UI treatment matters here (Volume 5): it should never look like "the app is broken" or "nothing to show."
2. **Every number is explainable and reproducible months later.** If the Time Machine snapshot can't answer "what did the AI know when it made this call," the recommendation shouldn't have shipped.
3. **Win % is never the headline metric anywhere in the product** — not onboarding, not dashboard, not marketing. ROI/EV/CLV lead everywhere.
4. **The AI never over-recommends to justify a subscription price.** This is enforced structurally by the subscription model (Section 2), not by policy alone — policy without structural incentive alignment doesn't hold up under business pressure six months post-launch.
5. **Bet slip upload is always optional, never gates functionality.**

---

## 5. Pricing Psychology & Positioning

Position against two categories simultaneously, since users will mentally compare The Playbook to both:

- **Vs. tout services / picks Discords/Telegrams:** The Playbook wins on transparency and reproducibility — a tout can't show you why, six weeks later, a pick made sense at the time. This is a real, defensible advantage; lead marketing with it.
- **Vs. "just doing your own research":** The Playbook wins on time and breadth (20+ specialized agents vs. one person checking a few sites) and on discipline (it won't talk itself into a bet out of boredom the way a person will). This is the harder sell — the natural-language interface and the postgame review engine are what make the case here, because they make the AI's reasoning legible instead of a black box.

**Do not compete on "hit rate."** Any pricing page copy or marketing claim built around win percentage undermines the entire product philosophy and will attract the wrong persona (Persona D, not defined above on purpose: the person chasing a hot streak, who will churn hard on the first cold week and leave bad reviews). Filter this persona out at the pricing page, not after they've paid.

---

## 6. Onboarding Flow

Goal: collect the minimum needed to personalize (per master spec — no over-collection), while also silently classifying the user into Persona A/B/C to set UI defaults.

**Step 1 — Conversational intro (not a form).** First message from the AI, not a signup wall: "Tell me how you bet." Free text. This does double duty — it's the natural-language interface proving itself in the first ten seconds, and the response length/vocabulary/specificity is a decent signal for persona classification (Volume 4's NL Engine should tag this).

**Step 2 — Structured essentials only (from master spec):**
- Betting experience (new / casual / experienced)
- Primary goal (fun / disciplined long-term / serious edge-seeking)
- Risk tolerance (conservative / moderate / aggressive)
- Preferred unit size
- Max parlay size (including "I don't want parlays" as an explicit option — called out directly in the master spec)
- Favorite sports (NFL only at launch, but ask broadly to seed future personalization)
- Optional bankroll

**Step 3 — First recommendation, immediately, same session.** Don't let a user complete onboarding and land on an empty dashboard. If it's a "No Bet Today" day, that's fine — but the Explainability Engine should walk them through *why*, right there, as the first real product experience. This turns the hardest thing to sell (an app that sometimes tells you not to bet) into the first impression, on your terms, with full context, rather than something they discover cold in week three and interpret as the app not working.

**Step 4 — Optional bet slip upload**, framed explicitly as optional and only for personalization, matching the master spec's requirement that this never becomes a gate.

---

## 7. Customer Journey Maps

### Journey 1 — New User, First Week (Persona B, Casual)
Signs up Thursday before Sunday NFL slate → conversational onboarding → gets a same-game parlay suggestion for $20 with plain-language reasoning → wins → comes back Sunday of week 2 → this time recommendation is "No Bet Today" on their favorite team's game → **this is the make-or-break moment.** If the app explains why clearly and offers an alternative (smaller stake, different game, or genuinely nothing) without being pushy, retention holds. If it feels like a dead end, churn risk spikes. Volume 5 should design a specific "No Bet Today" UI state for this reason, not reuse a generic empty state.

### Journey 2 — Power User, Month 2 (Persona A, Grinder)
Has been tracking recommendations manually for weeks out of habit → discovers the Projected Performance feature already did this automatically → this is a strong upgrade trigger to Elite (portfolio projection engine) → starts reading full agent-level breakdowns → becomes a candidate for referral/word-of-mouth, since this persona talks to other bettors. Product should surface a "share this recommendation's reasoning" moment here (Volume 5), since Persona A is your organic growth engine.

### Journey 3 — Numbers Person, Skeptical Evaluation (Persona C)
Signs up specifically to stress-test the reproducibility claim → pulls up a recommendation from 3 weeks prior → checks whether the Time Machine snapshot actually matches what really happened with odds/injuries at that time → if it holds up, converts to Elite same day and becomes highest-LTV user; if it doesn't hold up even once, churns immediately and is unlikely to return. **This journey is the reason reproducibility (Section 4, principle 2) cannot be treated as a nice-to-have in later volumes — for this persona, it's the entire product.**

---

## 8. Success Metrics (Business Layer)

Mirrors the master spec's AI-layer metrics but adds business-specific ones:

**Product/AI metrics (from master spec, inherited here):**
ROI, Expected Value, Closing Line Value, Units Won, risk-adjusted returns, confidence calibration.

**Business metrics (new, this volume):**
- Month-2 retention specifically (this is where the "No Bet Today" tension bites hardest — track it as its own cohort metric, not folded into general retention)
- Free → Pro conversion rate, segmented by which persona the onboarding classifier assigned
- % of users who ever open an individual agent breakdown (proxy for whether Explainability Engine is actually being used, not just shipped)
- Elite upgrade rate among users who've had at least one "No Bet Today" day (tests whether transparency during a no-bet day builds trust rather than eroding it)

---

## 9. Go-to-Market (Phase 1)

**Launch narrow:** NFL only, matching the master spec's sport sequencing. Don't launch multi-sport — it dilutes the depth of the agent committee's data per sport and makes the reproducibility/explainability story weaker across the board.

**Lead with Persona A in marketing**, not Persona B, even though B is a bigger addressable market. Persona A's word-of-mouth is more credible (bettors trust other serious bettors' recommendations far more than ads) and their retention validates the model before you spend on broader acquisition.

**Content strategy:** Public postgame reviews (anonymized, aggregate) are a strong content/trust asset — "here's a recommendation from 3 weeks ago, here's exactly why it hit or missed, here's what the AI learned" is content no tout service can produce, because they don't have the Time Machine/reproducibility layer. This should be a recurring content format from week one.

### 9.1 Referral & Public Trust Levers (v2.0)

Two additions from the external architecture review, both aligned with the "trust over win-rate" positioning already established in this volume:

**Referral system.** A `referral_code` field on the user's profile is cheap to add now and avoids a later migration, but the actual referral program mechanics — what a referrer earns, what a new user gets — should wait until real Persona A retention data exists (Section 7, Journey 2) to design the incentive around. Persona A is the natural word-of-mouth engine here; building the referral mechanic around guesses instead of that data risks optimizing for the wrong behavior.

**Public Transparency Portal.** A public-facing page showing aggregate historical ROI, EV, No Bet %, and full recommendation history (including withdrawn ones) is a strong differentiator given this volume's entire thesis — nothing hidden is the whole pitch. Explicitly **post-MLP**: it needs enough real settled recommendations to be credible rather than sparse, and it depends on public-facing aggregate reporting infrastructure that doesn't exist at launch. Target this for the first major post-launch release, not the initial NFL-only MLP.

---

## 10. Compliance & Business Risk Considerations

This is a business-planning section, not a legal opinion — flagging it here because it affects pricing, onboarding copy, and go-to-market sequencing, all of which are this volume's job.

- Sports betting advisory products sit in a regulated-adjacent space that varies by U.S. state; onboarding should collect state/jurisdiction early enough to gate availability if needed, without making that step feel like friction.
- "AI Operating System" / "investment firm" framing (used throughout the master spec) is a deliberate positioning choice, but marketing copy should avoid language that could be read as a guarantee of profit — this is a real business risk (FTC/state AG exposure), not a moral judgment on the product itself.
- Recommend involving actual legal counsel on subscription terms and state-by-state availability before public launch — this is a to-do for Phase 1 GTM, tracked here so it doesn't get lost between volumes.

---

## 11. Open Decisions Carried to Later Volumes

Flagging these now so Volumes 2–5 don't silently diverge:

- **Pricing tier → feature gating** must be reflected in the database schema (Volume 3, subscription tables) and in the AI Orchestrator's compute budget logic (Volume 4 — Elite tier's "priority agent compute" needs a concrete definition: deeper reasoning passes? more agents consulted? Both should be specified in Volume 4, not left implicit).
- **Persona classification from onboarding** needs a home in the User Profile Engine (Volume 2/4) and should influence default dashboard density (Volume 5).
- **State/jurisdiction gating** needs a technical enforcement point — likely Authentication Engine (Volume 2) at signup.

---

## Changelog Entry for This Version

See `CHANGELOG.md` — v1.0, 2026-08-05. Updated to v2.0, 2026-08-05, per external architecture review — Section 9.1 (Referral & Public Trust Levers) added above, not just noted in the version header. Updated to v3.0, 2026-08-05 — §1 amended with chat-first positioning, integrated directly rather than only noted in the header.
