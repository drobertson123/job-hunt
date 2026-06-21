import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#f6f4f0",
        paper: "#efeae2",                              // kanban columns
        surface: { DEFAULT: "#ffffff", alt: "#fbfaf8", sunk: "#f1ede7" },
        line: { DEFAULT: "#ebe7e1", soft: "#f1ede7", strong: "#e6e0d6" },
        ink: { DEFAULT: "#211e2b", body: "#3b3746", muted: "#6c6678", subtle: "#9a95a3", faint: "#a39c92" },
        panel: "#211e2b",                              // dark cards
        accent: { DEFAULT: "#5750d9", ink: "#4840c0", mid: "#7a73e6", light: "#a8a3f0", soft: "#c9c5f2", tint: "#ecebfb" },
        ok: { DEFAULT: "#3f9a6e", deep: "#2f7a57", soft: "#e8f3ec", mint: "#7ee0b0" },
        warn: { DEFAULT: "#c98a2e", soft: "#f7efe1" },
        error: { DEFAULT: "#d35a4a", soft: "#fbecea" },
        override: { DEFAULT: "#5750d9", soft: "#ecebfb" },
        stale: { DEFAULT: "#9a95a3", soft: "#f1ede7" },
      },
      fontFamily: {
        sans: ['Figtree', '"Segoe UI"', "-apple-system", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', '"SF Mono"', "Menlo", "Consolas", "monospace"],
      },
      borderRadius: { xs: "4px", sm: "7px", md: "11px", lg: "14px", xl: "16px" },
      boxShadow: {
        panel: "0 1px 0 rgba(33,30,43,0.04)",
        card: "0 8px 22px rgba(33,30,43,0.10)",
        accent: "0 3px 10px rgba(87,80,217,0.25)",
        pop: "0 6px 16px rgba(33,30,43,0.08)",
        modal: "0 12px 32px rgba(33,30,43,0.18)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
