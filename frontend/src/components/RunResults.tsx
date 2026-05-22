import { RunResult } from "../api/client";
import { FinalContent } from "./FinalContent";

type RunResultsProps = {
  result: RunResult | null;
  onDownloadReport: () => void;
};

export function RunResults({ result, onDownloadReport }: RunResultsProps) {
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
