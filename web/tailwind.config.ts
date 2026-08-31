import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Backgrounds - professional dark palette
        ink: "#0a0e14",
        panel: "#0f1419",
        "panel-elevated": "#1a1f26",
        
        // Borders - subtle, not bright
        line: "#262d38",
        "line-strong": "#384152",
        
        // Text hierarchy
        mute: "#64748b",
        "text-primary": "#e2e8f0",
        "text-secondary": "#94a3b8",
        "text-tertiary": "#64748b",
        
        // Semantic colors - only for numbers in tables
        up: "#10b981",
        down: "#ef4444",
        
        // Accents - professional blues/ambers
        accent: "#3b82f6",
        "accent-muted": "#475569",
        warning: "#f59e0b",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
