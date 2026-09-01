import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/**
 * Refreshes the Supabase session cookie on every navigable request --
 * the standard Next.js App Router SSR pattern. `getUser()` (not
 * `getSession()`) is called deliberately: it round-trips to Supabase
 * Auth to revalidate the token, rather than trusting whatever the
 * cookie currently claims, so a stale/tampered/expired session is
 * caught here rather than silently trusted by a Server Component.
 * Server Components/Actions then read the now-fresh cookie via
 * `getSession()` without needing to re-validate themselves.
 */
export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => {
            response.cookies.set(name, value, options);
          });
        },
      },
    },
  );

  await supabase.auth.getUser();

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|api/demo|demo|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
