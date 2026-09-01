import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * Server-side Supabase client (Server Components, Server Actions, Route
 * Handlers). Reads/writes the SSR session cookies `middleware.ts` keeps
 * fresh -- this is the one and only source of auth truth for the
 * frontend (Phase 6 Milestone 6, replacing M3's placeholder
 * `pb_session_token` cookie read, which never issued, refreshed, or
 * validated anything itself).
 *
 * `setAll` is wrapped in try/catch because a Server Component cannot set
 * cookies (Next.js throws) -- harmless there since `middleware.ts`
 * already refreshed the session for this request; only Server
 * Actions/Route Handlers actually need to persist a refreshed cookie.
 */
export function createClient() {
  const cookieStore = cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options);
            });
          } catch {
            // Called from a Server Component -- no-op, see docstring above.
          }
        },
      },
    },
  );
}
