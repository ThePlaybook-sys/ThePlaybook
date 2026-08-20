"use client";

import Link from "next/link";
import { demoApi } from "../lib/api";
import { usePolling } from "../lib/usePolling";
import { AuthExpired } from "../AuthExpired";

export default function DemoGamesPage() {
  const { data: games, error } = usePolling(() => demoApi.listGames(), () => "idle");

  if (error && error.includes("401")) return <AuthExpired />;

  return (
    <div>
      <h1 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>Games</h1>
      {!games ? (
        <p>Loading…</p>
      ) : games.length === 0 ? (
        <p>No games yet — load and step a scenario first.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#fff" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e5e5" }}>
              <th style={thStyle}>Matchup</th>
              <th style={thStyle}>Kickoff</th>
              <th style={thStyle}>Status</th>
              <th style={thStyle}>Score</th>
            </tr>
          </thead>
          <tbody>
            {games.map((game) => (
              <tr key={game.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                <td style={tdStyle}>
                  <Link href={`/demo/games/${game.id}`}>
                    {game.away_team} @ {game.home_team}
                  </Link>
                </td>
                <td style={tdStyle}>{new Date(game.scheduled_start).toLocaleString()}</td>
                <td style={tdStyle}>{game.status}</td>
                <td style={tdStyle}>
                  {game.final_score ? `${game.final_score.away} – ${game.final_score.home}` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = { padding: "0.5rem", fontSize: "0.85rem", color: "#525252" };
const tdStyle: React.CSSProperties = { padding: "0.5rem", fontSize: "0.9rem" };
