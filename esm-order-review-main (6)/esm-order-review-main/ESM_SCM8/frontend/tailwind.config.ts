import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#e6002d",
          dark: "#b80024",
          50: "#fff1f4",
          100: "#ffd8e1",
          500: "#e6002d",
          600: "#e6002d",
          700: "#b80024",
          900: "#000000"
        },
        slate: {
          25: "#fafafa",
          75: "#f4f4f4"
        },
        ink: "#111111",
        ink3: "var(--text-3)",
        line: "#dedede",
        cloud: "#f6f6f6",
        danger: "#e6002d",
        page: "var(--bg)",
        surface: {
          DEFAULT: "var(--surface)",
          soft: "var(--surface-soft)"
        },
        sidebar: "var(--sidebar)",
        dropdownpanel: "var(--dropdown-panel)",
        border: "var(--border)",
        divider: "var(--divider)",
        row: "var(--row)",
        rowline: "var(--border-soft)",
        track: "var(--track)",
        segbg: "var(--seg-bg)",
        muted: "var(--muted)",
        muted2: "var(--muted-2)",
        pos: {
          DEFAULT: "var(--pos)",
          bg: "var(--pos-bg)",
          border: "var(--pos-border)"
        },
        warn: {
          DEFAULT: "var(--warn)",
          bg: "var(--warn-bg)",
          border: "var(--warn-border)"
        },
        brandDark: "var(--accent-dark)",
        slatebar: "#18181b",
        about: {
          black: "var(--text-strong)",
          ink: "var(--text-700)",
          muted: "var(--text-3)",
          faint: "var(--muted-2)",
          line: "var(--border)",
          bg: "var(--surface)",
          surface: "var(--surface-soft)",
          accent: "var(--about-accent)",
          accentDark: "var(--about-accent-strong)",
          warm: "var(--about-warm)"
        }
      },
      boxShadow: {
        soft: "0 10px 30px rgba(15, 23, 42, 0.08)",
        panel: "0 18px 55px rgba(15, 23, 42, 0.14)",
        card: "0 1px 2px rgba(15, 23, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
