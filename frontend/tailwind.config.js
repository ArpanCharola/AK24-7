/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "Segoe UI Variable",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "SF Mono",
          "JetBrains Mono",
          "Menlo",
          "Consolas",
          "ui-monospace",
          "monospace",
        ],
      },
      colors: {
        // shadcn neutral theme tokens (HSL CSS vars defined in index.css)
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        // "accent" was the purple brand; remapped to neutral zinc so every
        // existing accent-* usage reads as the shadcn neutral admin look.
        accent: {
          50:  "#fafafa",
          100: "#f4f4f5",
          200: "#e4e4e7",
          300: "#d4d4d8",
          400: "#a1a1aa",
          500: "#71717a",
          600: "#52525b",
          700: "#3f3f46",
          800: "#27272a",
          900: "#18181b",
        },
      },
      backdropBlur: {
        xs: "2px",
      },
      boxShadow: {
        glass:        "0 1px 0 rgba(255,255,255,0.6) inset, 0 8px 32px -8px rgba(15,23,42,0.12), 0 2px 8px -2px rgba(15,23,42,0.06)",
        "glass-lg":   "0 1px 0 rgba(255,255,255,0.7) inset, 0 24px 60px -16px rgba(15,23,42,0.22), 0 8px 24px -6px rgba(15,23,42,0.10)",
        "glass-dark": "0 1px 0 rgba(255,255,255,0.06) inset, 0 8px 32px -8px rgba(0,0,0,0.4), 0 2px 8px -2px rgba(0,0,0,0.25)",
        "ring-accent":"0 0 0 4px rgba(126,83,255,0.18)",
        "inner-soft": "inset 0 1px 2px rgba(15,23,42,0.06)",
      },
      keyframes: {
        "fade-in": {
          "0%":   { opacity: 0, transform: "translateY(4px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        "slide-up": {
          "0%":   { opacity: 0, transform: "translateY(12px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        shimmer: {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 250ms ease-out both",
        "slide-up": "slide-up 350ms cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer:   "shimmer 2.4s linear infinite",
      },
    },
  },
  plugins: [],
}
