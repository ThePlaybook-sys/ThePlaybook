/**
 * Public Web M3 -- the one source of truth for MANSA's launch pricing
 * numbers and the plan/capability comparison direction, shared by the
 * homepage teaser (`PricingTeaser`) and the full `/pricing` page
 * (`PricingCard`/`PricingComparisonTable`) so the three prices never
 * drift between the two places they appear.
 *
 * HQ's explicit instruction: these are current MANSA launch pricing
 * numbers to treat as real in DEV, and product entitlement DIRECTIONS,
 * not backend limits -- no checkout/billing is wired to any of this,
 * and no numeric usage allowance (message counts, refresh intervals,
 * token limits) is invented anywhere below. Every string value here is
 * copied verbatim from HQ's own table; nothing is estimated or rounded.
 */

export interface PricingPlan {
  id: "core" | "pro" | "elite";
  name: string;
  price: string;
  tagline: string;
  highlights: string[];
  mostPopular?: boolean;
}

export const PRICING_PLANS: PricingPlan[] = [
  {
    id: "core",
    name: "Core",
    price: "$19.99",
    tagline: "MANSA's Command Center and real-market recommendations.",
    highlights: [
      "Command Center dashboard",
      "Recommendations across moneyline, spread, and totals",
      "Track Record",
      "Basic Explainability",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$34.99",
    tagline: "Full reasoning, the full conversational companion, and intelligent parlays.",
    highlights: [
      "Everything in Core",
      "Full Explainability & Time Machine",
      "Full Telegram Companion & Conversational MANSA",
      "Full Intelligent Parlays",
    ],
    mostPopular: true,
  },
  {
    id: "elite",
    name: "Elite",
    price: "$69.99",
    tagline: "MANSA's highest intelligence tier, with priority freshness and bet timing.",
    highlights: [
      "Everything in Pro",
      "Highest Conversational MANSA",
      "Full Market Intelligence & Bet Timing",
      "Highest Freshness Priority",
    ],
  },
];

export interface ComparisonRow {
  label: string;
  core: string;
  pro: string;
  elite: string;
  /** Doesn't exist in any operational form in DEV yet, under any tier --
   * distinct from a row whose CAPABILITY already ships and only the
   * tier-based differentiation itself is a future direction (e.g.
   * Explainability, Time Machine, Freshness Priority all have real,
   * shipped capabilities behind them today; the Basic/Full/Standard/
   * Enhanced tiering of them does not exist yet, but that's covered by
   * this page's own single top-of-table caveat, not a per-row marker). */
  notYetOperational?: boolean;
}

export const COMPARISON_ROWS: ComparisonRow[] = [
  { label: "Command Center", core: "✓", pro: "✓", elite: "✓" },
  { label: "MANSA Recommendations", core: "✓", pro: "✓", elite: "✓" },
  { label: "Moneyline / Spread / Totals", core: "✓", pro: "✓", elite: "✓" },
  { label: "Track Record", core: "✓", pro: "✓", elite: "✓" },
  { label: "Explainability", core: "Basic", pro: "Full", elite: "Full" },
  {
    label: "Telegram Companion",
    core: "Limited",
    pro: "Full",
    elite: "Full",
    notYetOperational: true,
  },
  {
    label: "Conversational MANSA",
    core: "Standard",
    pro: "Expanded",
    elite: "Highest",
    notYetOperational: true,
  },
  {
    label: "Intelligent Parlays",
    core: "Limited",
    pro: "Full",
    elite: "Full",
    notYetOperational: true,
  },
  { label: "Time Machine", core: "Limited", pro: "Full", elite: "Full" },
  {
    label: "Market Intelligence",
    core: "Basic/—",
    pro: "Advanced",
    elite: "Full",
    notYetOperational: true,
  },
  { label: "Bet Timing", core: "—", pro: "—", elite: "✓", notYetOperational: true },
  { label: "Advanced Alerts", core: "—", pro: "✓", elite: "✓", notYetOperational: true },
  { label: "Freshness Priority", core: "Standard", pro: "Enhanced", elite: "Highest" },
];
