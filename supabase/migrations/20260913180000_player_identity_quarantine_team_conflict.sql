-- Pre-Live Worker Hardening (2026-09-13, HQ-authorized): adds one new
-- conflict_type classification to player_identity_quarantine --
-- 'team_identity_conflict' -- required by the numeric-first team
-- resolution hardening in app.persistence.player_identity_activation.
--
-- Real justification, not speculative: the activation wrapper now
-- resolves team identity primarily through MySportsFeeds' own NUMERIC
-- team id (32/32-team coverage, vs. the abbreviation scheme's 12/32),
-- and treats a supplied abbreviation as supporting/consistency evidence
-- only. When both identifiers are present and mapped but resolve to
-- DIFFERENT canonical teams, that is a genuine data-integrity anomaly
-- between two of the provider's own identifier schemes -- a case the
-- prior 4-value enum (id_collision, team_unresolved, ambiguous_match,
-- malformed_identity) has no accurate name for. Widening the check
-- constraint's own IN-list, exactly the same additive-widening pattern
-- already used for team_provider_ids' own constraint (Sunday Ingestion
-- Foundation Build, 2026-09-11) -- no column added, no existing row
-- affected, no existing conflict_type value removed or renamed.
alter table player_identity_quarantine
  drop constraint player_identity_quarantine_conflict_type_check;

alter table player_identity_quarantine
  add constraint player_identity_quarantine_conflict_type_check
  check (conflict_type in (
    'id_collision',
    'team_unresolved',
    'ambiguous_match',
    'malformed_identity',
    'team_identity_conflict'
  ));
