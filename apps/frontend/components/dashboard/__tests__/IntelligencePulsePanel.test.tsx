import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { IntelligencePulsePanel } from "../IntelligencePulsePanel";
import { makeCard } from "@/components/recommendations/__tests__/fixtures";
import type { ApiResult, RecommendationCardData, SourceFreshness } from "@/app/lib/api-types";

function okToday(data: RecommendationCardData[]): ApiResult<RecommendationCardData[]> {
  return { kind: "ok", data };
}

const NO_FRESHNESS: ApiResult<SourceFreshness> = { kind: "unauthenticated" };

describe("IntelligencePulsePanel", () => {
  it("real zero counts are information, not an absence of it -- a zero-recommendation day shows 0, never a hidden/empty panel", () => {
    render(<IntelligencePulsePanel today={okToday([])} freshness={NO_FRESHNESS} />);
    expect(screen.getByText("Recommendations")).toBeInTheDocument();
    expect(screen.getAllByText("0")).toHaveLength(3);
  });

  it("exact count semantics: recommendations, No Bet decisions, and games represented are each their own real number", () => {
    const gameA = { homeTeam: "Chiefs", awayTeam: "Bills", scheduledStart: "2026-09-02T20:20:00Z", status: "scheduled" };
    render(
      <IntelligencePulsePanel
        today={okToday([
          makeCard({ displayId: "1", game: gameA }),
          makeCard({ displayId: "2", recommendationType: "no_bet", legs: [], game: gameA }),
          makeCard({ displayId: "3", recommendationType: "bankroll_preservation", scope: "slate", game: null, legs: [] }),
        ])}
        freshness={NO_FRESHNESS}
      />,
    );
    const values = screen.getAllByText(/^\d+$/).map((el) => el.textContent);
    expect(values).toEqual(["3", "1", "1"]); // 3 recommendations, 1 No Bet, 1 game represented
  });

  it("never fabricates markets analyzed/rejected, alerts, or live-AI-activity language", () => {
    render(<IntelligencePulsePanel today={okToday([makeCard()])} freshness={NO_FRESHNESS} />);
    expect(screen.queryByText(/markets analyzed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/markets rejected/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/awaiting analysis/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/analyzing/i)).not.toBeInTheDocument();
  });

  it("renders an honest degraded message, not fabricated zeros, when the read itself failed", () => {
    render(<IntelligencePulsePanel today={{ kind: "error", status: 502 }} freshness={NO_FRESHNESS} />);
    expect(screen.getByText("Intelligence summary isn't available right now.")).toBeInTheDocument();
  });
});
