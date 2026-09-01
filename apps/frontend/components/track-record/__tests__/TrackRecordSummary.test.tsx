import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrackRecordSummary } from "../TrackRecordSummary";
import { makeCounts, makeTrackRecord, makeTypeBreakdown } from "./fixtures";

describe("TrackRecordSummary", () => {
  it("renders an honest zero-sample state, no numeric table", () => {
    render(<TrackRecordSummary data={makeTrackRecord()} />);
    expect(screen.getByText("No graded recommendations yet")).toBeInTheDocument();
    expect(screen.queryByText("Win")).not.toBeInTheDocument();
  });

  it("shows a prominent early-sample disclosure for a low sample, alongside the real record", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 5,
          sampleStatus: "low",
          record: makeCounts({ win: 3, loss: 2 }),
        })}
      />,
    );
    expect(screen.getByText(/Early sample/)).toBeInTheDocument();
    expect(screen.getByText("Win")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Loss")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders a mature sample without the early-sample disclosure", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 40,
          sampleStatus: "mature",
          record: makeCounts({ win: 22, loss: 18 }),
        })}
      />,
    );
    expect(screen.queryByText(/Early sample/)).not.toBeInTheDocument();
    expect(screen.getByText("22")).toBeInTheDocument();
  });

  it("renders all five outcome buckets, including push, void, and mixed settled -- never folded together", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 40,
          sampleStatus: "mature",
          record: makeCounts({ win: 10, loss: 8, push: 4, voidNoAction: 3, mixedSettled: 15 }),
        })}
      />,
    );
    expect(screen.getByText("Push")).toBeInTheDocument();
    expect(screen.getByText("Void / No Action")).toBeInTheDocument();
    expect(screen.getByText("Mixed Settled")).toBeInTheDocument();
  });

  it("never renders any win-rate or derived percentage", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 40,
          sampleStatus: "mature",
          record: makeCounts({ win: 22, loss: 18 }),
        })}
      />,
    );
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("renders the recommendation-type breakdown for types with a real sample", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 40,
          sampleStatus: "mature",
          record: makeCounts({ win: 22, loss: 18 }),
          byRecommendationType: {
            single: makeTypeBreakdown({ win: 15, loss: 10 }),
            player_prop: makeTypeBreakdown({ win: 7, loss: 8 }),
          },
        })}
      />,
    );
    expect(screen.getByText("By Recommendation Type")).toBeInTheDocument();
    expect(screen.getByText("Single")).toBeInTheDocument();
    expect(screen.getByText("Player Prop")).toBeInTheDocument();
    expect(screen.getByText("n=25")).toBeInTheDocument();
    expect(screen.getByText("n=15")).toBeInTheDocument();
  });

  it("filters out phantom zero-sample entries (no_bet/bankroll_preservation graded NOT_APPLICABLE) from the type breakdown", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 10,
          sampleStatus: "low",
          record: makeCounts({ win: 6, loss: 4 }),
          byRecommendationType: {
            single: makeTypeBreakdown({ win: 6, loss: 4 }),
            no_bet: makeTypeBreakdown({}),
            bankroll_preservation: makeTypeBreakdown({}),
          },
        })}
      />,
    );
    expect(screen.getByText("Single")).toBeInTheDocument();
    expect(screen.queryByText("No Bet")).not.toBeInTheDocument();
    expect(screen.queryByText("Bankroll Preservation")).not.toBeInTheDocument();
  });

  it("falls back to a readable label for an unknown recommendation type", () => {
    render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 3,
          sampleStatus: "low",
          record: makeCounts({ win: 3 }),
          byRecommendationType: {
            future_exotic_type: makeTypeBreakdown({ win: 3 }),
          },
        })}
      />,
    );
    expect(screen.getByText("Future Exotic Type")).toBeInTheDocument();
  });

  it("mobile-safe structure: sections are single-column by construction", () => {
    const { container } = render(
      <TrackRecordSummary
        data={makeTrackRecord({
          sampleSize: 40,
          sampleStatus: "mature",
          record: makeCounts({ win: 22, loss: 18 }),
          byRecommendationType: { single: makeTypeBreakdown({ win: 22, loss: 18 }) },
        })}
      />,
    );
    const root = container.firstElementChild;
    expect(root).toHaveClass("flex-col");
  });
});
