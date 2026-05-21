const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
  });
  if (res.status === 401) {
    window.dispatchEvent(new Event("auth:unauthorized"));
    throw new Error("Authentication required.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type ModelOption = { id: string; label: string; provider: string; description: string };

export type LabSettings = {
  manufacturer_name: string;
  manufacturer_product_number: string;
  style_guide_filename: string;
  style_guide_text: string;
  step1_name: string;
  step1_prompt: string;
  step1_model: string;
  step2_name: string;
  step2_prompt: string;
  step2_model: string;
  step3_name: string;
  step3_prompt: string;
  step3_model: string;
};

export type CostLine = {
  phase: string;
  service?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  input_cost_usd?: number;
  output_cost_usd?: number;
  total_cost_usd?: number;
  units?: number | null;
};

export type RuntimeLine = { phase: string; duration_ms: number };

export type RunResult = {
  status: "complete" | "incomplete";
  incomplete_reason?: string | null;
  final_content?: string | null;
  style_guide_truncated: boolean;
  match_verified: boolean;
  cost_lines: CostLine[];
  total_cost_usd: number;
  runtime_lines: RuntimeLine[];
  total_runtime_ms: number;
  internal_report_html?: string | null;
};

export const api = {
  getSession: () => request<{ enabled: boolean; authenticated: boolean; username: string | null }>("/auth/session"),
  login: (body: { username: string; password: string }) =>
    request<{ ok: boolean; username: string | null }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  getSettings: () => request<LabSettings>("/settings"),
  saveSettings: (body: Partial<LabSettings>) =>
    request<LabSettings>("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  listModels: () => request<ModelOption[]>("/models"),
  runLab: (formData: FormData) =>
    request<RunResult>("/lab/run-with-upload", { method: "POST", body: formData }),
};

export function downloadReport(html: string) {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "pdp-lab-report.html";
  a.click();
  URL.revokeObjectURL(url);
}
