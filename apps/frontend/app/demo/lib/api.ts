"use client";

/**
 * Browser-side fetch helper for the Operator Dashboard. Every call goes
 * to this Next.js app's own `/api/demo/*` route handlers -- same origin,
 * no CORS, no token visible to this file at all (the httpOnly cookie is
 * attached automatically by the browser; this code never reads or sends
 * it directly).
 */
export class DemoApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/demo/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new DemoApiError(response.status, text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const demoApi = {
  listScenarios: () => request<import("./types").ScenarioSummary[]>("scenarios"),
  getStatus: () => request<import("./types").DemoStatus>("status"),
  loadScenario: (name: string) =>
    request<import("./types").DemoStatus>(`scenarios/${encodeURIComponent(name)}/load`, { method: "POST" }),
  step: () => request<import("./types").DemoStatus>("step", { method: "POST" }),
  runToCheckpoint: () => request<import("./types").DemoStatus>("run-to-checkpoint", { method: "POST" }),
  runToCompletion: () => request<import("./types").DemoStatus>("run", { method: "POST" }),
  reset: () => request<{ reset: boolean; deleted_counts: Record<string, number> }>("reset", { method: "POST" }),
  listGames: () => request<import("./types").GameRow[]>("games"),
  getGameIntelligence: (gameId: string) =>
    request<import("./types").DailyGameIntelligence>(`games/${encodeURIComponent(gameId)}/intelligence`),
};
