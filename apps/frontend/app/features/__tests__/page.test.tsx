import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import FeaturesPage from "../page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/features",
}));

const REQUIRED_FEATURES = [
  "Today's Board",
  "Recommendations",
  "AI Committee",
  "Modeled Probability & EV",
  "Explainability",
  "No Bet & Bankroll Preservation",
  "Time Machine",
  "Track Record",
  "Data Freshness & Provenance",
];

describe("FeaturesPage (Public Web M2)", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
  });

  it("lists only the real, shipped capabilities HQ specified, not the M1 placeholder copy", async () => {
    render(await FeaturesPage());
    for (const feature of REQUIRED_FEATURES) {
      expect(screen.getByText(feature)).toBeInTheDocument();
    }
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
  });

  it("never advertises unfinished Phase 7, parlays, Telegram, bet verification, or sharp money", async () => {
    render(await FeaturesPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/parlay/i);
    expect(text).not.toMatch(/telegram/i);
    expect(text).not.toMatch(/sharp money/i);
    expect(text).not.toMatch(/bet verification/i);
    expect(text).not.toMatch(/anomaly/i);
  });

  it("never claims a derived win rate, ROI, or units figure -- Track Record only shows the real graded-sample breakdown", async () => {
    render(await FeaturesPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/win rate/i);
    expect(text).not.toMatch(/\bROI\b/);
  });

  it("Web M1 routing correction: signed-out CTA is Create Account", async () => {
    render(await FeaturesPage());
    expect(screen.getAllByRole("link", { name: "Create Account" }).length).toBeGreaterThan(0);
  });

  it("Web M1 routing correction: signed-in CTA is Open MANSA -> /today", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    render(await FeaturesPage());
    const openMansaLinks = screen.getAllByRole("link", { name: "Open MANSA" });
    expect(openMansaLinks.length).toBeGreaterThan(0);
    for (const link of openMansaLinks) {
      expect(link).toHaveAttribute("href", "/today");
    }
  });

  it("Public Web M2.1: breaks up the tile list with the illustrative product visual, clearly labeled", async () => {
    render(await FeaturesPage());
    expect(screen.getByText("Illustrative Example")).toBeInTheDocument();
    expect(screen.getByText("Not a live recommendation")).toBeInTheDocument();
  });

  it("Public Web M2.1: body copy uses the brightened marketing tone", async () => {
    render(await FeaturesPage());
    const heroBody = screen.getByText(/What MANSA actually does today/);
    expect(heroBody.className).toContain("!text-body-bright");
  });
});
