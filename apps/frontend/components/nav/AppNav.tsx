"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Container } from "@/components/ds";

const LINKS = [
  { href: "/today", label: "Today" },
  { href: "/recommendations", label: "Recommendations" },
  { href: "/history", label: "History" },
  { href: "/track-record", label: "Track Record" },
  { href: "/account", label: "Account" },
];

/**
 * The one persistent nav across every authenticated destination (Phase
 * 6 Milestone 6). A client component (M7 polish) so the current
 * destination can be marked with `aria-current="page"` and a visible
 * active state -- screen-reader and sighted users alike previously had
 * no way to tell which of the five destinations they were on. Each
 * link is a real >=44px tap target (M7's mobile-scrutiny requirement;
 * the original `py-xs` row was ~25px tall). Horizontally scrollable
 * rather than wrapped on narrow viewports, so five destinations never
 * overflow or crowd a small screen; on wider viewports the row simply
 * doesn't overflow, so it never compresses into a cramped desktop bar
 * either -- the same markup handles both without a second nav design.
 */
export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="border-b border-border bg-surface-card" aria-label="Primary">
      <Container>
        <div className="flex gap-lg overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          {LINKS.map((link) => {
            const isActive = pathname === link.href || pathname?.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive ? "page" : undefined}
                className={`flex min-h-[44px] shrink-0 items-center whitespace-nowrap border-b-2 border-transparent text-label ${
                  isActive ? "mansa-illuminated-edge-bottom text-text-primary" : "text-text-secondary"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </Container>
    </nav>
  );
}
