"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export interface ScrollRevealProps {
  children: ReactNode;
  className?: string;
  /** Stagger multiple reveals on the same viewport entrance (ms). */
  delayMs?: number;
}

/**
 * Public Web M1 -- restrained scroll-reveal wrapper (HQ's "gentle
 * product-panel entrance / scroll reveals" motion requirement, "no
 * flashing odds, no casino animation, no fake real-time activity").
 *
 * Defaults to visible and only opts INTO a hidden starting state once
 * mounted client-side with a working `IntersectionObserver` -- content
 * is never permanently hidden if JS fails to run, if this renders in an
 * environment without `IntersectionObserver` (older browser, or a test
 * environment that doesn't polyfill it), or if the element is already
 * in view on mount. Reveals once and stops observing -- never replays
 * on scroll-back-up, matching the "no repeated distracting animation"
 * intent alongside globals.css's own `prefers-reduced-motion` rule
 * (which independently collapses the transition to instant regardless
 * of this component's state).
 */
export function ScrollReveal({ children, className, delayMs = 0 }: ScrollRevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    setReady(true);

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15 },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const hidden = ready && !visible;

  return (
    <div
      ref={ref}
      className={["transition-all duration-state ease-out", hidden ? "translate-y-3 opacity-0" : "translate-y-0 opacity-100", className]
        .filter(Boolean)
        .join(" ")}
      style={delayMs ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </div>
  );
}
