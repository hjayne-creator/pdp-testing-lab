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
  product_family_hint: string;
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

export type SourceRecord = {
  url: string;
  title: string;
  tier: string;
  domain: string;
  exact_mpn_found: boolean;
  family_match_found?: boolean;
  competitor_match_found?: boolean;
  scrape_ok: boolean;
  error?: string | null;
};

export type ResearchPreviewResponse = {
  research_session_id: string;
  status: "ready" | "incomplete";
  research_tier: string;
  research_tier_reason: string;
  match_verified: boolean;
  incomplete_reason?: string | null;
  manufacturer_name: string;
  manufacturer_product_number: string;
  product_family_hint: string;
  sources: SourceRecord[];
  evidence_text: string;
  cost_lines: CostLine[];
  total_cost_usd: number;
  runtime_lines: RuntimeLine[];
  total_runtime_ms: number;
  audit: Record<string, unknown>;
};

export type RunResult = {
  status: "complete" | "incomplete";
  incomplete_reason?: string | null;
  final_content?: string | null;
  style_guide_truncated: boolean;
  match_verified: boolean;
  sources?: SourceRecord[];
  cost_lines: CostLine[];
  total_cost_usd: number;
  runtime_lines: RuntimeLine[];
  total_runtime_ms: number;
  step1_output?: string | null;
  step2_output?: string | null;
  internal_report_html?: string | null;
  audit?: Record<string, unknown>;
};

export type RunSummary = {
  id: number;
  created_at: string;
  manufacturer_name: string;
  manufacturer_product_number: string;
  status: "complete" | "incomplete";
  match_verified: boolean;
  incomplete_reason?: string | null;
  total_cost_usd: number;
  total_runtime_ms: number;
  style_guide_filename: string;
};

export type StepConfigPayload = {
  name: string;
  prompt: string;
  model: string;
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
  researchLab: (body: {
    manufacturer_name: string;
    manufacturer_product_number: string;
    product_family_hint?: string;
  }) =>
    request<ResearchPreviewResponse>("/lab/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  continueLab: (body: {
    research_session_id: string;
    style_guide_text: string;
    style_guide_filename?: string;
    step1: StepConfigPayload;
    step2: StepConfigPayload;
    step3: StepConfigPayload;
  }) =>
    request<RunResult>("/lab/run/continue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  runLab: (formData: FormData) =>
    request<RunResult>("/lab/run-with-upload", { method: "POST", body: formData }),
  listRuns: (params?: { limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.limit != null) q.set("limit", String(params.limit));
    if (params?.offset != null) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<{ runs: RunSummary[]; total: number }>(`/lab/runs${qs ? `?${qs}` : ""}`);
  },
  getRun: (id: number) => request<RunResult>(`/lab/runs/${id}`),
  deleteRun: (id: number) => request<void>(`/lab/runs/${id}`, { method: "DELETE" }),
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
