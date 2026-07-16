import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        ring: "var(--ring)",
        brand: {
          50: "rgb(var(--brand-50-rgb) / <alpha-value>)",
          100: "rgb(var(--brand-100-rgb) / <alpha-value>)",
          200: "rgb(var(--brand-200-rgb) / <alpha-value>)",
          300: "rgb(var(--brand-300-rgb) / <alpha-value>)",
          400: "rgb(var(--brand-400-rgb) / <alpha-value>)",
          500: "rgb(var(--brand-500-rgb) / <alpha-value>)",
          600: "rgb(var(--brand-600-rgb) / <alpha-value>)",
          700: "rgb(var(--brand-700-rgb) / <alpha-value>)",
          800: "rgb(var(--brand-800-rgb) / <alpha-value>)",
          900: "rgb(var(--brand-900-rgb) / <alpha-value>)",
        },
        accent: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "rgb(var(--accent-500-rgb) / <alpha-value>)",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
        },
        surface: {
          DEFAULT: "rgb(var(--surface-rgb) / <alpha-value>)",
          light: "rgb(var(--surface-light-rgb) / <alpha-value>)",
          elevated: "rgb(var(--surface-elevated-rgb) / <alpha-value>)",
          lighter: "rgb(var(--surface-lighter-rgb) / <alpha-value>)",
          border: "rgb(var(--surface-border-rgb) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--ink-rgb) / <alpha-value>)",
          secondary: "rgb(var(--ink-secondary-rgb) / <alpha-value>)",
          muted: "rgb(var(--muted-rgb) / <alpha-value>)",
          dim: "rgb(var(--muted-dim-rgb) / <alpha-value>)",
        },
        kinexis: {
          ink: "rgb(var(--kinexis-ink-rgb) / <alpha-value>)",
          mist: "rgb(var(--kinexis-mist-rgb) / <alpha-value>)",
          focus: "rgb(var(--kinexis-focus-rgb) / <alpha-value>)",
          signal: "rgb(var(--kinexis-signal-rgb) / <alpha-value>)",
          proof: "rgb(var(--kinexis-proof-rgb) / <alpha-value>)",
          risk: "rgb(var(--kinexis-risk-rgb) / <alpha-value>)",
          momentum: "rgb(var(--kinexis-momentum-rgb) / <alpha-value>)",
        },
        success: "rgb(var(--success-rgb) / <alpha-value>)",
        danger: "rgb(var(--danger-rgb) / <alpha-value>)",
        warning: "rgb(var(--warning-rgb) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-ui)", "system-ui", "sans-serif"],
        ui: ["var(--font-ui)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
        "panel-lg": "var(--shadow-panel-lg)",
        dropdown: "var(--shadow-dropdown)",
      },
      borderRadius: {
        DEFAULT: "10px",
        sm: "8px",
        md: "10px",
        lg: "14px",
        xl: "18px",
      },
      transitionDuration: {
        micro: "160ms",
        state: "280ms",
        gauge: "700ms",
        bar: "500ms",
      },
      transitionTimingFunction: {
        smooth: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [animate],
};

export default config;
