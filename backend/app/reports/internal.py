from __future__ import annotations

import html


def render_internal_report(
    *,
    manufacturer: str,
    mpn: str,
    style_guide_filename: str,
    style_guide_truncated: bool,
    steps: list[dict],
    sources: list[dict],
    match_verified: bool,
    incomplete_reason: str | None,
    cost_lines: list[dict],
    total_cost_usd: float,
    runtime_lines: list[dict],
    total_runtime_ms: int,
    step1_output: str | None,
    step2_output: str | None,
    final_content: str | None,
    audit: dict,
) -> str:
    def esc(value: str | None) -> str:
        return html.escape(value or "")

    source_rows = "".join(
        f"<tr><td>{esc(s.get('tier'))}</td><td><a href='{esc(s.get('url'))}'>{esc(s.get('url'))}</a></td>"
        f"<td>{'yes' if s.get('exact_mpn_found') else 'no'}</td>"
        f"<td>{'yes' if s.get('scrape_ok') else 'no'}</td>"
        f"<td>{esc(s.get('error'))}</td></tr>"
        for s in sources
    )
    cost_rows = "".join(
        f"<tr><td>{esc(str(c.get('phase')))}</td><td>{esc(str(c.get('service')))}</td>"
        f"<td>{esc(str(c.get('model')))}</td><td>{c.get('input_tokens') or ''}</td>"
        f"<td>{c.get('output_tokens') or ''}</td><td>${c.get('total_cost_usd', 0):.6f}</td></tr>"
        for c in cost_lines
    )
    runtime_rows = "".join(
        f"<tr><td>{esc(r.get('phase'))}</td><td>{r.get('duration_ms')} ms</td></tr>" for r in runtime_lines
    )
    step_blocks = "".join(
        f"<section><h3>{esc(step.get('name'))} ({esc(step.get('model'))})</h3>"
        f"<pre>{esc(step.get('prompt'))}</pre></section>"
        for step in steps
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>PDP Testing Lab Internal Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #111; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    pre {{ white-space: pre-wrap; background: #fafafa; padding: 12px; border: 1px solid #eee; }}
    .bad {{ color: #b00020; }}
    .ok {{ color: #0a7a2f; }}
  </style>
</head>
<body>
  <h1>PDP Testing Lab Internal Report</h1>
  <p><strong>Manufacturer:</strong> {esc(manufacturer)}<br/>
     <strong>MPN:</strong> {esc(mpn)}<br/>
     <strong>Style guide:</strong> {esc(style_guide_filename)}<br/>
     <strong>Style guide truncated:</strong> {'yes' if style_guide_truncated else 'no'}</p>

  <h2>Match status</h2>
  <p class="{'ok' if match_verified else 'bad'}">
    {'Verified' if match_verified else esc(incomplete_reason or 'Not verified')}
  </p>
  <p><strong>Research tier:</strong> {esc(str(audit.get('research_tier', '')))}<br/>
     <strong>Tier reason:</strong> {esc(str(audit.get('research_tier_reason', '')))}</p>

  <h2>Configured steps</h2>
  {step_blocks}

  <h2>Sources</h2>
  <table>
    <tr><th>Tier</th><th>URL</th><th>Exact MPN</th><th>Scrape OK</th><th>Error</th></tr>
    {source_rows}
  </table>

  <h2>Cost</h2>
  <table>
    <tr><th>Phase</th><th>Service</th><th>Model</th><th>Input tokens</th><th>Output tokens</th><th>Total $</th></tr>
    {cost_rows}
  </table>
  <p><strong>Total cost:</strong> ${total_cost_usd:.6f}</p>

  <h2>Runtime</h2>
  <table>
    <tr><th>Phase</th><th>Duration</th></tr>
    {runtime_rows}
  </table>
  <p><strong>Total runtime:</strong> {total_runtime_ms} ms</p>

  <h2>Intermediate outputs</h2>
  <h3>Step 1</h3><pre>{esc(step1_output)}</pre>
  <h3>Step 2</h3><pre>{esc(step2_output)}</pre>
  <h3>Final</h3><pre>{esc(final_content)}</pre>

  <h2>Audit</h2>
  <pre>{esc(str(audit))}</pre>
</body>
</html>"""
