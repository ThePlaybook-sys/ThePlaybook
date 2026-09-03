import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import HowItWorksPage from "../page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/how-it-works",
}));

describe("HowItWorksPage (Public Web M2)", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
  });

  it("renders the real pipeline, in order, not the M1 placeholder copy", async () => {
    render(await HowItWorksPage());
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items[0]).toContain("Data");
    expect(items[1]).toContain("Intelligence");
    expect(items[2]).toContain("AI Committee");
    expect(items[3]).toContain("Decision");
    expect(items[4]).toContain("Explainability");
    expect(items[5]).toContain("Time Machine");
    expect(items[6]).toContain("Grading & Track Record");
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
  });

  it("explicitly states confidence is not win probability", async () => {
    render(await HowItWorksPage());
    expect(screen.getByText("Confidence ≠ Win Probability")).toBeInTheDocument();
    expect(screen.getByText(/not the likelihood that a wager wins/i)).toBeInTheDocument();
  });

  it("explicitly states No Bet is a legitimate decision, not a failure", async () => {
    render(await HowItWorksPage());
    expect(screen.getByText("No Bet Is a Legitimate Decision")).toBeInTheDocument();
    expect(screen.getByText(/never a failure to find a recommendation/i)).toBeInTheDocument();
  });

  it("never claims sharp money or a guarantee, and only mentions parlays as an explicit 'coming at launch' note, never as a live capability", async () => {
    render(await HowItWorksPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/sharp money/i);
    expect(text).not.toMatch(/guarantee/i);
    expect(text).not.toMatch(/telegram/i);
    expect(text).toMatch(/intelligent parlays are coming at launch/i);
  });

  it("the real Decision step names the actual markets -- moneyline, spread, total -- never 'picking a winning team'", async () => {
    render(await HowItWorksPage());
    expect(screen.getByText(/moneyline, spread, or total/i)).toBeInTheDocument();
  });

  it("Web M1 routing correction: signed-out CTA is Create Account", async () => {
    render(await HowItWorksPage());
    expect(screen.getAllByRole("link", { name: "Create Account" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Open MANSA" })).not.toBeInTheDocument();
  });

  it("Web M1 routing correction: signed-in CTA is Open MANSA -> /today", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    render(await HowItWorksPage());
    const openMansaLinks = screen.getAllByRole("link", { name: "Open MANSA" });
    expect(openMansaLinks.length).toBeGreaterThan(0);
    for (const link of openMansaLinks) {
      expect(link).toHaveAttribute("href", "/today");
    }
    expect(screen.queryByRole("link", { name: "Create Account" })).not.toBeInTheDocument();
  });

  it("Public Web M2.1: shows the intelligence-flow visual (Data -> Intelligence & AI Committee -> MANSA Decision)", async () => {
    render(await HowItWorksPage());
    const flowHeadings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(flowHeadings).toEqual(["Data", "Intelligence & AI Committee", "MANSA Decision"]);
  });

  it("Public Web M2.1: body copy uses the brightened marketing tone", async () => {
    render(await HowItWorksPage());
    const heroBody = screen.getByText(/One pipeline, from raw data/);
    expect(heroBody.className).toContain("!text-body-bright");
  });
});
