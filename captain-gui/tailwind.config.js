/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0a0f0d',
          dark: '#080e0d',
          card: '#08100f',
          elevated: '#0a1614',
        },
        border: {
          DEFAULT: '#1e293b',
          subtle: '#1a3038',
          accent: '#2e4e5a',
        },
        captain: {
          green: '#0faf7a',
          red: '#ef4444',
          cyan: '#06b6d4',
          amber: '#f59e0b',
          blue: '#3b82f6',
          orange: '#ff8800',
          pink: '#ff0040',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'SF Mono', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  corePlugins: {
    preflight: false,
  },
};
