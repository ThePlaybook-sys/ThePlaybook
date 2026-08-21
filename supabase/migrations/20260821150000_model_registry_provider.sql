-- Milestone 4.4 pre-check (Decision 1, 2026-08-21): model_registry gains an
-- explicit provider column -- ModelRouter (Milestone 4.3) previously had to
-- infer provider from model-name prefix ("claude-" -> anthropic, "gpt-" ->
-- openai), correctly flagged as an anti-pattern: model names identify
-- models, they should not secretly double as provider identifiers.
--
-- Deliberately NOT a `check (provider in ('openai','anthropic'))` constraint
-- -- per explicit instruction not to permanently hardcode the database to
-- today's two vendors merely to gain DB-level validation (the same rigid-
-- CHECK pattern game_provider_ids/team_provider_ids/player_provider_ids.
-- provider_name already use, each requiring its own follow-up migration for
-- a new vendor). `provider` is `text not null` only -- validated at the
-- application layer (app.models.router's adapter registry), where the real
-- consequence of an unrecognized provider already lives (Milestone 4.3's
-- UnknownProviderError). Adding a third provider later is a plain data
-- INSERT, never a schema migration.
alter table model_registry add column provider text;

-- Backfill: both of dev's existing rows are Anthropic-family models
-- (claude-sonnet-5, claude-opus-5) -- confirmed via direct query before
-- writing this migration, not assumed.
update model_registry set provider = 'anthropic' where model_name in ('claude-sonnet-5', 'claude-opus-5');

alter table model_registry alter column provider set not null;
