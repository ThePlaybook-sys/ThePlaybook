import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PublicNav } from "../PublicNav";

const usePathnameMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => usePathnameMock(),
}));

describe("PublicNav", () => {
  it("links to all four public destinations", () => {
    usePathnameMock.mockReturnValue("/");
    render(<PublicNav />);
    expect(screen.getByRole("link", { name: "How It Works" })).toHaveAttribute("href", "/how-it-works");
    expect(screen.getByRole("link", { name: "Features" })).toHaveAttribute("href", "/features");
    expect(screen.getByRole("link", { name: "Pricing" })).toHaveAttribute("href", "/pricing");
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
  });

  it("routes Sign In and Create Account into the existing /sign-in auth system, never a second implementation", () => {
    usePathnameMock.mockReturnValue("/");
    render(<PublicNav />);
    const signInLinks = screen.getAllByRole("link", { name: "Sign In" });
    const createAccountLinks = screen.getAllByRole("link", { name: "Create Account" });
    expect(signInLinks[0]).toHaveAttribute("href", "/sign-in");
    expect(createAccountLinks[0]).toHaveAttribute("href", "/sign-in?mode=sign-up");
  });

  it("marks the current public destination with aria-current=page", () => {
    usePathnameMock.mockReturnValue("/pricing");
    render(<PublicNav />);
    expect(screen.getAllByRole("link", { name: "Pricing" })[0]).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: "About" })[0]).not.toHaveAttribute("aria-current");
  });

  it("mobile menu toggle is a real >=44px tap target and opens/closes a disclosure", () => {
    usePathnameMock.mockReturnValue("/");
    render(<PublicNav />);
    const toggle = screen.getByRole("button", { name: "Open menu" });
    expect(toggle).toHaveClass("min-h-[44px]");
    expect(toggle).toHaveClass("min-w-[44px]");

    expect(screen.queryByRole("link", { name: "How It Works" })).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close menu" })).toBeInTheDocument();
    expect(document.getElementById("public-nav-mobile-menu")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close menu" }));
    expect(document.getElementById("public-nav-mobile-menu")).not.toBeInTheDocument();
  });

  it("brand mark links back to the public landing page at /", () => {
    usePathnameMock.mockReturnValue("/pricing");
    render(<PublicNav />);
    expect(screen.getByRole("link", { name: "MANSA Sports Intelligence" })).toHaveAttribute("href", "/");
  });
});
