"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Container } from "@/components/ds";

const NAV_LINKS = [
  { href: "/how-it-works", label: "How It Works" },
  { href: "/features", label: "Features" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
];

/**
 * Public Web M1 -- the shared header for every unauthenticated MANSA
 * route (`/`, and the M2-placeholder `/how-it-works`, `/features`,
 * `/pricing`, `/about`). A new, distinct component from `AppNav`
 * (`components/nav/AppNav.tsx`), which is the authenticated app's own
 * five-destination nav and is never shown to a signed-out visitor --
 * this is not a modification of that component, and the two are never
 * mounted together.
 *
 * "Sign In" and "Create Account" both route into the one existing
 * `/sign-in` `AuthForm` (tabbed sign-in/sign-up) -- `?mode=sign-up`
 * preselects the Create Account tab (see `app/sign-in/page.tsx`).
 * Neither link is a second authentication implementation.
 *
 * Mobile: a disclosure toggle (>=44px tap target, matching `AppNav`'s
 * own mobile-tap-target discipline) rather than a compressed desktop
 * bar -- collapsed by default below the `lg` breakpoint, expanded to a
 * normal inline row above it.
 */
export function PublicNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="border-b border-border bg-surface-page/80 backdrop-blur">
      <Container className="flex items-center justify-between gap-md py-sm">
        <Link href="/" className="flex items-baseline gap-sm" onClick={() => setOpen(false)}>
          <span className="text-heading font-bold text-text-primary">MANSA</span>
          <span className="text-label uppercase tracking-wide text-text-meta">Sports Intelligence</span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-lg lg:flex">
          {NAV_LINKS.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive ? "page" : undefined}
                className={`text-label ${
                  isActive ? "text-text-primary" : "text-text-secondary hover:text-text-primary"
                } transition-colors duration-micro`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden items-center gap-sm lg:flex">
          <Link
            href="/sign-in"
            className="flex min-h-[44px] items-center rounded-sm px-md text-label text-text-secondary transition-colors duration-micro hover:text-text-primary"
          >
            Sign In
          </Link>
          <Link
            href="/sign-in?mode=sign-up"
            className="flex min-h-[44px] items-center rounded-sm bg-accent px-md text-label font-semibold text-surface-page transition-opacity duration-micro hover:opacity-90"
          >
            Create Account
          </Link>
        </div>

        <button
          type="button"
          aria-expanded={open}
          aria-controls="public-nav-mobile-menu"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((value) => !value)}
          className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-sm text-text-primary lg:hidden"
        >
          <span aria-hidden="true" className="text-heading">
            {open ? "✕" : "☰"}
          </span>
        </button>
      </Container>

      {open && (
        <div id="public-nav-mobile-menu" className="border-t border-border lg:hidden">
          <Container className="flex flex-col gap-xs py-md">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                aria-current={pathname === link.href ? "page" : undefined}
                className="flex min-h-[44px] items-center text-body text-text-secondary"
              >
                {link.label}
              </Link>
            ))}
            <div className="mt-sm flex flex-col gap-sm border-t border-border pt-sm">
              <Link
                href="/sign-in"
                onClick={() => setOpen(false)}
                className="flex min-h-[44px] items-center justify-center rounded-sm border border-border text-label text-text-primary"
              >
                Sign In
              </Link>
              <Link
                href="/sign-in?mode=sign-up"
                onClick={() => setOpen(false)}
                className="flex min-h-[44px] items-center justify-center rounded-sm bg-accent text-label font-semibold text-surface-page"
              >
                Create Account
              </Link>
            </div>
          </Container>
        </div>
      )}
    </header>
  );
}
