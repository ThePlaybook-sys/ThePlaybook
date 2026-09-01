"use client";

import { createBrowserClient } from "@supabase/ssr";

/**
 * Browser-side Supabase client -- used only for `auth.*` calls
 * (signInWithPassword/signUp/signOut/onAuthStateChange). This project's
 * established architecture never queries Supabase tables directly from
 * the browser (`.from(...)`) -- every data read/write goes through
 * api-gateway, which holds the service-role key. The anon key exposed
 * here is the one Supabase key that is safe for the browser: it can
 * only ever act as the currently-authenticated user, under RLS.
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
