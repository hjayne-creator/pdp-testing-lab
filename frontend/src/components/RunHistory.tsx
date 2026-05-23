import { useCallback, useEffect, useState } from "react";
import { api, RunSummary } from "../api/client";

type RunHistoryProps = {
  refreshKey: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
};

function formatWhen(iso: string): string {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function RunHistory({ refreshKey, selectedId, onSelect }: RunHistoryProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listRuns({ limit: 50 });
      setRuns(data.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run history.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  async function onDelete(e: React.MouseEvent, id: number) {
    e.stopPropagation();
    if (!window.confirm("Delete this run from history?")) return;
    try {
      await api.deleteRun(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  }

  return (
    <div className="run-history">
      <div className="run-history-header">
        <h3 className="run-history-title">Run history</h3>
        <button type="button" className="secondary run-history-refresh" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      </div>
      {error ? <p className="small bad-text">{error}</p> : null}
      {loading && runs.length === 0 ? (
        <p className="small muted">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="small muted">No runs yet.</p>
      ) : (
        <ul className="run-history-list">
          {runs.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                className={`run-history-item${selectedId === run.id ? " selected" : ""}`}
                onClick={() => onSelect(run.id)}
              >
                <span className={`status-pill ${run.status === "complete" ? "good" : "bad"}`}>
                  {run.status}
                </span>
                <span className="run-history-product">
                  {run.manufacturer_name} · {run.manufacturer_product_number}
                </span>
                <span className="run-history-meta small muted">
                  ${run.total_cost_usd.toFixed(3)} · {formatWhen(run.created_at)}
                </span>
              </button>
              <button
                type="button"
                className="run-history-delete secondary"
                title="Delete run"
                onClick={(e) => void onDelete(e, run.id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
