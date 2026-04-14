import { create } from "zustand";

const MAX_ENTRIES = 500;
const MAX_BACKEND = 800;
let _seq = 0;

const useTerminalStore = create((set) => ({
  entries: [],
  backendEntries: [],
  addEntry: (entry) =>
    set((state) => ({
      entries: [
        ...state.entries,
        { ...entry, _seq: ++_seq },
      ].slice(-MAX_ENTRIES),
    })),
  addBackendEntry: (entry) =>
    set((state) => ({
      backendEntries: [
        ...state.backendEntries,
        { ...entry, _seq: ++_seq },
      ].slice(-MAX_BACKEND),
    })),
  clear: () => set({ entries: [], backendEntries: [] }),
}));

export default useTerminalStore;
