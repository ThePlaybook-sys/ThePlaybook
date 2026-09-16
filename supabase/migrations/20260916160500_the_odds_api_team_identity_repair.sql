-- Odds Team Identity Repair (2026-09-16, HQ-authorized "ODDS TEAM IDENTITY
-- REPAIR + AUTONOMOUS PROOF"). Completes The Odds API's canonical team
-- coverage from 17/32 to 32/32.
--
-- WHY THE GAP EXISTED. Migration 20260814050000 seeded `the_odds_api`
-- mappings ONLY from teams confirmed by real fixture evidence, and recorded
-- in its own header that "26 teams have zero The Odds API fixture evidence --
-- reported to Mac as unverified rather than filled in from general
-- knowledge," per the standing instruction never to fabricate a provider
-- identifier. That discipline was correct and is NOT relaxed here. Nine more
-- teams were added as evidence arrived, reaching 17.
--
-- WHY THE 15 BELOW ARE NOW EVIDENCE, NOT GENERAL KNOWLEDGE. The Odds API
-- emitted every one of these strings verbatim in a real production response.
--
--   PROVENANCE: Railway deploy log, service `cron-odds-worker`
--   (04b53e11-e8bf-40ad-9e07-15f465ced2ee), environment dev
--   (5c1e630f-f4b7-4d99-933a-231bf1aaca91), deployment
--   a1a606e3-8526-45c9-b8a2-f58935474c57, cron tick of
--   2026-09-16 13:00:26 UTC (and identically on every subsequent tick
--   through 16:01:37 UTC).
--
--   The worker's own `unresolved_events` payload named each missing team
--   in the form:
--     "<event_id>: unknown team(s), no team_provider_ids mapping:
--      ['Atlanta Falcons', 'Carolina Panthers']"
--
--   Those bracketed strings ARE The Odds API's own `home_team`/`away_team`
--   field values, passed through `odds_game_linking` untransformed. They are
--   observed provider output, transcribed, not recalled.
--
-- WHY A PLAIN NAME JOIN IS EXACT IDENTITY HERE, NOT FUZZY MATCHING. For this
-- provider `provider_team_id` IS the full team name -- that is the vendor's
-- own identifier scheme, not a display label we are parsing. Every one of the
-- 17 rows already present follows the identical pattern ("Baltimore Ravens"
-- -> Baltimore Ravens). So `t.name = mapping.provider_team_id` is an exact
-- string equality between the provider's identifier and the canonical
-- identifier, with no normalization, no casefolding, no whitespace handling,
-- no abbreviation inference and no nearest-match. A string that did not match
-- exactly would insert nothing rather than resolve to something close.
--
-- Verified read-only BEFORE this migration was written, per row, all 15:
--   * exactly 1 canonical `teams` row matches the string exactly (never 0, never >1);
--   * the `provider_team_id` is not already taken by another team;
--   * the canonical team does not already hold a conflicting `the_odds_api` identity.
-- Zero conflicts and zero ambiguities were found. Had any row failed any of
-- those three checks it would have been left out rather than guessed.
--
-- WHAT THIS UNBLOCKS. Ten of the sixteen Week 2 games could not link, so they
-- could never persist an odds snapshot; `last_polled_at` is derived from
-- `odds_snapshots.captured_at`, so a game with no snapshot reads as never
-- polled and is due on EVERY tick, permanently. Each tick spent a real paid
-- bulk call and persisted nothing -- 3 credits x 96 ticks/day. These 15 rows
-- close that loop.
--
-- No schema change. Reversible by deleting exactly these 15 rows.

insert into team_provider_ids (team_id, provider_name, provider_team_id)
select t.id, 'the_odds_api', mapping.provider_team_id
from (values
  ('Atlanta Falcons'),
  ('Carolina Panthers'),
  ('Cincinnati Bengals'),
  ('Cleveland Browns'),
  ('Denver Broncos'),
  ('Houston Texans'),
  ('Indianapolis Colts'),
  ('Jacksonville Jaguars'),
  ('Los Angeles Rams'),
  ('New Orleans Saints'),
  ('New York Giants'),
  ('New York Jets'),
  ('Pittsburgh Steelers'),
  ('Tampa Bay Buccaneers'),
  ('Tennessee Titans')
) as mapping(provider_team_id)
join teams t on t.name = mapping.provider_team_id
-- Never overwrite or duplicate an existing identity on either side.
where not exists (
  select 1 from team_provider_ids existing
  where existing.provider_name = 'the_odds_api'
    and existing.team_id = t.id
)
on conflict (provider_name, provider_team_id) do nothing;
