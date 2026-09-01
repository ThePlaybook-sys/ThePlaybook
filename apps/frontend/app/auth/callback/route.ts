import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/app/lib/supabase/server";

/**
 * Exchanges a Supabase email-confirmation/magic-link `code` for a real
 * session and sets the SSR cookies, then hands off to `/` -- root
 * routing decides onboarding vs. Today from there. Required regardless
 * of whether DEV's email-confirmation setting is on or off: it's the
 * standard landing target for any Supabase auth email link, confirmed
 * account, magic link, or (if OAuth is ever authorized later) an OAuth
 * redirect.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  if (code) {
    const supabase = createClient();
    await supabase.auth.exchangeCodeForSession(code);
  }

  return NextResponse.redirect(`${origin}/`);
}
