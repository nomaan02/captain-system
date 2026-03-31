const BASE = "/api";

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

const api = {
  health: () => fetchJson(`${BASE}/health`),
  status: () => fetchJson(`${BASE}/status`),
  dashboard: (userId) => fetchJson(`${BASE}/dashboard/${userId}`),
  systemOverview: () => fetchJson(`${BASE}/system-overview`),
  processesStatus: () => fetchJson(`${BASE}/processes/status`),
  reportTypes: () => fetchJson(`${BASE}/reports/types`),
  generateReport: (payload) =>
    fetchJson(`${BASE}/reports/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  validateInput: (payload) =>
    fetchJson(`${BASE}/validate/input`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  validateAssetConfig: (payload) =>
    fetchJson(`${BASE}/validate/asset-config`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  setAccount: (accountName) =>
    fetchJson(`${BASE}/set-account`, {
      method: "POST",
      body: JSON.stringify({ account_name: accountName }),
    }),
  bars: (asset, timeframe = "5m", limit = 500) =>
    fetchJson(`${BASE}/bars/${asset}?timeframe=${timeframe}&limit=${limit}`),
  orders: (userId) => fetchJson(`${BASE}/orders/${userId}`),
  performance: (userId) => fetchJson(`${BASE}/performance/${userId}`),
};

export default api;
