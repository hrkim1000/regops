import type { Config } from 'tailwindcss';

// Dark theme is the default, not a toggle (frontend-page skill).
export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: { DEFAULT: '#0f1115', raised: '#171a21', border: '#252a33' },
        accent: { DEFAULT: '#5b9dff', muted: '#2c4a7c' },
      },
      fontFamily: { mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'] },
    },
  },
  plugins: [],
} satisfies Config;
