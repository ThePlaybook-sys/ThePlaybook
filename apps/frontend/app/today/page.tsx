import { Container } from "@/components/ds";
import { AppNav } from "@/components/nav/AppNav";
import {
  CommandHeader,
  IntelligencePulsePanel,
  RecentDecisionsList,
  TodaysBoard,
  TrackRecordSnapshot,
} from "@/components/dashboard";
import { getRecommendations, getSourceFreshness, getToday, getTrackRecord } from "@/app/lib/api";

export const metadata = { title: "Today — MANSA" };

const RECENT_DECISIONS_LIMIT = 6;

/**
 * The MANSA Command Center (Phase 6 Milestone 7.1, replacing M3's plain
 * title+list rendering). Composes four independently-fetched, already-
 * authoritative reads -- today's recommendation products, the recent
 * feed, the track record snapshot, and source-data freshness -- into
 * one entry surface: Today's Board (dominant) plus a supporting
 * intelligence rail. No new business logic anywhere in this
 * composition; every module either renders API data verbatim or a
 * pure client-side count/label derived from it (`dashboardCounts.ts`,
 * `recentDecisionState.ts`).
 *
 * Each module receives its own `ApiResult` and renders its own honest
 * state independently (the established M6 `AccountSummary` pattern) --
 * a failure in one read (e.g. Track Record) never blanks the rest of
 * the dashboard.
 *
 * Desktop: Today's Board occupies the dominant left zone, the rail
 * (Intelligence/Recent Decisions/Track Record) sits to its right.
 * Mobile: the exact same modules, same order, stacked vertically --
 * never a reduced or reordered "mobile mode."
 */
export default async function TodayPage() {
  const [today, recent, trackRecord, freshness] = await Promise.all([
    getToday(),
    getRecommendations({ limit: RECENT_DECISIONS_LIMIT }),
    getTrackRecord(),
    getSourceFreshness(),
  ]);

  return (
    <>
      <AppNav />
      <Container as="main" className="flex flex-col gap-xl py-xl">
        <CommandHeader freshness={freshness} />

        <div className="flex flex-col gap-xl lg:grid lg:grid-cols-3 lg:items-start lg:gap-xl">
          <div className="lg:col-span-2">
            <TodaysBoard today={today} />
          </div>

          <div className="flex flex-col gap-lg">
            <IntelligencePulsePanel today={today} freshness={freshness} />
            <RecentDecisionsList recent={recent} />
            <TrackRecordSnapshot trackRecord={trackRecord} />
          </div>
        </div>
      </Container>
    </>
  );
}
