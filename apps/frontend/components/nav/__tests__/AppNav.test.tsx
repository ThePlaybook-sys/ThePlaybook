import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AppNav } from "../AppNav";

describe("AppNav", () => {
  it("links to all five authenticated destinations", () => {
    render(<AppNav />);
    expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute("href", "/today");
    expect(screen.getByRole("link", { name: "Recommendations" })).toHaveAttribute("href", "/recommendations");
    expect(screen.getByRole("link", { name: "History" })).toHaveAttribute("href", "/history");
    expect(screen.getByRole("link", { name: "Track Record" })).toHaveAttribute("href", "/track-record");
    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("href", "/account");
  });

  it("mobile-safe structure: the link row scrolls horizontally rather than wrapping or overflowing", () => {
    const { container } = render(<AppNav />);
    const row = container.querySelector("nav > div > div");
    expect(row).toHaveClass("overflow-x-auto");
  });
});
