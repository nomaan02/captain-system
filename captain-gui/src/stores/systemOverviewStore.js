import { create } from "zustand";
import api from "../api/client";

const useSystemOverviewStore = create((set) => ({
  overview: null,
  loading: true,
  error: null,

  fetch: async () => {
    try {
      const data = await api.systemOverview();
      set({ overview: data, loading: false, error: null });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  setOverview: (data) => set({ overview: data, loading: false }),
}));

export default useSystemOverviewStore;
