import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TimeMachine } from "../TimeMachine";
import {
  makeDetail,
  makeGradeEvent,
  makeLifecycleEvent,
  makePostgameReview,
  makeReconstruction,
} from "./fixtures";

describe("TimeMachine", () => {
  it("always renders all six stages, structurally stable even with minimal data", () => {
    render(
      <TimeMachine
        detail={makeDetail({ legs: [], whyNotOtherShapes: null, dataLimitations: null })}
        reconstruction={makeReconstruction({ legs: [] })}
      />,
    );
    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "What We Recommended",
      "What We Knew",
      "Why We Liked It",
      "What Changed",
      "What Happened",
      "Final Result / Review",
    ]);
  });

  it("renders each stage's own honest empty copy when its data is genuinely absent", () => {
    render(
      <TimeMachine
        detail={makeDetail({
          legs: [
            {
              ...makeDetail().legs[0],
              strongestEvidence: null,
              biggestRisks: null,
              contributingAgents: [],
              wouldChangeMindIf: null,
              agentContributions: [],
              consensus: null,
            },
          ],
          whyNotOtherShapes: null,
          dataLimitations: null,
        })}
        reconstruction={makeReconstruction({
          lifecycle_events: [makeLifecycleEvent()],
          product_grade_history: [],
          current_product_grade: null,
          postgame_reviews: [],
        })}
      />,
    );
    expect(screen.getByText("No additional evidence recorded.")).toBeInTheDocument();
    expect(screen.getByText("No material changes recorded.")).toBeInTheDocument();
    // Ungraded -- both Stage 5 and Stage 6 honestly say the same thing,
    // never a fabricated result.
    expect(screen.getAllByText("Awaiting final result.").length).toBe(2);
  });

  it("never invents a Postgame Review when the product is graded but no review exists", () => {
    render(
      <TimeMachine
        detail={makeDetail()}
        reconstruction={makeReconstruction({
          current_product_grade: makeGradeEvent({ outcome: "WIN" }),
          product_grade_history: [makeGradeEvent({ outcome: "WIN" })],
          postgame_reviews: [],
        })}
      />,
    );
    expect(screen.getByText("Postgame review unavailable.")).toBeInTheDocument();
  });

  it("renders a real Postgame Review when one exists", () => {
    render(
      <TimeMachine
        detail={makeDetail()}
        reconstruction={makeReconstruction({
          current_product_grade: makeGradeEvent({ outcome: "WIN" }),
          product_grade_history: [makeGradeEvent({ outcome: "WIN" })],
          postgame_reviews: [makePostgameReview()],
        })}
      />,
    );
    expect(screen.getByText("Chiefs covered comfortably.")).toBeInTheDocument();
    expect(screen.getByText(/Home favorite closed the game out/)).toBeInTheDocument();
  });

  it("shows the full grade history including a correction, never collapsing it to just the current value", () => {
    render(
      <TimeMachine
        detail={makeDetail()}
        reconstruction={makeReconstruction({
          product_grade_history: [
            makeGradeEvent({ id: "grade-1", outcome: "WIN", is_correction: false, computed_at: "2026-08-29T02:00:00Z" }),
            makeGradeEvent({ id: "grade-2", outcome: "LOSS", is_correction: true, computed_at: "2026-08-30T09:00:00Z" }),
          ],
          current_product_grade: makeGradeEvent({ id: "grade-2", outcome: "LOSS", is_correction: true }),
        })}
      />,
    );
    expect(screen.getByText("Win")).toBeInTheDocument();
    expect(screen.getByText("Loss")).toBeInTheDocument();
    expect(screen.getByText("Correction")).toBeInTheDocument();
  });

  it("only shows per-leg grading breakdown for multi-leg products, never fabricated for a single leg", () => {
    const { rerender } = render(
      <TimeMachine
        detail={makeDetail()}
        reconstruction={makeReconstruction()}
      />,
    );
    expect(screen.queryByText("Per-leg grading")).not.toBeInTheDocument();

    rerender(
      <TimeMachine
        detail={makeDetail({ recommendationType: "multiple_singles" })}
        reconstruction={makeReconstruction({
          legs: [
            { leg_order: 1, leg: { ...makeReconstruction().legs[0].leg, id: "leg-1", selection: "Chiefs" }, explanation: null, grade_history: [], current_grade: null, weighting_evidence: [] },
            { leg_order: 2, leg: { ...makeReconstruction().legs[0].leg, id: "leg-2", selection: "Bills" }, explanation: null, grade_history: [], current_grade: null, weighting_evidence: [] },
          ],
        })}
      />,
    );
    expect(screen.getByText("Per-leg grading")).toBeInTheDocument();
  });

  it("temporal integrity: never surfaces detail's current status/grade -- only reconstruction's own historical record", () => {
    render(
      <TimeMachine
        detail={makeDetail({
          status: "withdrawn",
          withdrawalReason: "line moved past invalidation threshold",
          grade: { outcome: "LOSS", gradedAt: "2026-08-29T02:00:00Z", isCorrection: false, correctedAt: null },
        })}
        reconstruction={makeReconstruction({
          // Reconstruction's own historical record disagrees with (or
          // simply doesn't yet reflect) detail's current live state --
          // Stage 4/5/6 must reflect ONLY what reconstruction says.
          lifecycle_events: [makeLifecycleEvent()],
          product_grade_history: [],
          current_product_grade: null,
        })}
      />,
    );
    // detail.grade's "Loss" and detail.status's "withdrawn"/reason text
    // must never leak into the render -- only reconstruction's own
    // append-only history may produce those words.
    expect(screen.queryByText("Loss")).not.toBeInTheDocument();
    expect(screen.queryByText("line moved past invalidation threshold")).not.toBeInTheDocument();
    expect(screen.queryByText("Withdrawn")).not.toBeInTheDocument();
    expect(screen.getByText("No material changes recorded.")).toBeInTheDocument();
  });

  it("renders a real lifecycle event (withdrawal) when reconstruction actually has one", () => {
    render(
      <TimeMachine
        detail={makeDetail()}
        reconstruction={makeReconstruction({
          lifecycle_events: [
            makeLifecycleEvent({ event_type: "ACTIVATED", event_timestamp: "2026-08-28T06:00:30Z" }),
            makeLifecycleEvent({
              event_type: "WITHDRAWN",
              event_timestamp: "2026-08-28T10:00:00Z",
              reason: "line moved past invalidation threshold",
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText("Withdrawn")).toBeInTheDocument();
    expect(screen.getByText("line moved past invalidation threshold")).toBeInTheDocument();
  });

  it("mobile-safe structure: the stage list and stage content are single-column by construction", () => {
    const { container } = render(<TimeMachine detail={makeDetail()} reconstruction={makeReconstruction()} />);
    const list = container.querySelector("ol");
    expect(list).toHaveClass("flex-col");
    const firstStageContent = container.querySelectorAll("li > div")[0];
    expect(firstStageContent).toHaveClass("flex-col");
  });
});
