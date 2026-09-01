import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SourceFreshnessLabel } from "../SourceFreshnessLabel";
import type { ApiResult, SourceFreshness } from "@/app/lib/api-types";

describe("SourceFreshnessLabel", () => {
  it("real M7.1 requirement: no refresh has ever run is a distinct, honest state -- never a fabricated timestamp", () => {
    render(<SourceFreshnessLabel freshness={ok({ status: null, startedAt: null, completedAt: null, gamesInSlate: null })} />);
    expect(screen.getByText("Awaiting first data refresh")).toBeInTheDocument();
  });

  it("a running refresh (no completedAt yet) is distinguished from a completed one", () => {
    render(
      <SourceFreshnessLabel
        freshness={ok({ status: "running", startedAt: "2026-09-02T06:00:00Z", completedAt: null, gamesInSlate: null })}
      />,
    );
    expect(screen.getByText("Data refresh in progress")).toBeInTheDocument();
  });

  it("a completed refresh shows its own relative timestamp -- never the word 'Updated', never a recommendation's own decision time", () => {
    render(
      <SourceFreshnessLabel
        freshness={ok({ status: "success", startedAt: "2026-09-02T06:00:00Z", completedAt: "2026-09-02T06:04:12Z", gamesInSlate: 14 })}
      />,
    );
    // formatRelativeTime uses the real clock by default; assert the honest structural
    // contract instead of a specific relative string that would depend on wall-clock time.
    expect(screen.getByText(/^Data refreshed /)).toBeInTheDocument();
    expect(screen.queryByText(/^Updated/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Decided/)).not.toBeInTheDocument();
  });

  it("degrades quietly (renders nothing) on unauthenticated/error -- the rest of the Command Center still renders", () => {
    const { container, rerender } = render(<SourceFreshnessLabel freshness={{ kind: "unauthenticated" }} />);
    expect(container).toBeEmptyDOMElement();

    rerender(<SourceFreshnessLabel freshness={{ kind: "error", status: 502 }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

function ok(data: SourceFreshness): ApiResult<SourceFreshness> {
  return { kind: "ok", data };
}
