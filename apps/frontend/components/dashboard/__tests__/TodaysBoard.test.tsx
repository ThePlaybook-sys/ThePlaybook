import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TodaysBoard } from "../TodaysBoard";
import { makeCard } from "@/components/recommendations/__tests__/fixtures";
import type { ApiResult, RecommendationCardData } from "@/app/lib/api-types";

function ok(data: RecommendationCardData[]): ApiResult<RecommendationCardData[]> {
  return { kind: "ok", data };
}

describe("TodaysBoard", () => {
  it("renders one BoardCard per recommendation product", () => {
    render(ToWrapper(ok([makeCard({ displayId: "2026-00101" }), makeCard({ displayId: "2026-00102" })])));
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("real M7.1 correction: two products sharing the same game both render as separate cards -- never merged, hidden, or ranked", () => {
    const sharedGame = { homeTeam: "Chiefs", awayTeam: "Bills", scheduledStart: "2026-09-02T20:20:00Z", status: "scheduled" };
    render(
      ToWrapper(
        ok([
          makeCard({ displayId: "2026-00101", game: sharedGame, oneLineSummary: "first qualifying candidate" }),
          makeCard({ displayId: "2026-00102", game: sharedGame, oneLineSummary: "second qualifying candidate" }),
        ]),
      ),
    );
    expect(screen.getByText("first qualifying candidate")).toBeInTheDocument();
    expect(screen.getByText("second qualifying candidate")).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/recommendations/2026-00101",
      "/recommendations/2026-00102",
    ]);
  });

  it("honest empty state uses the same copy /today has always shipped -- never implies analysis is in progress", () => {
    render(ToWrapper(ok([])));
    expect(screen.getByText("Today's recommendations aren't available yet.")).toBeInTheDocument();
  });

  it("unauthenticated/error states render distinctly, never as a silent empty board", () => {
    const { rerender } = render(ToWrapper({ kind: "unauthenticated" }));
    expect(screen.getByText("Sign in to see today's board.")).toBeInTheDocument();

    rerender(ToWrapper({ kind: "error", status: 502 }));
    expect(screen.getByText("Today's board isn't available right now.")).toBeInTheDocument();
  });

  it("mobile-safe structure: the board grid collapses to a single column by default and expands only at the lg breakpoint", () => {
    const { container } = render(ToWrapper(ok([makeCard()])));
    const grid = container.querySelector("[class*='grid-cols-1']");
    expect(grid).toHaveClass("grid-cols-1");
    expect(grid).toHaveClass("lg:grid-cols-2");
  });
});

function ToWrapper(today: ApiResult<RecommendationCardData[]>) {
  return <TodaysBoard today={today} />;
}
