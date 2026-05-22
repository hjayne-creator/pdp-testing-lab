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
            <strong>Research</strong> — Search and scrape the web, rank sources (manufacturer, datasheet,
            distributors), and verify the product match.
          </li>
          <li>
            <strong>Three LLM steps</strong> — Default: Research, Writing, Fact-check and edit. Each step uses
            your prompt, chosen model, style guide, source evidence, and prior step outputs.
          </li>
          <li>
            <strong>Results</strong> — Final content, intermediate outputs, sources, cost, runtime, and a
            downloadable internal report.
          </li>
        </ol>
        <p className="sidebar-about-label">Guardrails</p>
        <ul>
          <li>Runs stop if the product match cannot be verified.</li>
          <li>Models must follow the style guide and use only validated source evidence.</li>
          <li>Runs time out after ~180 seconds; thin or placeholder output is rejected.</li>
        </ul>
      </div>
    </details>
  );
}
