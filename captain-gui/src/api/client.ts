import type {
  DashboardSnapshot,
  SystemOverview,
  HealthResponse,
  ReportType,
  ReportResult,
} from "./types";

const BASE = "/api";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  health: () => fetchJson<HealthResponse>("/health"),

  status: () => fetchJson<Record<string, unknown>>("/status"),

  dashboard: (userId: string) =>
    fetchJson<DashboardSnapshot>(`/dashboard/${userId}`),

  systemOverview: () =>
    fetchJson<SystemOverview>("/system-overview"),

  reportTypes: () => fetchJson<ReportType[]>("/reports/types"),

  generateReport: (reportType: string, userId: string, params: Record<string, unknown> = {}) =>
    fetchJson<ReportResult>("/reports/generate", {
      method: "POST",
      body: JSON.stringify({ report_type: reportType, user_id: userId, params }),
    }),

  validateInput: (inputType: string, value: number, context: Record<string, unknown> = {}) =>
    fetchJson<{ valid: boolean; message?: string }>("/validate/input", {
      method: "POST",
      body: JSON.stringify({ input_type: inputType, value, context }),
    }),

  validateAssetConfig: (assetConfig: Record<string, unknown>) =>
    fetchJson<{ valid: boolean; errors?: string[] }>("/validate/asset-config", {
      method: "POST",
      body: JSON.stringify({ asset_config: assetConfig }),
    }),
};
