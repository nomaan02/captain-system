const BASE = "/api";

async function fetchJson(url, options = {}) {
  const token = localStorage.getItem("captain_jwt");
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("captain_jwt");
    window.dispatchEvent(new Event("auth:expired"));
    throw new Error("Session expired");
  }
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

function post(url, body) {
  return fetchJson(url, { method: "POST", body: JSON.stringify(body) });
}

function get(url) {
  return fetchJson(url);
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
  accounts: () => fetchJson(`${BASE}/accounts`),
  setAccount: (accountName) =>
    fetchJson(`${BASE}/set-account`, {
      method: "POST",
      body: JSON.stringify({ account_name: accountName }),
    }),
  bars: (asset, timeframe = "5m", limit = 500) =>
    fetchJson(`${BASE}/bars/${asset}?timeframe=${timeframe}&limit=${limit}`),
  orders: (userId) => fetchJson(`${BASE}/orders/${userId}`),
  performance: (userId) => fetchJson(`${BASE}/performance/${userId}`),

  // Replay API
  replayStart: (date, sessions, configOverrides, speed) =>
    post(`${BASE}/replay/start`, { date, sessions, config_overrides: configOverrides, speed }),
  replayBatchStart: (dateFrom, dateTo, sessions, configOverrides, speed) =>
    post(`${BASE}/replay/batch/start`, {
      date_from: dateFrom, date_to: dateTo, sessions,
      config_overrides: configOverrides, speed,
    }),
  replayControl: (action, value) =>
    post(`${BASE}/replay/control`, { action, value }),
  replaySave: (replayId, userId = "primary_user") =>
    post(`${BASE}/replay/save`, { replay_id: replayId, user_id: userId }),
  replayStatus: () => get(`${BASE}/replay/status`),
  replayHistory: () => get(`${BASE}/replay/history`),
  replayPresets: () => get(`${BASE}/replay/presets`),
  replayPresetSave: (name, config, userId = "primary_user") =>
    post(`${BASE}/replay/presets`, { name, config, user_id: userId }),
  replayWhatIf: (configOverrides) =>
    post(`${BASE}/replay/whatif`, { config_overrides: configOverrides }),

  // Notifications
  telegramHistory: (limit = 50) => get(`${BASE}/notifications/telegram-history?limit=${limit}`),
  testNotification: (userId, message, priority = "HIGH") =>
    post(`${BASE}/notifications/test`, { user_id: userId, priority, message }),

  // AIM Registry
  aimDetail: (aimId) => get(`${BASE}/aim/${aimId}/detail`),
  aimActivate: (aimId) => post(`${BASE}/aim/${aimId}/activate`, {}),
  aimDeactivate: (aimId) => post(`${BASE}/aim/${aimId}/deactivate`, {}),

  // Signals
  clearSignals: (userId, signalIds) =>
    post(`${BASE}/signals/clear`, { user_id: userId, signal_ids: signalIds }),

  // System
  gitPull: () => post(`${BASE}/system/git-pull`, {}),

  // Pseudotrader
  pseudotraderDecisions: (limit = 200) =>
    fetchJson(`${BASE}/pseudotrader/decisions?limit=${limit}`),
  pseudotraderParameters: () =>
    fetchJson(`${BASE}/pseudotrader/parameters`),
  pseudotraderHealth: () =>
    fetchJson(`${BASE}/pseudotrader/health`),
  pseudotraderTrends: (days = 30) =>
    fetchJson(`${BASE}/pseudotrader/trends?days=${days}`),
  pseudotraderVersions: (limit = 50) =>
    fetchJson(`${BASE}/pseudotrader/versions?limit=${limit}`),
  pseudotraderForecasts: () =>
    fetchJson(`${BASE}/pseudotrader/forecasts`),
};

export default api;
