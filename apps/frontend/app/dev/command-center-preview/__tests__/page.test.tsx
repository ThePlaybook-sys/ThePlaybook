import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import CommandCenterPreviewPage from "../page";

const ORIGINAL_RAILWAY_ENVIRONMENT_NAME = process.env.RAILWAY_ENVIRONMENT_NAME;

function setEnvironmentName(value: string | undefined) {
  if (value === undefined) {
    delete process.env.RAILWAY_ENVIRONMENT_NAME;
  } else {
    process.env.RAILWAY_ENVIRONMENT_NAME = value;
  }
}

afterEach(() => {
  setEnvironmentName(ORIGINAL_RAILWAY_ENVIRONMENT_NAME);
});

describe("CommandCenterPreviewPage -- production exclusion (M7.3 §3)", () => {
  it("calls Next's notFound() when RAILWAY_ENVIRONMENT_NAME is exactly 'production'", () => {
    setEnvironmentName("production");
    let thrown: unknown;
    try {
      CommandCenterPreviewPage();
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeDefined();
    // Next's real notFound() throws an Error whose digest starts with
    // NEXT_NOT_FOUND -- the documented way to assert notFound() actually
    // fired, not just that *some* error was thrown.
    expect((thrown as { digest?: string }).digest).toMatch(/^NEXT_NOT_FOUND/);
  });

  it("renders normally on 'dev'", () => {
    setEnvironmentName("dev");
    expect(() => render(<CommandCenterPreviewPage />)).not.toThrow();
  });

  it("renders normally on 'staging'", () => {
    setEnvironmentName("staging");
    expect(() => render(<CommandCenterPreviewPage />)).not.toThrow();
  });

  it("renders normally when RAILWAY_ENVIRONMENT_NAME is unset (local `next dev`)", () => {
    setEnvironmentName(undefined);
    expect(() => render(<CommandCenterPreviewPage />)).not.toThrow();
  });
});

describe("CommandCenterPreviewPage -- fixture labeling (M7.3 §4)", () => {
  it("clearly labels itself as a static, non-real preview", () => {
    setEnvironmentName("dev");
    render(<CommandCenterPreviewPage />);
    expect(screen.getByText("MANSA UI Preview")).toBeInTheDocument();
    expect(screen.getByText("STATIC DESIGN FIXTURES — NOT REAL RECOMMENDATIONS")).toBeInTheDocument();
  });
});

describe("CommandCenterPreviewPage -- reuses real production components (M7.3 §5)", () => {
  it("renders the real CommandHeader, Today's Board, MANSA Intelligence, Recent Decisions, and Track Record headings verbatim", () => {
    setEnvironmentName("dev");
    render(<CommandCenterPreviewPage />);
    // CommandHeader's own h1 -- proves the real component rendered, not a
    // hand-rolled duplicate (a duplicate would not produce this exact,
    // separately-tested component's DOM).
    expect(screen.getByRole("heading", { level: 1, name: "MANSA" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Today's Board" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "MANSA Intelligence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent Decisions" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Track Record" })).toBeInTheDocument();
  });

  it("BoardCard's real data-recommendation-type/status attributes are present -- proof the real component, not a mockup, rendered each fixture", () => {
    setEnvironmentName("dev");
    const { container } = render(<CommandCenterPreviewPage />);
    expect(container.querySelectorAll("[data-recommendation-type='no_bet']").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("[data-recommendation-type='bankroll_preservation']").length).toBeGreaterThan(
      0,
    );
  });
});

describe("CommandCenterPreviewPage -- required fixture states (M7.3 §6)", () => {
  beforeEach(() => setEnvironmentName("dev"));

  it("renders an active recommendation", () => {
    render(<CommandCenterPreviewPage />);
    // Appears in both Today's Board and Recent Decisions -- the same
    // real-data pattern the production route uses, since one product
    // can legitimately surface in both modules at once.
    expect(screen.getAllByText("Buffalo Bills @ Kansas City Chiefs").length).toBeGreaterThan(0);
  });

  it("renders No Bet's deliberate-decline treatment, with the real matchup still visible", () => {
    render(<CommandCenterPreviewPage />);
    expect(screen.getAllByText("No Bet").length).toBeGreaterThan(0);
    expect(screen.getByText("Philadelphia Eagles @ Dallas Cowboys")).toBeInTheDocument();
  });

  it("renders Bankroll Preservation's distinct slate-scoped treatment, with no fabricated matchup", () => {
    render(<CommandCenterPreviewPage />);
    expect(screen.getAllByText("Bankroll Preservation").length).toBeGreaterThan(0);
    expect(screen.getByText("Today's Slate")).toBeInTheDocument();
  });

  it("renders a settled WIN, LOSS, PUSH, VOID/No Action, and Mixed Settled state each", () => {
    render(<CommandCenterPreviewPage />);
    expect(screen.getAllByText("Win").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Loss").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Push").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Void").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mixed Settled").length).toBeGreaterThan(0);
  });

  it("multiple products for the same game both render, at equal weight, per HQ's multiplicity rule (M7.3 §6.G)", () => {
    render(<CommandCenterPreviewPage />);
    // Both PREVIEW-00002 and PREVIEW-00003 share the same matchup.
    expect(screen.getAllByText("San Francisco 49ers @ Jacksonville Jaguars")).toHaveLength(2);
  });

  it("a long real team name renders in full, without being truncated away from the DOM (M7.5 realistic stress case)", () => {
    render(<CommandCenterPreviewPage />);
    expect(screen.getByText("Jacksonville Jaguars +3.5")).toBeInTheDocument();
  });
});
