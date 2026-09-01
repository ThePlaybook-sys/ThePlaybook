import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrackRecordSnapshot } from "../TrackRecordSnapshot";
import type { ApiResult, TrackRecordData } from "@/app/lib/api-types";

function ok(data: TrackRecordData): ApiResult<TrackRecordData> {
  return { kind: "ok", data };
}

describe("TrackRecordSnapshot", () => {
  it("reuses the exact zero-sample copy TrackRecordSummary already ships -- no second, drifting message", () => {
    render(
      <TrackRecordSnapshot
        trackRecord={ok({
          sampleSize: 0,
          sampleStatus: "zero",
          record: { win: 0, loss: 0, push: 0, voidNoAction: 0, mixedSettled: 0 },
          byRecommendationType: {},
        })}
      />,
    );
    expect(
      screen.getByText(/MANSA hasn't graded any recommendation products yet\. A track record will appear here/),
    ).toBeInTheDocument();
  });

  it("shows product-level counts only -- sample size, W/L/Push/Void/Mixed -- never a derived win rate", () => {
    render(
      <TrackRecordSnapshot
        trackRecord={ok({
          sampleSize: 42,
          sampleStatus: "mature",
          record: { win: 24, loss: 15, push: 2, voidNoAction: 1, mixedSettled: 0 },
          byRecommendationType: {},
        })}
      />,
    );
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("W 24")).toBeInTheDocument();
    expect(screen.getByText("L 15")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ROI/i)).not.toBeInTheDocument();
  });

  it("preserves the low-sample disclosure", () => {
    render(
      <TrackRecordSnapshot
        trackRecord={ok({
          sampleSize: 5,
          sampleStatus: "low",
          record: { win: 3, loss: 2, push: 0, voidNoAction: 0, mixedSettled: 0 },
          byRecommendationType: {},
        })}
      />,
    );
    expect(screen.getByText(/Early sample/)).toBeInTheDocument();
  });

  it("links to the full track record page", () => {
    render(
      <TrackRecordSnapshot
        trackRecord={ok({
          sampleSize: 0,
          sampleStatus: "zero",
          record: { win: 0, loss: 0, push: 0, voidNoAction: 0, mixedSettled: 0 },
          byRecommendationType: {},
        })}
      />,
    );
    expect(screen.getByRole("link", { name: "See full record" })).toHaveAttribute("href", "/track-record");
  });
});
