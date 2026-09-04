-- Pre-9/9 Data Preservation Readiness: news_article_history (Volume 3 §4.4 addition)
--
-- Closes the "News has no history" gap re-confirmed by both the Phase 7
-- Milestone 7.0 audit and the Phase 8 Milestone 8.0 audit --
-- `daily_game_intelligence.news` remains current-state-only and is NOT
-- migrated, replaced, or altered by this migration; this is new,
-- additive history alongside it.
--
-- Insert-once-per-(provider_name, article_url), NOT "every poll is a new
-- row": unlike odds_snapshots (where a changed value each poll is a
-- meaningful new row), a news article's content is typically immutable
-- once published, so the unique index below enforces "capture the first
-- sighting only," making `ingested_at` a reliable answer to "when did
-- MANSA first learn this" -- the actual fact this table exists to
-- preserve. Application-layer writes use
-- `Prefer: resolution=ignore-duplicates` against this same unique key, so
-- a re-sighted article on a later News Worker cycle is a no-op, never a
-- duplicate row and never an overwrite of the original `ingested_at`.
--
-- `related_player_ids` is new relative to the current `NewsArticle`
-- model (`app.adapters.models`), which carries no player-level field at
-- all -- added here since injury/inactive/trade news is fundamentally
-- player-scoped, not only team-scoped (Volume 4 §8.6's own connection
-- to future Contextual Performance Intelligence).
--
-- Licensing/redistribution caution, explicitly not resolved by this
-- migration: `summary`/`raw_payload` are intended for metadata-level
-- content only (headline/description), never full article body text,
-- until each provider's commercial redistribution terms are
-- independently confirmed (GNews Essential's own commercial-suitability
-- question remains open per docs/ops/news-provider-validation-gnews-2026-09-03.md).
-- Not enforced at the database level -- an application-layer discipline,
-- same as several other content-shape conventions in this schema.

create table news_article_history (
  id uuid primary key default gen_random_uuid(),
  provider_name text not null,
  provider_article_id text,
  article_url text not null,
  published_at timestamptz,
  ingested_at timestamptz not null default now(),
  headline text,
  summary text,
  source_name text,
  related_team_ids jsonb,
  related_player_ids jsonb,
  raw_payload jsonb,
  created_at timestamptz not null default now()
);
create unique index idx_news_article_history_identity on news_article_history(provider_name, article_url);
create index idx_news_article_history_ingested on news_article_history(ingested_at desc);

alter table news_article_history enable row level security;
create policy "public_read" on news_article_history for select using (true);

create trigger trg_block_news_article_history_update
  before update on news_article_history
  for each row execute function block_snapshot_updates();
