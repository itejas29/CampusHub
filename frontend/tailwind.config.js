/** @type {import('tailwindcss').Config} */
// Tokens mirror design-system/campushub/MASTER.md. Components must reference
// these semantic names, never a raw hex value.
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--c-canvas) / <alpha-value>)",
        surface: "rgb(var(--c-surface) / <alpha-value>)",
        "surface-muted": "rgb(var(--c-surface-muted) / <alpha-value>)",
        "surface-raised": "rgb(var(--c-surface-raised) / <alpha-value>)",
        "surface-soft": "rgb(var(--c-surface-soft) / <alpha-value>)",
        "surface-sunken": "rgb(var(--c-surface-sunken) / <alpha-value>)",
        line: "rgb(var(--c-line) / <alpha-value>)",
        "line-strong": "rgb(var(--c-line-strong) / <alpha-value>)",
        ink: "rgb(var(--c-ink) / <alpha-value>)",
        "ink-muted": "rgb(var(--c-ink-muted) / <alpha-value>)",
        "ink-subtle": "rgb(var(--c-ink-subtle) / <alpha-value>)",
        brand: {
          DEFAULT: "rgb(var(--c-brand) / <alpha-value>)",
          hover: "rgb(var(--c-brand-hover) / <alpha-value>)",
          soft: "rgb(var(--c-brand-soft) / <alpha-value>)",
          fg: "rgb(var(--c-brand-fg) / <alpha-value>)",
        },
        // Fixed institutional navy — identical in light and dark, for brand
        // surfaces (the sign-in hero, dashboard heroes) that should never invert.
        navy: {
          DEFAULT: "#0B2545",
          deep: "#071A33",
          light: "#0F3B6C",
        },
        // `primary` is the interactive blue — the same token as `accent`.
        // Several screens were written against this name before it existed,
        // which left their buttons with no background at all.
        primary: {
          DEFAULT: "rgb(var(--c-accent) / <alpha-value>)",
          hover: "rgb(var(--c-accent-hover) / <alpha-value>)",
          soft: "rgb(var(--c-accent-soft) / <alpha-value>)",
          fg: "rgb(var(--c-accent-fg) / <alpha-value>)",
        },
        electric: "rgb(var(--c-electric) / <alpha-value>)",
        iris: {
          DEFAULT: "rgb(var(--c-iris) / <alpha-value>)",
          soft: "rgb(var(--c-iris-soft) / <alpha-value>)",
        },
        violet: {
          DEFAULT: "rgb(var(--c-violet) / <alpha-value>)",
          soft: "rgb(var(--c-violet-soft) / <alpha-value>)",
        },
        sidebar: {
          DEFAULT: "rgb(var(--c-sidebar-bg) / <alpha-value>)",
          ink: "rgb(var(--c-sidebar-ink) / <alpha-value>)",
          text: "rgb(var(--c-sidebar-item-text) / <alpha-value>)",
          icon: "rgb(var(--c-sidebar-item-icon) / <alpha-value>)",
          section: "rgb(var(--c-sidebar-section-text) / <alpha-value>)",
          active: "rgb(var(--c-sidebar-item-active-bg) / <alpha-value>)",
          "active-fg": "rgb(var(--c-sidebar-item-active-text) / <alpha-value>)",
          indicator: "rgb(var(--c-sidebar-indicator) / <alpha-value>)",
          logo: "rgb(var(--c-sidebar-logo-bg) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--c-accent) / <alpha-value>)",
          hover: "rgb(var(--c-accent-hover) / <alpha-value>)",
          soft: "rgb(var(--c-accent-soft) / <alpha-value>)",
          fg: "rgb(var(--c-accent-fg) / <alpha-value>)",
        },
        success: {
          DEFAULT: "rgb(var(--c-success) / <alpha-value>)",
          solid: "rgb(var(--c-success-solid) / <alpha-value>)",
          soft: "rgb(var(--c-success-soft) / <alpha-value>)",
          fg: "rgb(var(--c-success-fg) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "rgb(var(--c-warning) / <alpha-value>)",
          solid: "rgb(var(--c-warning-solid) / <alpha-value>)",
          soft: "rgb(var(--c-warning-soft) / <alpha-value>)",
        },
        danger: {
          DEFAULT: "rgb(var(--c-danger) / <alpha-value>)",
          soft: "rgb(var(--c-danger-soft) / <alpha-value>)",
          fg: "rgb(var(--c-danger-fg) / <alpha-value>)",
        },
        info: {
          DEFAULT: "rgb(var(--c-info) / <alpha-value>)",
          soft: "rgb(var(--c-info-soft) / <alpha-value>)",
          fg: "rgb(var(--c-info-fg) / <alpha-value>)",
        },
      },
      fontFamily: {
        // Family names containing a digit MUST stay quoted — an unquoted
        // `Source Sans 3` is invalid CSS and the browser drops the whole
        // font-family declaration (falling back to Times).
        sans: ['"Source Sans 3"', "ui-sans-serif", "system-ui", "sans-serif"],
        heading: ["Lexend", '"Source Sans 3"', "ui-sans-serif", "sans-serif"],
        display: ["Lexend", '"Source Sans 3"', "ui-sans-serif", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // Dense dashboard scale — nothing below 12px.
        "3xs": ["0.625rem", { lineHeight: "0.875rem", letterSpacing: "0.05em" }],
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.04em" }],
        xs: ["0.75rem", { lineHeight: "1.125rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.375rem" }],
        md: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.5rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem" }],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
        xl: "14px",
        "2xl": "18px",
      },
      boxShadow: {
        // Refined multi-layer shadows for premium card depth.
        "2xs": "0 1px 1px 0 rgb(15 23 42 / 0.04)",
        xs: "0 1px 2px 0 rgb(15 23 42 / 0.04)",
        sm:
          "0 1px 3px 0 rgb(15 23 42 / 0.06), " +
          "0 1px 2px -1px rgb(15 23 42 / 0.04)",
        md:
          "0 4px 12px -2px rgb(15 23 42 / 0.08), " +
          "0 2px 4px -2px rgb(15 23 42 / 0.04)",
        lg:
          "0 12px 32px -8px rgb(15 23 42 / 0.14), " +
          "0 4px 8px -4px rgb(15 23 42 / 0.06)",
        xl:
          "0 24px 48px -12px rgb(15 23 42 / 0.20), " +
          "0 8px 16px -8px rgb(15 23 42 / 0.08)",
        // Focused input ring
        "focus-ring": "0 0 0 3px rgb(var(--c-accent) / 0.15)",
        // Card hover lift
        "glow-accent": "0 6px 20px -6px rgb(var(--c-accent) / 0.55)",
        "card-hover":
          "0 6px 20px -4px rgb(15 23 42 / 0.10), " +
          "0 2px 6px -2px rgb(15 23 42 / 0.05)",
      },
      backgroundImage: {
        "brand-gradient":
          "linear-gradient(135deg, #0B2545 0%, #0F3B6C 45%, #2563EB 100%)",
        "accent-gradient":
          "linear-gradient(135deg, rgb(var(--c-accent)) 0%, rgb(var(--c-iris)) 60%, rgb(var(--c-violet)) 100%)",
      },
      backdropBlur: { xs: "2px" },
      transitionDuration: { DEFAULT: "180ms" },
      transitionTimingFunction: {
        smooth: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      spacing: {
        4.5: "1.125rem",
        8.5: "2.125rem",
        18: "4.5rem",
        72: "18rem",
        80: "20rem",
        88: "22rem",
        96: "24rem",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down": {
          from: { opacity: "0", transform: "translateY(-6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: { "100%": { transform: "translateX(200%)" } },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgb(var(--c-accent) / 0.3)" },
          "70%": { boxShadow: "0 0 0 6px transparent" },
          "100%": { boxShadow: "0 0 0 0 transparent" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        "slide-up": "slide-up 200ms cubic-bezier(0.16,1,0.3,1)",
        "slide-down": "slide-down 180ms cubic-bezier(0.16,1,0.3,1)",
        "scale-in": "scale-in 180ms cubic-bezier(0.16,1,0.3,1)",
        "pulse-ring": "pulse-ring 1.2s cubic-bezier(0.36,0.07,0.19,0.97) infinite",
      },
    },
  },
  plugins: [],
};
