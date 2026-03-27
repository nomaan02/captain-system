import { create } from "zustand";

type Theme = "dark" | "light";

interface ThemeState {
  theme: Theme;
  toggle: () => void;
}

function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem("captain-theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // ignore
  }
  return "dark";
}

export const useThemeStore = create<ThemeState>()((set) => ({
  theme: getInitialTheme(),
  toggle: () =>
    set((state) => {
      const next = state.theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem("captain-theme", next);
      } catch {
        // ignore
      }
      return { theme: next };
    }),
}));
