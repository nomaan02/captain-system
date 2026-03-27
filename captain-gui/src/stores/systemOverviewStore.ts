import { create } from "zustand";
import type { SystemOverview } from "@/api/types";

interface SystemOverviewState {
  overview: SystemOverview | null;
  setOverview: (o: SystemOverview) => void;
}

export const useSystemOverviewStore = create<SystemOverviewState>()((set) => ({
  overview: null,
  setOverview: (overview) => set({ overview }),
}));
