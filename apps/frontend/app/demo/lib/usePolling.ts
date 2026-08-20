"use client";

import { useEffect, useRef, useState } from "react";

/**
 * DEMO-4's approved v1 polling policy (Mac's explicit decision -- plain
 * polling, no WebSockets/SSE/Supabase Realtime): ~3s while a scenario is
 * ACTIVE (running), ~10s while a scenario is loaded but IDLE, and paused
 * entirely when nothing is relevant to poll or the tab isn't visible.
 * Treated here as a v1 UX policy, not a permanent architectural
 * requirement -- these two numbers are the only thing that would need to
 * change later.
 */
const ACTIVE_INTERVAL_MS = 3000;
const IDLE_INTERVAL_MS = 10000;

export type PollingActivity = "active" | "idle" | "stopped";

/**
 * `getActivity` is called with the LAST fetched value (null before the
 * first fetch completes) to decide the cadence for the NEXT poll -- this
 * lets the cadence depend on the data itself (e.g. scenario status)
 * without needing a second, separately-polling hook instance just to
 * learn that status first.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  getActivity: (data: T | null) => PollingActivity
): { data: T | null; error: string | null; loading: boolean; refresh: () => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const getActivityRef = useRef(getActivity);
  getActivityRef.current = getActivity;

  const run = async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (cancelled) return;
      const result = document.hidden ? null : await run();
      if (cancelled) return;
      const activity = getActivityRef.current(result);
      if (activity === "stopped") return;
      timer = setTimeout(tick, activity === "active" ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS);
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // Intentionally empty deps -- this hook polls for the lifetime of the
    // component; callers who need a fresh poll on demand use `refresh()`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { data, error, loading, refresh: async () => void (await run()) };
}
