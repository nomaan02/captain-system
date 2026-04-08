import { create } from "zustand";
import api from "../api/client";

const useReportsStore = create((set) => ({
  reportTypes: [],
  selectedType: null,
  generating: false,
  result: null,
  error: null,
  loading: true,

  fetchTypes: async () => {
    try {
      const data = await api.reportTypes();
      const types = Array.isArray(data) ? data : data.report_types || [];
      set({ reportTypes: types, selectedType: types[0] || null, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  selectType: (type) => set({ selectedType: type, result: null, error: null }),

  generate: async (reportType, userId) => {
    set({ generating: true, result: null, error: null });
    try {
      const data = await api.generateReport({
        report_type: reportType,
        user_id: userId,
        params: {},
      });
      set({ result: data, generating: false });
    } catch (err) {
      set({ error: err.message, generating: false });
    }
  },
}));

export default useReportsStore;
