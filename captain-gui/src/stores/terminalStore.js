import { create } from "zustand";

const MAX_ENTRIES = 500;
let _seq = 0;

const useTerminalStore = create((set) => ({
  entries: [],
  addEntry: (entry) =>
    set((state) => ({
      entries: [
        ...state.entries,
        { ...entry, _seq: ++_seq },
      ].slice(-MAX_ENTRIES),
    })),
  clear: () => set({ entries: [] }),
}));

export default useTerminalStore;
