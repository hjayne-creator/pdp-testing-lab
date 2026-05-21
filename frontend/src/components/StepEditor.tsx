import { ModelOption } from "../api/client";

type StepEditorProps = {
  stepNo: 1 | 2 | 3;
  name: string;
  prompt: string;
  model: string;
  models: ModelOption[];
  onChange: (patch: Partial<{ name: string; prompt: string; model: string }>) => void;
};

export function StepEditor({ stepNo, name, prompt, model, models, onChange }: StepEditorProps) {
  return (
    <div className="card">
      <h3>Step {stepNo}</h3>
      <label htmlFor={`step${stepNo}-name`}>Step name</label>
      <input
        id={`step${stepNo}-name`}
        value={name}
        onChange={(e) => onChange({ name: e.target.value })}
      />
      <label htmlFor={`step${stepNo}-model`}>Model</label>
      <select
        id={`step${stepNo}-model`}
        value={model}
        onChange={(e) => onChange({ model: e.target.value })}
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
      </select>
      <label htmlFor={`step${stepNo}-prompt`}>Prompt</label>
      <textarea
        id={`step${stepNo}-prompt`}
        rows={8}
        value={prompt}
        onChange={(e) => onChange({ prompt: e.target.value })}
      />
    </div>
  );
}
