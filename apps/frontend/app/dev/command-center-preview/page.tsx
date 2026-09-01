import { notFound } from "next/navigation";
import { Container, Text } from "@/components/ds";
import {
  CommandHeader,
  IntelligencePulsePanel,
  RecentDecisionsList,
  TodaysBoard,
  TrackRecordSnapshot,
} from "@/components/dashboard";
import {
  BOARD_RESULT,
  FRESHNESS_RESULT,
  RECENT_DECISIONS_RESULT,
  TRACK_RECORD_RESULT,
} from "./fixtures";

export const metadata = { title: "MANSA UI Preview — Not For Production" };

/**
 * Forces per-request rendering. Without this, Next.js statically
 * prerenders this route at `next build` time (it has no other dynamic
 * API call to force that automatically) -- which would evaluate
 * `RAILWAY_ENVIRONMENT_NAME` once, during the build, and bake that
 * single result into the static output forever, regardless of which
 * Railway environment actually serves it afterward. The production
 * guard below is only meaningful if it reads the real deployed
 * container's environment on every request.
 */
export const dynamic = "force-dynamic";

/**
 * Phase 6 Milestone 7.3 -- MANSA Command Center Visual Validation
 * Showcase. HQ's exact authorization: DEV has zero real recommendation
 * products, so the most important populated Command Center states
 * (multiple products per game, every settled outcome, a dense board,
 * simultaneous Recent Decisions states) cannot be visually validated
 * against real data. This route renders the real, unmodified
 * `components/dashboard` components against explicitly static fixture
 * data (`./fixtures.ts`) instead of fabricating anything in Supabase.
 *
 * This is a development-only diagnostic page, not a product route:
 * - Never linked from `AppNav` (HQ's explicit instruction).
 * - Guarded out of production below -- `notFound()`, not just hidden nav.
 * - Zero backend calls: every prop below is a locally-imported constant,
 *   never the result of `app/lib/api.ts`'s fetch helpers. Nothing here
 *   can write to Supabase, call a recommendation-creation endpoint, or
 *   enter Time Machine / Track Record / grading / adaptive weighting.
 *
 * Production exclusion mechanism: `next start` always sets
 * `NODE_ENV=production` regardless of which Railway environment runs
 * it (confirmed via `Dockerfile`'s `ENV NODE_ENV=production`), so
 * `NODE_ENV` cannot distinguish Railway's "dev"/"staging" environments
 * from "production". `RAILWAY_ENVIRONMENT_NAME` is the value that
 * actually differs per environment (Railway auto-injects it on every
 * service in every environment) and is exactly "production" only on
 * the production Railway environment -- that is the one and only
 * condition this guard checks. Unset locally (`next dev`), so the
 * preview also renders for local development, which HQ's "DEVELOPMENT-
 * ONLY" framing intends.
 */
export default function CommandCenterPreviewPage() {
  if (process.env.RAILWAY_ENVIRONMENT_NAME === "production") {
    notFound();
  }

  return (
    <Container as="main" className="flex flex-col gap-3xl py-xl">
      <div className="flex flex-col gap-xs rounded-md border-2 border-attention-amber bg-surface-card p-lg">
        {/* h2, not h1 -- CommandHeader below renders this page's one real
            h1 ("MANSA"). Keeping a single h1 per page preserves the M7
            accessibility pass's heading-hierarchy guarantee; `as="h2"`
            with `variant="display"` keeps this banner visually the most
            prominent element on the page without claiming the h1 role. */}
        <Text variant="display" as="h2">
          MANSA UI Preview
        </Text>
        <Text variant="body" className="font-bold text-attention-amber">
          STATIC DESIGN FIXTURES — NOT REAL RECOMMENDATIONS
        </Text>
        <Text variant="body">
          Every product, count, and record on this page is hand-authored fixture data for visually
          validating the MANSA Command Center&apos;s populated states. None of it is read from or
          written to any database, and none of it reflects a real MANSA decision. This page is not
          part of the product, is not linked from navigation, and does not exist in production.
        </Text>
      </div>

      <CommandHeader freshness={FRESHNESS_RESULT} />

      <div className="flex flex-col gap-3xl lg:grid lg:grid-cols-3 lg:items-start lg:gap-3xl">
        <div className="lg:col-span-2">
          <TodaysBoard today={BOARD_RESULT} />
        </div>

        <div className="flex flex-col gap-3xl">
          <IntelligencePulsePanel today={BOARD_RESULT} freshness={FRESHNESS_RESULT} />
          <RecentDecisionsList recent={RECENT_DECISIONS_RESULT} />
          <TrackRecordSnapshot trackRecord={TRACK_RECORD_RESULT} />
        </div>
      </div>
    </Container>
  );
}
