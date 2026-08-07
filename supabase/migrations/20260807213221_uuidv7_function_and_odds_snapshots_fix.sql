-- CHANGELOG v4.1.1 (PATCH): Milestone 2 built odds_snapshots with gen_random_uuid() (UUIDv4),
-- missing the v2.0 amendment's requirement that odds_snapshots, recommendation_agent_outputs,
-- and market_monitoring_events use UUIDv7 for index locality on the schema's highest-insert
-- tables. Dev runs PostgreSQL 17.6, which has no native uuidv7() (that lands in PG18), so a
-- custom implementation is used instead. This function is also used by Milestone 3's
-- recommendation_agent_outputs and will be reused for market_monitoring_events in Milestone 4.

create or replace function uuid_generate_v7()
returns uuid
as $$
declare
  unix_ts_ms bytea;
  uuid_bytes bytea;
begin
  unix_ts_ms = substring(int8send(floor(extract(epoch from clock_timestamp()) * 1000)::bigint) from 3);
  uuid_bytes = uuid_send(gen_random_uuid());
  uuid_bytes = overlay(uuid_bytes placing unix_ts_ms from 1 for 6);
  uuid_bytes = set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15) | 112); -- version nibble -> 0111 (7)
  uuid_bytes = set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63) | 128); -- variant bits -> 10
  return encode(uuid_bytes, 'hex')::uuid;
end
$$ language plpgsql volatile;

alter table odds_snapshots alter column id set default uuid_generate_v7();
