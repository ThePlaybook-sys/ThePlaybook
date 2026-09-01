import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppNav } from "../AppNav";

const usePathnameMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

describe("AppNav", () => {
  it("links to all five authenticated destinations", () => {
    usePathnameMock.mockReturnValue("/today");
    render(<AppNav />);
    expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute("href", "/today");
    expect(screen.getByRole("link", { name: "Recommendations" })).toHaveAttribute("href", "/recommendations");
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "/history");
    expect(screen.getByRole("link", { name: "Track Record" })).toHaveAttribute("href", "/track-record");
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("href", "/account");
  });

  it("mobile-safe structure: the link row scrolls horizontally rather than wrapping or overflowing", () => {
    usePathnameMock.mockReturnValue("/today");
    const { container } = render(<AppNav />);
    const row = container.querySelector("nav > div > div");
    expect(row).toHaveClass("overflow-x-auto");
  });

  it("real M7 fix: every link is a >=44px tap target -- the original row was ~25px tall", () => {
    usePathnameMock.mockReturnValue("/today");
    render(<AppNav />);
    expect(screen.getByRole("link", { name: "Today" })).toHaveClass("min-h-[44px]");
  });

  it("marks the current destination with aria-current=page, including a nested detail route", () => {
    usePathnameMock.mockReturnValue("/recommendations/abc123");
    render(<AppNav />);
    expect(screen.getByRole("link", { name: "Recommendations" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Today" })).not.toHaveAttribute("aria-current");
  });

  it("M7.3: never links to the dev-only MANSA UI Preview -- it is not a real product destination", () => {
    usePathnameMock.mockReturnValue("/today");
    const { container } = render(<AppNav />);
    expect(container.innerHTML).not.toMatch(/\/dev\/command-center-preview/);
    expect(screen.queryByRole("link", { name: /preview/i })).not.toBeInTheDocument();
  });
});
