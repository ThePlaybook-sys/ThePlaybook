import Link from "next/link";
import { Container, Text } from "@/components/ds";

const NAV_LINKS = [
  { href: "/how-it-works", label: "How It Works" },
  { href: "/features", label: "Features" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
];

/** Public Web M1 -- the shared footer for every unauthenticated MANSA
 * route. Deliberately minimal (no Privacy/Terms links -- Volume 1 §10's
 * privacy policy does not exist yet, per `app/layout.tsx`'s own
 * Sentry-config comment; linking either now would point at a page that
 * doesn't exist). Copyright year is computed, never a value that goes
 * stale. */
export function PublicFooter() {
  return (
    <footer className="border-t border-border py-xl">
      <Container className="flex flex-col items-center gap-lg text-center sm:flex-row sm:items-center sm:justify-between sm:text-left">
        <div className="flex items-baseline gap-sm">
          <span className="text-heading font-bold text-text-primary">MANSA</span>
          <span className="text-label uppercase tracking-wide text-text-meta">Sports Intelligence</span>
        </div>

        <nav aria-label="Footer" className="flex flex-wrap justify-center gap-lg">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-label text-text-secondary transition-colors duration-micro hover:text-text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <Text variant="label" as="span" className="normal-case text-text-meta">
          © {new Date().getFullYear()} MANSA. All rights reserved.
        </Text>
      </Container>
    </footer>
  );
}
