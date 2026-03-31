import { create } from "zustand";
import api from "../api/client";

const useProcessesStore = create((set, get) => ({
  processes: {},
  blocks: [],
  lockedStrategies: [],
  apiConnections: { connected: 0, total: 0 },
  loading: true,
  error: null,
  pollInterval: null,

  fetch: async () => {
    try {
      const data = await api.processesStatus();
      set({
        processes: data.processes || {},
        blocks: data.blocks || [],
        lockedStrategies: data.locked_strategies || [],
        apiConnections: data.api_connections || { connected: 0, total: 0 },
        loading: false,
        error: null,
      });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  startPolling: () => {
    const { fetch } = get();
    fetch();
    const id = setInterval(fetch, 15000);
    set({ pollInterval: id });
  },

  stopPolling: () => {
    const { pollInterval } = get();
    if (pollInterval) clearInterval(pollInterval);
    set({ pollInterval: null });
  },
}));

export default useProcessesStore;
