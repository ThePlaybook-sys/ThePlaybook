import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import PricingPage from "../page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/pricing",
}));

describe("PricingPage (Public Web M3)", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
  });

  it("shows the real launch monthly prices for all three plans, no placeholder copy", async () => {
    render(await PricingPage());
    expect(screen.getByText("Choose Your MANSA Experience")).toBeInTheDocument();
    expect(screen.getAllByText("Core").length).toBeGreaterThan(0);
    expect(screen.getByText("$19.99")).toBeInTheDocument();
    expect(screen.getByText("$34.99")).toBeInTheDocument();
    expect(screen.getByText("$69.99")).toBeInTheDocument();
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
  });

  it("includes the shared public nav so a visitor can always get back to the other public pages", async () => {
    render(await PricingPage());
    expect(screen.getAllByRole("link", { name: "How It Works" }).length).toBeGreaterThan(0);
  });

  it("marks Pro as Most Popular, and only Pro", async () => {
    render(await PricingPage());
    const tags = screen.getAllByText("Most Popular");
    expect(tags).toHaveLength(1);
  });

  it("renders the full comparison matrix with real table semantics", async () => {
    render(await PricingPage());
    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    const withinTable = within(table);
    expect(withinTable.getByText("Command Center")).toBeInTheDocument();
    expect(withinTable.getByRole("rowheader", { name: /Track Record/ })).toBeInTheDocument();
    expect(withinTable.getByText(/Telegram Companion/)).toBeInTheDocument();
    expect(screen.getByText(/Not yet operational in DEV/)).toBeInTheDocument();
  });

  it("never invents numeric usage limits (message counts, refresh intervals, token/parlay limits)", async () => {
    render(await PricingPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d+\s*(messages|requests|tokens|parlays)\b/i);
    expect(text).not.toMatch(/token/i);
    expect(text).not.toMatch(/compute unit/i);
    expect(text).not.toMatch(/API budget/i);
  });

  it("never implements or references checkout, Stripe, or annual/discount pricing", async () => {
    render(await PricingPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/stripe/i);
    expect(text).not.toMatch(/checkout/i);
    expect(text).not.toMatch(/annual/i);
    expect(text).not.toMatch(/save \d+%/i);
    expect(text).not.toMatch(/\/yr\b/i);
  });

  it("never claims fabricated testimonials or performance stats", async () => {
    render(await PricingPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/win rate/i);
    expect(text).not.toMatch(/\bROI\b/);
  });

  it("signed-out CTA is Create Account on every plan card", async () => {
    render(await PricingPage());
    const links = screen.getAllByRole("link", { name: "Create Account" });
    expect(links.length).toBeGreaterThanOrEqual(3);
  });

  it("signed-in CTA is Open MANSA -> /today on every plan card", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    render(await PricingPage());
    const links = screen.getAllByRole("link", { name: "Open MANSA" });
    expect(links.length).toBeGreaterThanOrEqual(3);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "/today");
    }
  });
});
