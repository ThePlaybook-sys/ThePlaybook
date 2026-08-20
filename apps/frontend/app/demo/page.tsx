"use client";

import { useEffect, useState } from "react";
import { demoApi, DemoApiError } from "./lib/api";
import { usePolling, PollingActivity } from "./lib/usePolling";
import type { ScenarioSummary, StepOutcome } from "./lib/types";
import { AuthExpired } from "./AuthExpired";

function activityForStatus(status: string | undefined): PollingActivity {
  if (status === "running") return "active";
  if (status === "loaded" || status === "idle") return "idle";
  // "completed" / "failed" -- nothing left to change on its own; slow poll
  // in case the operator resets from another tab.
  return "idle";
}

function outcomeSummary(outcome: StepOutcome): string {
  if (outcome.error) return `failed: ${outcome.error}`;
  if (outcome.action === "advance_time") return "virtual clock advanced";
  if (outcome.action === "checkpoint") return outcome.checkpoint_note ?? "checkpoint";
  const result = outcome.result as Record<string, unknown> | null;
  const status = (result?.status as string) ?? "success";
  return `${outcome.action} → ${status}`;
}

export default function DemoDashboardPage() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [showRaw, setShowRaw] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    demoApi
      .listScenarios()
      .then((list) => {
        setScenarios(list);
        if (list[0]) setSelected(list[0].name);
      })
      .catch(() => void 0);
  }, []);

  const { data: current, error: currentError, refresh } = usePolling(
    () => demoApi.getStatus(),
    (last) => activityForStatus(last?.status)
  );

  if (currentError && currentError.includes("401")) {
    return <AuthExpired />;
  }

  const runAction = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      if (err instanceof DemoApiError && err.status === 401) {
        setActionError("session expired");
      } else {
        setActionError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>Operator Dashboard</h1>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Scenario Control</h2>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
          <select value={selected} onChange={(e) => setSelected(e.target.value)} style={selectStyle}>
            {scenarios.map((s) => (
              <option key={s.name} value={s.name}>
                {s.title} ({s.step_count} steps)
              </option>
            ))}
          </select>
          <button disabled={busy || !selected} onClick={() => runAction(() => demoApi.loadScenario(selected))} style={btnStyle}>
            Load
          </button>
          <button disabled={busy || !current || current.is_finished} onClick={() => runAction(() => demoApi.step())} style={btnStyle}>
            Step
          </button>
          <button
            disabled={busy || !current || current.is_finished}
            onClick={() => runAction(() => demoApi.runToCheckpoint())}
            style={btnStyle}
          >
            Run to Checkpoint
          </button>
          <button
            disabled={busy || !current || current.is_finished}
            onClick={() => runAction(() => demoApi.runToCompletion())}
            style={btnStyle}
          >
            Run to Completion
          </button>
          <button disabled={busy} onClick={() => runAction(() => demoApi.reset())} style={{ ...btnStyle, background: "#7c2d12" }}>
            Reset
          </button>
        </div>
        {actionError && <p style={{ color: "#b91c1c", marginTop: "0.5rem" }}>{actionError}</p>}
      </section>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>Scenario State</h2>
        {current ? (
          <dl style={dlStyle}>
            <dt>Scenario</dt>
            <dd>{current.title ?? "(none loaded)"}</dd>
            <dt>Status</dt>
            <dd>
              <StatusBadge status={current.status} />
            </dd>
            <dt>Virtual time</dt>
            <dd>{current.virtual_now ?? "—"}</dd>
            <dt>Step</dt>
            <dd>
              {current.step_index} / {current.total_steps}
            </dd>
            <dt>Checkpoints</dt>
            <dd>{current.checkpoints.length ? current.checkpoints.join(" · ") : "—"}</dd>
          </dl>
        ) : (
          <p>Loading…</p>
        )}
      </section>

      <section style={cardStyle}>
        <h2 style={sectionTitleStyle}>System Activity</h2>
        {current && current.outcomes.length > 0 ? (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {[...current.outcomes].reverse().map((outcome) => (
              <li
                key={outcome.step_index}
                style={{
                  padding: "0.5rem 0",
                  borderBottom: "1px solid #eee",
                  color: outcome.error ? "#b91c1c" : "#171717",
                }}
              >
                <strong>Step {outcome.step_index}</strong> — {outcomeSummary(outcome)}
                <span style={{ color: "#737373", fontSize: "0.8rem", marginLeft: "0.5rem" }}>
                  ({outcome.virtual_now})
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No activity yet.</p>
        )}
      </section>

      {current && current.errors.length > 0 && (
        <section style={{ ...cardStyle, borderColor: "#fecaca", background: "#fef2f2" }}>
          <h2 style={sectionTitleStyle}>Errors</h2>
          <ul>
            {current.errors.map((e, i) => (
              <li key={i} style={{ color: "#b91c1c" }}>
                {e}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section style={cardStyle}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
          <input type="checkbox" checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />
          Raw / debug view
        </label>
        {showRaw && (
          <pre style={preStyle}>{JSON.stringify(current, null, 2)}</pre>
        )}
      </section>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle: "#a3a3a3",
    loaded: "#2563eb",
    running: "#16a34a",
    completed: "#16a34a",
    failed: "#b91c1c",
  };
  return (
    <span
      style={{
        background: colors[status] ?? "#a3a3a3",
        color: "#fff",
        padding: "0.15rem 0.5rem",
        borderRadius: 4,
        fontSize: "0.8rem",
        textTransform: "uppercase",
      }}
    >
      {status}
    </span>
  );
}

const cardStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e5e5",
  borderRadius: 6,
  padding: "1rem",
  marginBottom: "1rem",
};
const sectionTitleStyle: React.CSSProperties = { fontSize: "1rem", marginTop: 0, marginBottom: "0.75rem" };
const btnStyle: React.CSSProperties = {
  padding: "0.4rem 0.8rem",
  background: "#1f2937",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: "0.85rem",
};
const selectStyle: React.CSSProperties = { padding: "0.4rem", borderRadius: 4, border: "1px solid #d4d4d4" };
const dlStyle: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.35rem 1rem", margin: 0 };
const preStyle: React.CSSProperties = {
  background: "#0a0a0a",
  color: "#d4d4d4",
  padding: "0.75rem",
  borderRadius: 4,
  overflowX: "auto",
  fontSize: "0.8rem",
  marginTop: "0.75rem",
};
