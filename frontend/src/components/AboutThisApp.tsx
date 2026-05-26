export function AboutThisApp() {
  return (
    <details className="sidebar-about">
      <summary>About this app</summary>
      <div className="sidebar-about-body">
        <p>
          Internal lab for testing AI-generated product detail page (PDP) copy. Configure prompts and models,
          run the pipeline, and review outputs, sources, cost, and timing.
        </p>
        <p className="sidebar-about-label">How a run works</p>
        <ol>
          <li>
            <strong>Research</strong> — Search and scrape the web using a three-tier hierarchy: exact MPN on
            the manufacturer site, then family/series (with your optional hint), then 1–3 competitor pages.
          </li>
          <li>
            <strong>Review</strong> — Research results (sources, tier, evidence) are shown before any LLM steps run.
          </li>
          <li>
            <strong>Three LLM steps</strong> — Default: Research, Writing, Fact-check and edit. Each step uses
            your prompt, chosen model, style guide, source evidence, and prior step outputs.
          </li>
          <li>
            <strong>Results</strong> — Final content, intermediate outputs, sources, cost, runtime, and a
            downloadable internal report.
          </li>
          <li>
            <strong>Run history</strong> — Past runs are saved locally so you can reopen results without
            re-running the pipeline.
          </li>
        </ol>
        <p className="sidebar-about-label">Guardrails</p>
        <ul>
          <li>LLM steps only proceed after you review research and click Continue (when match is verified).</li>
          <li>Models must follow the style guide and use only validated source evidence.</li>
          <li>Runs time out after ~180 seconds; thin or placeholder output is rejected.</li>
        </ul>
      </div>
    </details>
  );
}
