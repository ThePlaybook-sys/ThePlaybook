-- Pre-Phase-6 Operational Readiness Gate, Decision 5 (2026-08-27).
--
-- Closes a real inefficiency the readiness gate's own inspection found:
-- (master_refresh_run_id, game_id) is persistence-idempotent through
-- recommendations.correlation_id (Milestone 4.9), but nothing durable
-- previously distinguished "this correlation's full agent-committee
-- cycle already ran to completion" from "a recommendations row exists
-- but the cycle crashed partway through" -- so a repeated worker-
-- scheduled cron fire against the same still-eligible master_refresh_run
-- would re-run the entire (expensive) agent committee every time.
--
-- cycle_completed_at is set exactly once, as the very last step of a
-- successful app.orchestration.recommendation_worker.run_game_recommendation
-- call (Milestone 4.9's own orchestration, unchanged) -- never touched
-- on any other code path, never overwritten once set. A cycle that
-- crashed/raised before reaching that point leaves it NULL forever,
-- which is exactly what "failed/incomplete attempts must remain
-- retryable" requires: nothing here blocks a retry, it only skips
-- recomputation for a correlation that is durably known to have
-- already finished.
alter table recommendations
  add column cycle_completed_at timestamptz;

comment on column recommendations.cycle_completed_at is
  'Pre-Phase-6 Operational Readiness Gate, Decision 5: set once, by app.orchestration.recommendation_worker.run_game_recommendation, as the last step of a successfully-completed agent-committee cycle for this row''s correlation_id. NULL means never completed (never started, or crashed partway through) -- always safely retryable. Never updated after being set.';
