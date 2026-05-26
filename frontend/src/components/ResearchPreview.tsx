import { ResearchPreviewResponse } from "../api/client";

type ResearchPreviewProps = {
  preview: ResearchPreviewResponse;
  continuing: boolean;
  onContinue: () => void;
  onDismiss: () => void;
};

const TIER_LABELS: Record<string, string> = {
  exact_manufacturer: "Exact MPN on manufacturer site",
  family_series: "Family / series on manufacturer site",
  competitor_proxy: "Competitor proxy (no OEM data)",
  none: "No match",
};

export function ResearchPreview({ preview, continuing, onContinue, onDismiss }: ResearchPreviewProps) {
  const tierLabel = TIER_LABELS[preview.research_tier] ?? preview.research_tier;

  return (
    <div className="card research-preview">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3>Research preview</h3>
          <span className={`status-pill ${preview.match_verified ? "good" : "bad"}`}>
            {preview.match_verified ? "ready to continue" : "incomplete"}
          </span>
        </div>
        <button type="button" className="secondary" onClick={onDismiss}>Dismiss</button>
      </div>

      <p className="small muted">
        <strong>Research tier:</strong> {tierLabel}
        {preview.research_tier_reason ? ` — ${preview.research_tier_reason}` : null}
      </p>

      {preview.incomplete_reason ? (
        <p className="bad-text">{preview.incomplete_reason}</p>
      ) : null}

      {preview.sources.length > 0 ? (
        <>
          <h4>Sources</h4>
          <table className="data-table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>URL</th>
                <th>MPN</th>
                <th>Family</th>
                <th>Scraped</th>
              </tr>
            </thead>
            <tbody>
              {preview.sources.map((s, idx) => (
                <tr key={idx}>
                  <td>{s.tier}</td>
                  <td>
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.title || s.url}
                    </a>
                  </td>
                  <td>{s.exact_mpn_found ? "yes" : "no"}</td>
                  <td>{s.family_match_found ? "yes" : "no"}</td>
                  <td>{s.scrape_ok ? "yes" : s.error || "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {preview.evidence_text ? (
        <details className="step-output-details" open>
          <summary>Evidence bundle</summary>
          <pre className="output-text step-output-pre">{preview.evidence_text}</pre>
        </details>
      ) : null}

      <p className="small muted">
        Research cost: ${preview.total_cost_usd.toFixed(4)} · {preview.total_runtime_ms} ms
      </p>

      <div className="row right">
        <button type="button" onClick={onContinue} disabled={!preview.match_verified || continuing}>
          {continuing ? "Running LLM steps..." : "Continue to LLM steps"}
        </button>
      </div>
    </div>
  );
}
