import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/app/lib/supabase/server";
import { resolveRequestOrigin } from "@/app/lib/request-origin";

/** Real sign-out (Phase 6 Milestone 6) -- clears the Supabase session
 * cookies server-side via `auth.signOut()`, then redirects to sign-in.
 * POST-only (invoked from a `<form method="post">`, never a link) so a
 * prefetch or crawler can never sign a user out as a side effect.
 * Redirect target is built from `resolveRequestOrigin` (M6 defect #3),
 * never `request.url` directly -- see that module for why. */
export async function POST(request: NextRequest) {
  const supabase = createClient();
  await supabase.auth.signOut();
  return NextResponse.redirect(new URL("/sign-in", resolveRequestOrigin(request)));
}
