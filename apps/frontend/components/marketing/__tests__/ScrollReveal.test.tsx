import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { ScrollReveal } from "../ScrollReveal";

describe("ScrollReveal", () => {
  const originalIO = global.IntersectionObserver;

  afterEach(() => {
    global.IntersectionObserver = originalIO;
  });

  it("renders its children regardless of reveal state -- content is never removed from the DOM", () => {
    render(
      <ScrollReveal>
        <p>Hero content</p>
      </ScrollReveal>,
    );
    expect(screen.getByText("Hero content")).toBeInTheDocument();
  });

  it("defaults to visible when IntersectionObserver is unavailable, never permanently hidden", () => {
    // @ts-expect-error -- deliberately simulating an environment without it
    delete global.IntersectionObserver;

    render(
      <ScrollReveal>
        <p>Always visible</p>
      </ScrollReveal>,
    );

    const wrapper = screen.getByText("Always visible").parentElement;
    expect(wrapper).toHaveClass("opacity-100");
    expect(wrapper).not.toHaveClass("opacity-0");
  });

  it("starts hidden and reveals once the observed element intersects, then stops observing", () => {
    const observe = vi.fn();
    const unobserve = vi.fn();
    const disconnect = vi.fn();
    let capturedCallback: IntersectionObserverCallback = () => {};

    class FakeIntersectionObserver {
      constructor(callback: IntersectionObserverCallback) {
        capturedCallback = callback;
      }
      observe = observe;
      unobserve = unobserve;
      disconnect = disconnect;
    }

    // @ts-expect-error -- test double, not a full IntersectionObserver
    global.IntersectionObserver = FakeIntersectionObserver;

    render(
      <ScrollReveal>
        <p>Panel content</p>
      </ScrollReveal>,
    );

    expect(observe).toHaveBeenCalled();
    const wrapper = screen.getByText("Panel content").parentElement as HTMLElement;
    expect(wrapper).toHaveClass("opacity-0");

    act(() => {
      capturedCallback(
        [{ isIntersecting: true, target: wrapper } as unknown as IntersectionObserverEntry],
        {} as IntersectionObserver,
      );
    });

    expect(wrapper).toHaveClass("opacity-100");
    expect(unobserve).toHaveBeenCalled();
  });

  it("applies a transitionDelay style when delayMs is provided, for staggered reveals", () => {
    render(
      <ScrollReveal delayMs={160}>
        <p>Staggered</p>
      </ScrollReveal>,
    );
    const wrapper = screen.getByText("Staggered").parentElement as HTMLElement;
    expect(wrapper.style.transitionDelay).toBe("160ms");
  });
});
