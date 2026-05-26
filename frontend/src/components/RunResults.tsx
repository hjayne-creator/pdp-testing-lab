import { RunResult } from "../api/client";
import { FinalContent } from "./FinalContent";

type RunResultsProps = {
  result: RunResult | null;
  fromHistory?: boolean;
  onDownloadReport: () => void;
};

export function RunResults({ result, fromHistory, onDownloadReport }: RunResultsProps) {
  if (!result) return null;

  const overBudget = result.total_cost_usd > 0.1;

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3>Run result</h3>
          <span className={`status-pill ${result.status === "complete" ? "good" : "bad"}`}>
            {result.status}
          </span>
          {fromHistory ? <span className="small muted" style={{ marginLeft: 8 }}>from history</span> : null}
          {result.match_verified === false ? (
            <span className="small warn-text" style={{ marginLeft: 8 }}>match not verified</span>
          ) : null}
          {result.audit?.research_tier ? (
            <span className="small muted" style={{ marginLeft: 8 }}>tier: {String(result.audit.research_tier)}</span>
          ) : null}
        </div>
        <button className="secondary" onClick={onDownloadReport}>Download internal report</button>
      </div>

      {result.incomplete_reason ? (
        <p className="bad-text">{result.incomplete_reason}</p>
      ) : null}

      {result.style_guide_truncated ? (
        <p className="warn-text small">Style guide was truncated for model context.</p>
      ) : null}

      {result.final_content ? (
        <div>
          <h4>Final WYSIWYG content</h4>
          <FinalContent content={result.final_content} />
        </div>
      ) : null}

      {result.sources && result.sources.length > 0 ? (
        <>
          <h4>Sources</h4>
          <table className="data-table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>URL</th>
                <th>MPN match</th>
                <th>Scraped</th>
              </tr>
            </thead>
            <tbody>
              {result.sources.map((s, idx) => (
                <tr key={idx}>
                  <td>{s.tier}</td>
                  <td>
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.title || s.url}
                    </a>
                  </td>
                  <td>{s.exact_mpn_found ? "yes" : "no"}</td>
                  <td>{s.scrape_ok ? "yes" : s.error || "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {result.step1_output ? (
        <details className="step-output-details">
          <summary>Step 1 output</summary>
          <pre className="output-text step-output-pre">{result.step1_output}</pre>
        </details>
      ) : null}
      {result.step2_output ? (
        <details className="step-output-details">
          <summary>Step 2 output</summary>
          <pre className="output-text step-output-pre">{result.step2_output}</pre>
        </details>
      ) : null}

      <h4>Cost report</h4>
      <table className="data-table">
        <thead>
          <tr>
            <th>Phase</th>
            <th>Service</th>
            <th>Model</th>
            <th>Input tokens</th>
            <th>Output tokens</th>
            <th>Total $</th>
          </tr>
        </thead>
        <tbody>
          {result.cost_lines.map((line, idx) => (
            <tr key={idx}>
              <td>{line.phase}</td>
              <td>{line.service ?? ""}</td>
              <td>{line.model ?? ""}</td>
              <td>{line.input_tokens ?? ""}</td>
              <td>{line.output_tokens ?? ""}</td>
              <td>${(line.total_cost_usd ?? 0).toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={overBudget ? "warn-text" : ""}>
        <strong>Total cost:</strong> ${result.total_cost_usd.toFixed(4)}
        {overBudget ? " (exceeds $0.10 target)" : ""}
      </p>

      <h4>Runtime report</h4>
      <table className="data-table">
        <thead>
          <tr><th>Phase</th><th>Duration</th></tr>
        </thead>
        <tbody>
          {result.runtime_lines.map((line, idx) => (
            <tr key={idx}>
              <td>{line.phase}</td>
              <td>{line.duration_ms} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p><strong>Total runtime:</strong> {result.total_runtime_ms} ms</p>
    </div>
  );
}
