import { create } from "zustand";
import api from "../api/client";

const usePseudotraderStore = create((set) => ({
  decisions: [],
  parameters: null,
  health: null,
  trends: [],
  versions: [],
  forecasts: [],
  loading: true,
  error: null,

  fetchDecisions: async (limit = 200) => {
    try {
      const data = await api.pseudotraderDecisions(limit);
      set({ decisions: data.decisions || [] });
    } catch (err) {
      console.warn("Failed to fetch pseudotrader decisions:", err);
    }
  },

  fetchParameters: async () => {
    try {
      const data = await api.pseudotraderParameters();
      set({ parameters: data });
    } catch (err) {
      console.warn("Failed to fetch pseudotrader parameters:", err);
    }
  },

  fetchHealth: async () => {
    try {
      const data = await api.pseudotraderHealth();
      set({ health: data.health || null });
    } catch (err) {
      console.warn("Failed to fetch pseudotrader health:", err);
    }
  },

  fetchTrends: async (days = 30) => {
    try {
      const data = await api.pseudotraderTrends(days);
      set({ trends: data.trends || [] });
    } catch (err) {
      console.warn("Failed to fetch pseudotrader trends:", err);
    }
  },

  fetchVersions: async (limit = 50) => {
    try {
      const data = await api.pseudotraderVersions(limit);
      set({ versions: data.versions || [] });
    } catch (err) {
      console.warn("Failed to fetch pseudotrader versions:", err);
    }
  },

  fetchForecasts: async () => {
    try {
      const data = await api.pseudotraderForecasts();
      set({ forecasts: data.forecasts || [] });
    } catch (err) {
      console.warn("Failed to fetch pseudotrader forecasts:", err);
    }
  },

  fetchAll: async () => {
    set({ loading: true, error: null });
    try {
      const [decData, paramData, healthData, trendsData, versionsData, forecastsData] =
        await Promise.allSettled([
          api.pseudotraderDecisions(),
          api.pseudotraderParameters(),
          api.pseudotraderHealth(),
          api.pseudotraderTrends(),
          api.pseudotraderVersions(),
          api.pseudotraderForecasts(),
        ]);
      set({
        decisions: decData.status === "fulfilled" ? decData.value.decisions || [] : [],
        parameters: paramData.status === "fulfilled" ? paramData.value : null,
        health: healthData.status === "fulfilled" ? healthData.value.health || null : null,
        trends: trendsData.status === "fulfilled" ? trendsData.value.trends || [] : [],
        versions: versionsData.status === "fulfilled" ? versionsData.value.versions || [] : [],
        forecasts: forecastsData.status === "fulfilled" ? forecastsData.value.forecasts || [] : [],
        loading: false,
      });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },
}));

export default usePseudotraderStore;
