// Mirrors app/demo/router.py's JSON response shapes (sports-intel-layer) --
// kept intentionally loose (mostly `unknown`/`Record<string, unknown>` for
// worker result payloads) rather than fully typed, since those shapes
// belong to Phase 3's own worker Result dataclasses and are expected to
// grow; this dashboard's job is to display them, not to own their schema.

export interface ScenarioSummary {
  name: string;
  scenario_id: string;
  title: string;
  description: string;
  version: string;
  step_count: number;
}

export interface StepOutcome {
  step_index: number;
  action: string;
  virtual_now: string;
  result: Record<string, unknown> | null;
  checkpoint_note: string | null;
  error: string | null;
}

export interface DemoStatus {
  scenario_id: string | null;
  title: string | null;
  status: "idle" | "loaded" | "running" | "completed" | "failed";
  virtual_now: string | null;
  step_index: number;
  total_steps: number;
  is_finished: boolean;
  outcomes: StepOutcome[];
  checkpoints: string[];
  errors: string[];
}

export interface GameRow {
  id: string;
  external_provider_id: string | null;
  home_team: string;
  away_team: string;
  scheduled_start: string;
  stadium: string | null;
  status: string;
  season_type: string | null;
  week: number | null;
  venue_lat: number | null;
  venue_long: number | null;
  venue_type: string | null;
  finalized_at: string | null;
  final_score: { home: number; away: number } | null;
}

export type DailyGameIntelligence = Record<string, unknown> & { game_id: string };
