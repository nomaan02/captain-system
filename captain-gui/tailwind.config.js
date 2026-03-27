import animate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        /* ── Legacy (backward compat — existing panels reference these) ── */
        captain: {
          green: "#22c55e",
          red: "#ef4444",
          amber: "#f59e0b",
          blue: "#3b82f6",
          purple: "#8b5cf6",
        },

        /* ── Surfaces ── */
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          elevated: "var(--card-elevated)",
          foreground: "var(--foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--foreground)",
        },

        /* ── Text tiers ── */
        dim: "var(--dim-foreground)",
        ghost: "var(--ghost-foreground)",

        /* ── Borders ── */
        border: "var(--border)",
        "border-subtle": "var(--border-subtle)",
        ring: "var(--ring)",
        input: "var(--border)",

        /* ── Status: solid ── */
        green: "var(--green)",
        "green-dim": "var(--green-dim)",
        red: "var(--red)",
        "red-dim": "var(--red-dim)",
        amber: "var(--amber)",
        "amber-bright": "var(--amber-bright)",
        blue: "var(--blue)",
        "blue-raw": "var(--blue-raw)",

        /* ── Status: tinted backgrounds ── */
        "green-tint": "var(--green-tint)",
        "red-tint": "var(--red-tint)",
        "amber-tint": "var(--amber-tint)",
        "blue-tint": "var(--blue-tint)",

        /* ── Status: borders ── */
        "green-border": "var(--green-border)",
        "red-border": "var(--red-border)",
        "amber-border": "var(--amber-border)",
        "blue-border": "var(--blue-border)",

        /* ── Status: dim text (on colored backgrounds) ── */
        "green-dim": "var(--green-dim)",
        "red-dim": "var(--red-dim)",

        /* ── Neutral badge ── */
        "neutral-badge-bg": "var(--neutral-badge-bg)",
        "neutral-badge-text": "var(--neutral-badge-text)",

        /* ── Brand ── */
        brand: "var(--brand)",

        /* ── Semantic (shadcn compat) ── */
        primary: {
          DEFAULT: "var(--blue-raw)",
          foreground: "var(--foreground)",
        },
        secondary: {
          DEFAULT: "var(--muted)",
          foreground: "var(--foreground)",
        },
        destructive: {
          DEFAULT: "var(--red)",
          foreground: "var(--foreground)",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 1px)",
        sm: "calc(var(--radius) - 2px)",
      },
      keyframes: {
        "collapsible-down": {
          from: { height: "0" },
          to: { height: "var(--radix-collapsible-content-height)" },
        },
        "collapsible-up": {
          from: { height: "var(--radix-collapsible-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "collapsible-down": "collapsible-down 200ms ease-out",
        "collapsible-up": "collapsible-up 200ms ease-out",
      },
    },
  },
  plugins: [animate],
};
