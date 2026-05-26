import { FormEvent, useEffect, useState } from "react";
import { api, downloadReport, LabSettings, ModelOption, ResearchPreviewResponse, RunResult } from "../api/client";
import { ResearchPreview } from "../components/ResearchPreview";
import { RunHistory } from "../components/RunHistory";
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
  const [researching, setResearching] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [researchPreview, setResearchPreview] = useState<ResearchPreviewResponse | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);

  useEffect(() => {
    if (!settingsSaved) return;
    const timer = window.setTimeout(() => setSettingsSaved(false), 3000);
    return () => window.clearTimeout(timer);
  }, [settingsSaved]);

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
    setSettingsSaved(false);
    setSavingSettings(true);
    try {
      await persistSettings(settings);
      setSettingsSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setSavingSettings(false);
    }
  }

  async function resolveStyleGuideText(): Promise<{ text: string; filename: string }> {
    if (styleGuideFile) {
      const text = await styleGuideFile.text();
      return { text, filename: styleGuideFile.name };
    }
    return {
      text: settings.style_guide_text,
      filename: settings.style_guide_filename || "style-guide.txt",
    };
  }

  async function onResearch(e: FormEvent) {
    e.preventDefault();
    setResearching(true);
    setError(null);
    setResult(null);
    setResearchPreview(null);
    setSelectedHistoryId(null);
    try {
      await persistSettings(settings);
      const preview = await api.researchLab({
        manufacturer_name: settings.manufacturer_name,
        manufacturer_product_number: settings.manufacturer_product_number,
        product_family_hint: settings.product_family_hint,
      });
      setResearchPreview(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Research failed.");
    } finally {
      setResearching(false);
    }
  }

  async function onContinue() {
    if (!researchPreview) return;
    setContinuing(true);
    setError(null);
    setResult(null);
    try {
      const styleGuide = await resolveStyleGuideText();
      const runResult = await api.continueLab({
        research_session_id: researchPreview.research_session_id,
        style_guide_text: styleGuide.text,
        style_guide_filename: styleGuide.filename,
        step1: {
          name: settings.step1_name,
          prompt: settings.step1_prompt,
          model: settings.step1_model,
        },
        step2: {
          name: settings.step2_name,
          prompt: settings.step2_prompt,
          model: settings.step2_model,
        },
        step3: {
          name: settings.step3_name,
          prompt: settings.step3_prompt,
          model: settings.step3_model,
        },
      });
      setResult(runResult);
      setResearchPreview(null);
      setHistoryRefresh((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Continue failed.");
    } finally {
      setContinuing(false);
    }
  }

  async function onSelectHistoryRun(id: number) {
    setHistoryLoading(true);
    setError(null);
    setResearchPreview(null);
    try {
      const loaded = await api.getRun(id);
      setResult(loaded);
      setSelectedHistoryId(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run.");
    } finally {
      setHistoryLoading(false);
    }
  }

  const busy = researching || continuing || savingSettings;

  return (
    <div>
      <header className="page-header">
        <div>
          <h2>AI PDP Content Testing Lab</h2>
          <p className="muted">
            Enter a manufacturer + MPN, optionally a family/series hint, run research, review sources, then continue to LLM steps.
          </p>
        </div>
      </header>

      <form onSubmit={onResearch}>
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
          <div>
            <label htmlFor="family-hint">Family / series hint (optional)</label>
            <input
              id="family-hint"
              value={settings.product_family_hint}
              onChange={(e) => patchSettings({ product_family_hint: e.target.value })}
              placeholder='e.g. "Landing Gear Series LG-200"'
            />
            <p className="small muted">
              Used for tier (b) matching when the exact MPN is not on the manufacturer site.
            </p>
          </div>
          <label htmlFor="style-guide">Style guide upload (optional)</label>
          <input
            id="style-guide"
            type="file"
            onChange={(e) => setStyleGuideFile(e.target.files?.[0] ?? null)}
          />
          <p className="small muted">
            Any file type (PDF, Word, Markdown, plain text, HTML, etc.). Text-based formats work best.
          </p>
          {settings.style_guide_filename ? (
            <p className="small muted">Last style guide: {settings.style_guide_filename}</p>
          ) : null}
        </div>

        {researchPreview ? (
          <ResearchPreview
            preview={researchPreview}
            continuing={continuing}
            onContinue={() => void onContinue()}
            onDismiss={() => setResearchPreview(null)}
          />
        ) : null}

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
          {settingsSaved ? (
            <span className="status-pill good" role="status" aria-live="polite">
              Settings saved
            </span>
          ) : null}
          <button type="button" className="secondary" onClick={() => void onSaveSettings()} disabled={busy}>
            {savingSettings ? "Saving…" : "Save settings"}
          </button>
          <button type="submit" disabled={busy}>
            {researching ? "Researching..." : "Run research"}
          </button>
        </div>
      </form>

      <RunHistory
        refreshKey={historyRefresh}
        selectedId={selectedHistoryId}
        onSelect={(id) => void onSelectHistoryRun(id)}
      />

      {historyLoading ? <p className="muted small">Loading run from history…</p> : null}

      <RunResults
        result={result}
        fromHistory={selectedHistoryId != null}
        onDownloadReport={() => {
          if (result?.internal_report_html) downloadReport(result.internal_report_html);
        }}
      />
    </div>
  );
}
