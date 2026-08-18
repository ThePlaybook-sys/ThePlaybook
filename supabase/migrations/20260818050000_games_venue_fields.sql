-- Phase 3E-6, Option A (Mac's explicit approval, 2026-08-18): preserve
-- venue coordinates and indoor/outdoor classification from SportsDataIO's
-- Schedule response instead of discarding them during normalization.
--
-- CONFIRMED FROM LIVE FREE TRIAL: StadiumDetails.GeoLat/GeoLong/Type are
-- genuinely present in this project's own already-captured fixtures
-- (tests/fixtures/sportsdataio/schedules_normal.json and
-- teams_active_normal.json) -- three distinct Type values observed across
-- both captures: "Outdoor", "Dome", "RetractableDome". No new provider
-- call was made to confirm this.
--
-- Smallest additive change (Option A, not the alternative dedicated
-- `stadiums` reference table considered and explicitly deferred) -- three
-- nullable columns directly on `games`, matching the exact precedent
-- `season_type`/`week` set in the 3E-1 migration rather than a new table.
-- Nullable because not every provider response carries venue metadata
-- (never fabricated when missing).
--
-- `venue_type` uses a normalized internal vocabulary, never SportsDataIO's
-- raw wording directly in business logic -- same discipline as
-- `season_type`'s `_SEASON_TYPE_MAP`/`games.status`'s check constraint.
-- The check constraint is the enforcement point, matching this project's
-- existing convention for `games.status`/`season_type`.
alter table games add column venue_lat double precision;
alter table games add column venue_long double precision;
alter table games add column venue_type text check (venue_type in ('outdoor', 'dome', 'retractable_dome'));

comment on column games.venue_lat is
  'Venue latitude, from SportsDataIO Schedule StadiumDetails.GeoLat -- Phase 3E-6. Nullable: not every provider response carries venue metadata.';
comment on column games.venue_long is
  'Venue longitude, from SportsDataIO Schedule StadiumDetails.GeoLong -- Phase 3E-6. Nullable, same reason as venue_lat.';
comment on column games.venue_type is
  'Normalized indoor/outdoor classification (outdoor|dome|retractable_dome), from SportsDataIO Schedule StadiumDetails.Type -- Phase 3E-6. Nullable: unknown is a real, distinct state, never defaulted to outdoor or dome.';
