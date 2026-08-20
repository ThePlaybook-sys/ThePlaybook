"use client";

import { useState } from "react";
import { demoApi } from "../../lib/api";
import { usePolling } from "../../lib/usePolling";
import { AuthExpired } from "../../AuthExpired";

/**
 * One category's envelope, matching `app.persistence.daily_game_intelligence`'s
 * `{value, source, last_updated, status}` shape -- rendered generically
 * (neutral card, not a final designed component) since this dashboard's
 * job is to show what the real pipeline produced, not to anticipate the
 * UX/UI Designer Brief's eventual card design.
 */
interface Envelope {
  value: unknown;
  source?: string;
  last_updated?: string;
  status?: string;
}

function isEnvelope(value: unknown): value is Envelope {
  return typeof value === "object" && value !== null && "value" in value;
}

function Category({ name, data }: { name: string; data: unknown }) {
  if (data === null || data === undefined) {
    return (
      <div style={cardStyle}>
        <h3 style={cardTitleStyle}>{name}</h3>
        <p style={{ color: "#a3a3a3" }}>not yet available</p>
      </div>
    );
  }
  const envelope = isEnvelope(data) ? data : null;
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={cardTitleStyle}>{name}</h3>
        {envelope?.status && <FreshnessBadge status={envelope.status} />}
      </div>
      {envelope?.source && (
        <p style={{ fontSize: "0.75rem", color: "#737373", margin: "0 0 0.5rem" }}>
          source: {envelope.source}
          {envelope.last_updated ? ` · ${envelope.last_updated}` : ""}
        </p>
      )}
      <pre style={preStyle}>{JSON.stringify(envelope ? envelope.value : data, null, 2)}</pre>
    </div>
  );
}

function FreshnessBadge({ status }: { status: string }) {
  const colors: Record<string, string> = { fresh: "#16a34a", needs_refresh: "#d97706", stale: "#b91c1c" };
  return (
    <span
      style={{
        fontSize: "0.7rem",
        textTransform: "uppercase",
        color: "#fff",
        background: colors[status] ?? "#a3a3a3",
        padding: "0.1rem 0.4rem",
        borderRadius: 3,
      }}
    >
      {status}
    </span>
  );
}

export default function GameDetailPage({ params }: { params: { id: string } }) {
  const [showRaw, setShowRaw] = useState(false);
  const { data: dgi, error } = usePolling(
    () => demoApi.getGameIntelligence(params.id),
    () => "idle"
  );

  if (error && error.includes("401")) return <AuthExpired />;
  if (error && error.includes("404")) {
    return <p>No daily_game_intelligence yet for this game — step the scenario further.</p>;
  }

  return (
    <div>
      <h1 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>Game Intelligence</h1>
      {!dgi ? (
        <p>Loading…</p>
      ) : (
        <>
          <div style={gridStyle}>
            <Category name="Teams" data={dgi.teams} />
            <Category name="Odds" data={dgi.odds} />
            <Category name="Player Props" data={dgi.props} />
            <Category name="Injuries" data={dgi.injuries} />
            <Category name="Weather" data={dgi.weather} />
            <Category name="News" data={dgi.news} />
            <Category name="Players / Rosters" data={dgi.players} />
            <Category name="Rest" data={dgi.rest} />
            <Category name="Stadium" data={dgi.stadium} />
          </div>

          <div style={{ ...cardStyle, marginTop: "1rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
              <input type="checkbox" checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />
              Raw / debug view (full row)
            </label>
            {showRaw && <pre style={preStyle}>{JSON.stringify(dgi, null, 2)}</pre>}
          </div>
        </>
      )}
    </div>
  );
}

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
  gap: "1rem",
};
const cardStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e5e5",
  borderRadius: 6,
  padding: "1rem",
};
const cardTitleStyle: React.CSSProperties = { fontSize: "0.95rem", margin: "0 0 0.25rem" };
const preStyle: React.CSSProperties = {
  background: "#0a0a0a",
  color: "#d4d4d4",
  padding: "0.6rem",
  borderRadius: 4,
  overflowX: "auto",
  fontSize: "0.75rem",
  maxHeight: 200,
};
