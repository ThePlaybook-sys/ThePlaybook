import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import AboutPage from "../page";

const getCurrentUserMock = vi.fn();

vi.mock("@/app/lib/auth", () => ({
  getCurrentUser: () => getCurrentUserMock(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/about",
}));

describe("AboutPage (Public Web M2)", () => {
  beforeEach(() => {
    getCurrentUserMock.mockReset();
    getCurrentUserMock.mockResolvedValue(null);
  });

  it("explains why MANSA exists, not the M1 placeholder copy", async () => {
    render(await AboutPage());
    expect(screen.getByRole("heading", { level: 1, name: "About MANSA" })).toBeInTheDocument();
    expect(screen.getByText("Why MANSA Exists")).toBeInTheDocument();
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
  });

  it("never fabricates founder history, statistics, or testimonials", async () => {
    render(await AboutPage());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/founded in|our founder|ceo|ex-vegas/i);
    expect(text).not.toMatch(/\d+%\s*(accurate|win|success)/i);
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();
  });

  it("Web M1 routing correction: signed-out CTA is Create Account", async () => {
    render(await AboutPage());
    expect(screen.getAllByRole("link", { name: "Create Account" }).length).toBeGreaterThan(0);
  });

  it("Web M1 routing correction: signed-in CTA is Open MANSA -> /today", async () => {
    getCurrentUserMock.mockResolvedValue({ id: "u1", email: "user@example.com" });
    render(await AboutPage());
    const openMansaLinks = screen.getAllByRole("link", { name: "Open MANSA" });
    expect(openMansaLinks.length).toBeGreaterThan(0);
    for (const link of openMansaLinks) {
      expect(link).toHaveAttribute("href", "/today");
    }
  });
});
