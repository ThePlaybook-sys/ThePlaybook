import Link from "next/link";
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
 * 6 Milestone 6) -- without it, /today through /account were only
 * reachable by typing a URL directly. A plain server component (no
 * active-route highlighting, which would require client-side
 * `usePathname`) to keep this app's established Server-Component-first
 * architecture rather than introducing client JS for a cosmetic detail.
 * Horizontally scrollable rather than wrapped on narrow viewports, so
 * five destinations never overflow or crowd a small screen.
 */
export function AppNav() {
  return (
    <nav className="border-b border-border-default bg-surface-card" aria-label="Primary">
      <Container>
        <div className="flex gap-lg overflow-x-auto py-sm" style={{ scrollbarWidth: "none" }}>
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="shrink-0 whitespace-nowrap py-xs text-label text-text-secondary"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </Container>
    </nav>
  );
}
