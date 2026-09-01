import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/app/lib/supabase/server";
import { resolveRequestOrigin } from "@/app/lib/request-origin";

/**
 * Exchanges a Supabase email-confirmation/magic-link `code` for a real
 * session and sets the SSR cookies, then hands off to `/` -- root
 * routing decides onboarding vs. Today from there. Required regardless
 * of whether DEV's email-confirmation setting is on or off: it's the
 * standard landing target for any Supabase auth email link, confirmed
 * account, magic link, or (if OAuth is ever authorized later) an OAuth
 * redirect. Redirect target is built from `resolveRequestOrigin` (M6
 * defect #3), never the request's raw `origin` -- see that module for
 * why: behind Railway's proxy, `new URL(request.url).origin` reflects
 * the container's internal port, not the deployed public origin.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");

  if (code) {
    const supabase = createClient();
    await supabase.auth.exchangeCodeForSession(code);
  }

  return NextResponse.redirect(`${resolveRequestOrigin(request)}/`);
}
