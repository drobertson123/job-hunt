import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#f5f6f7",
        surface: { DEFAULT: "#ffffff", alt: "#fafbfc", sunk: "#edeef0" },
        line: { DEFAULT: "#d8dbe0", soft: "#e8eaee", strong: "#b5bac2" },
        ink: { DEFAULT: "#0f1620", muted: "#5a6270", subtle: "#8a929e" },
        accent: { DEFAULT: "#0f766e", soft: "#e6f2f0", ink: "#0a4f49" },
        ok: { DEFAULT: "#2f7d4e", soft: "#e5f3ea" },
        override: { DEFAULT: "#3b7bb8", soft: "#e6eef7" },
        warn: { DEFAULT: "#b45816", soft: "#fbecdd" },
        error: { DEFAULT: "#a6342a", soft: "#f5e1df" },
        stale: { DEFAULT: "#7a8494", soft: "#e5e7ea" },
      },
      fontFamily: {
        sans: ['Inter', '"Segoe UI"', "-apple-system", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { xs: "2px", sm: "3px", md: "4px", lg: "6px" },
      boxShadow: {
        panel: "0 1px 0 rgba(15,22,32,0.04)",
        pop: "0 1px 2px rgba(15,22,32,0.06), 0 4px 12px rgba(15,22,32,0.08)",
        modal: "0 8px 32px rgba(15,22,32,0.18)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
