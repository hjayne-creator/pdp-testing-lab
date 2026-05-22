import { FormEvent, useState } from "react";
import { api, downloadReport, LabSettings, ModelOption, RunResult } from "../api/client";
import { RunResults } from "../components/RunResults";
import { StepEditor } from "../components/StepEditor";

type LabPageProps = {
  initialSettings: LabSettings;
  models: ModelOption[];
  onSettingsChange: (settings: LabSettings) => void;
};

export function LabPage({ initialSettings, models, onSettingsChange }: LabPageProps) {
  const [settings, setSettings] = useState(initialSettings);
  const [styleGuideFile, setStyleGuideFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);

  function patchSettings(patch: Partial<LabSettings>) {
    const next = { ...settings, ...patch };
    setSettings(next);
  }

  async function persistSettings(next: LabSettings) {
    const saved = await api.saveSettings(next);
    onSettingsChange(saved);
    setSettings(saved);
  }

  async function onSaveSettings() {
    setError(null);
    try {
      await persistSettings(settings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    }
  }

  async function onRun(e: FormEvent) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      await persistSettings(settings);
      const formData = new FormData();
      formData.append("manufacturer_name", settings.manufacturer_name);
      formData.append("manufacturer_product_number", settings.manufacturer_product_number);
      formData.append("step1_name", settings.step1_name);
      formData.append("step1_prompt", settings.step1_prompt);
      formData.append("step1_model", settings.step1_model);
      formData.append("step2_name", settings.step2_name);
      formData.append("step2_prompt", settings.step2_prompt);
      formData.append("step2_model", settings.step2_model);
      formData.append("step3_name", settings.step3_name);
      formData.append("step3_prompt", settings.step3_prompt);
      formData.append("step3_model", settings.step3_model);

      if (styleGuideFile) {
        formData.append("style_guide", styleGuideFile);
      } else if (settings.style_guide_text.trim()) {
        const blob = new Blob([settings.style_guide_text], { type: "text/plain" });
        formData.append("style_guide", blob, settings.style_guide_filename || "style-guide.txt");
      }

      const runResult = await api.runLab(formData);
      setResult(runResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>AI PDP Content Testing Lab</h2>
          <p className="muted">Enter a manufacturer + MPN, optionally upload a style guide, configure three steps, and run.</p>
        </div>
      </header>

      <form onSubmit={onRun}>
        <div className="card">
          <h3>Product inputs</h3>
          <div className="grid-2">
            <div>
              <label htmlFor="manufacturer">Manufacturer name</label>
              <input
                id="manufacturer"
                value={settings.manufacturer_name}
                onChange={(e) => patchSettings({ manufacturer_name: e.target.value })}
                required
              />
            </div>
            <div>
              <label htmlFor="mpn">Manufacturer product number</label>
              <input
                id="mpn"
                value={settings.manufacturer_product_number}
                onChange={(e) => patchSettings({ manufacturer_product_number: e.target.value })}
                required
              />
            </div>
          </div>
          <label htmlFor="style-guide">Style guide upload (optional)</label>
          <input
            id="style-guide"
            type="file"
            accept=".txt,.md,.doc,.docx,.html,.htm"
            onChange={(e) => setStyleGuideFile(e.target.files?.[0] ?? null)}
          />
          {settings.style_guide_filename ? (
            <p className="small muted">Last style guide: {settings.style_guide_filename}</p>
          ) : null}
        </div>

        <StepEditor
          stepNo={1}
          name={settings.step1_name}
          prompt={settings.step1_prompt}
          model={settings.step1_model}
          models={models}
          onChange={(patch) => patchSettings({
            step1_name: patch.name ?? settings.step1_name,
            step1_prompt: patch.prompt ?? settings.step1_prompt,
            step1_model: patch.model ?? settings.step1_model,
          })}
        />
        <StepEditor
          stepNo={2}
          name={settings.step2_name}
          prompt={settings.step2_prompt}
          model={settings.step2_model}
          models={models}
          onChange={(patch) => patchSettings({
            step2_name: patch.name ?? settings.step2_name,
            step2_prompt: patch.prompt ?? settings.step2_prompt,
            step2_model: patch.model ?? settings.step2_model,
          })}
        />
        <StepEditor
          stepNo={3}
          name={settings.step3_name}
          prompt={settings.step3_prompt}
          model={settings.step3_model}
          models={models}
          onChange={(patch) => patchSettings({
            step3_name: patch.name ?? settings.step3_name,
            step3_prompt: patch.prompt ?? settings.step3_prompt,
            step3_model: patch.model ?? settings.step3_model,
          })}
        />

        {error ? <p className="bad-text">{error}</p> : null}

        <div className="row right sticky-actions">
          <button type="button" className="secondary" onClick={onSaveSettings} disabled={running}>
            Save settings
          </button>
          <button type="submit" disabled={running}>
            {running ? "Running..." : "Run"}
          </button>
        </div>
      </form>

      <RunResults
        result={result}
        onDownloadReport={() => {
          if (result?.internal_report_html) downloadReport(result.internal_report_html);
        }}
      />
    </div>
  );
}
