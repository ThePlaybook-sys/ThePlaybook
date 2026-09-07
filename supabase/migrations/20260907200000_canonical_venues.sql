-- Phase 8.0.5 Data Activation Pass 2 (2026-09-07): canonical, sport-
-- agnostic venue reference table. Deliberately carries no sport_id/
-- league_id -- a physical venue is not owned by one sport, and this
-- table must be directly reusable by a future NBA (or any other sport)
-- games row without redesign. Supersedes Option A's original "smallest
-- additive change... given the league's small ~30 venue count" rationale
-- (Volume 3 v4.9), which was explicitly NFL-scoped -- games.venue_lat/
-- .venue_long/.venue_type are NOT removed (same "legacy field stays
-- populated for compatibility" precedent as games.sport alongside
-- sport_id); games.venue_id is the new canonical path.
create table venues (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  city text,
  state text,
  lat double precision,
  long double precision,
  -- NULL is a real, distinct "genuinely unclassifiable under this
  -- vocabulary" state (e.g. SoFi Stadium's fixed-canopy/open-side design),
  -- never coerced into outdoor/dome/retractable_dome -- same discipline
  -- games.venue_type already established.
  venue_type text check (venue_type in ('outdoor','dome','retractable_dome')),
  created_at timestamptz not null default now()
);
create unique index idx_venues_name on venues(name);

alter table games add column venue_id uuid references venues(id);

alter table venues enable row level security;
