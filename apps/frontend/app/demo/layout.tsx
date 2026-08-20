import { cookies } from "next/headers";
import Link from "next/link";
import { DemoModeBanner } from "./DemoModeBanner";
import { LoginForm } from "./LoginForm";
import { DEMO_OPERATOR_COOKIE } from "../api/demo/_gateway";

/**
 * Shared Demo layout (DEMO-4). The persistent DEMO MODE banner renders
 * here, unconditionally, before anything else -- individual pages never
 * remember to add it themselves, and it survives navigation, screenshots,
 * and every page under `/demo` including the future Component Gallery.
 *
 * Cookie presence is checked here (server-side) as a coarse gate: if
 * absent, the operator sees the login form instead of any dashboard
 * content. This is NOT a full re-validation of the token's correctness
 * on every navigation (that would mean a server-side call to API Gateway
 * on every single page load) -- a stale/wrong cookie still gets caught
 * the moment a page's own data fetch 401s, same as any other API error.
 */
export default function DemoLayout({ children }: { children: React.ReactNode }) {
  const hasToken = Boolean(cookies().get(DEMO_OPERATOR_COOKIE)?.value);

  return (
    <div style={{ minHeight: "100vh", background: "#fafafa" }}>
      <DemoModeBanner />
      {hasToken ? (
        <div style={{ fontFamily: "system-ui, sans-serif" }}>
          <nav
            style={{
              display: "flex",
              gap: "1rem",
              padding: "0.75rem 1rem",
              borderBottom: "1px solid #e5e5e5",
              background: "#fff",
              fontSize: "0.9rem",
            }}
          >
            <Link href="/demo">Operator Dashboard</Link>
            <Link href="/demo/games">Games</Link>
          </nav>
          <main style={{ padding: "1.5rem" }}>{children}</main>
        </div>
      ) : (
        <LoginForm />
      )}
    </div>
  );
}
