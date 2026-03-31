import { create } from "zustand";

const useChartStore = create((set, get) => ({
  bars: [],
  timeframe: "5m",
  selectedAsset: "MES",
  overlays: {
    or: true,
    entry: true,
    sl: true,
    tp: true,
    vwap: false,
  },

  addBar: (bar) => {
    const current = get().bars;
    const lastBar = current[current.length - 1];
    // If same timestamp, update last bar; otherwise append
    if (lastBar && lastBar.time === bar.time) {
      set({ bars: [...current.slice(0, -1), bar] });
    } else {
      set({ bars: [...current, bar] });
    }
  },

  setTimeframe: (timeframe) => set({ timeframe, bars: [] }), // Clear bars on timeframe change
  setSelectedAsset: (selectedAsset) => set({ selectedAsset, bars: [] }), // Clear bars on asset change

  toggleOverlay: (name) =>
    set((state) => ({
      overlays: { ...state.overlays, [name]: !state.overlays[name] },
    })),
}));

export default useChartStore;
