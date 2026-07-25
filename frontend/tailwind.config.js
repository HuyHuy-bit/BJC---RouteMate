/** @type {import('tailwindcss').Config} */

/* Every value here points at a CSS custom property declared in
   src/index.css. That indirection is what makes dark mode a
   token swap rather than a per-component `dark:` variant on every
   element — and it means `bg-surface` is correct in both themes.

   Consequently: no component should contain a raw hex value, and
   none should reach for bg-[var(--surface)] either. If a utility
   you want doesn't exist, add it here. */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Surfaces */
        canvas: "var(--bg)",
        surface: "var(--surface)",
        sunken: "var(--surface-sunken)",
        inverse: "var(--surface-inverse)",

        /* Text. Named for weight-in-the-hierarchy, not for hue,
           so they stay meaningful when the theme flips. */
        ink: "var(--text)",
        muted: "var(--text-secondary)",
        faint: "var(--text-tertiary)",
        "on-inverse": "var(--text-on-inverse)",
        "on-danger": "var(--on-danger)",

        /* Brand orange, split by contrast duty — see index.css.
           `brand` is the deep fill that carries white text and is
           identical in both themes. `accent` is the bright logo
           orange for marks and indicators only. `accent-text` is the
           readable-at-body-size variant. */
        brand: {
          DEFAULT: "var(--brand)",
          hover: "var(--brand-hover)",
          subtle: "var(--brand-subtle)",
          text: "var(--accent-text)",
        },
        accent: "var(--accent)",
        navy: "var(--navy)",
        cobalt: {
          DEFAULT: "var(--cobalt)",
          subtle: "var(--cobalt-subtle)",
        },

        /* Semantic */
        success: { DEFAULT: "var(--success)", subtle: "var(--success-subtle)" },
        warning: { DEFAULT: "var(--warning)", subtle: "var(--warning-subtle)" },
        danger: { DEFAULT: "var(--danger)", subtle: "var(--danger-subtle)" },
        info: { DEFAULT: "var(--info)", subtle: "var(--info-subtle)" },

        /* Borders. `line` is decorative separation; `line-strong`
           is the edge of an interactive control and clears 3:1. */
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
          focus: "var(--border-focus)",
        },

        scrim: "var(--scrim)",
        "photo-ground": "var(--photo-ground)",
      },

      /* Eight steps, nothing between them. Body is 14px, so `base`
         is 14 and `sm`/`xs` step down into dense-data territory.
         Arbitrary text-[Npx] should not appear in components. */
      fontSize: {
        "2xs": ["11px", { lineHeight: "1.45" }],
        xs: ["12px", { lineHeight: "1.5" }],
        sm: ["13px", { lineHeight: "1.5" }],
        base: ["14px", { lineHeight: "1.55" }],
        lg: ["16px", { lineHeight: "1.45" }],
        xl: ["20px", { lineHeight: "1.3", letterSpacing: "-0.014em" }],
        "2xl": ["26px", { lineHeight: "1.2", letterSpacing: "-0.02em" }],
        "3xl": ["34px", { lineHeight: "1.1", letterSpacing: "-0.026em" }],
        "4xl": ["42px", { lineHeight: "1.05", letterSpacing: "-0.032em" }],
      },

      fontFamily: {
        display: "var(--font-display)",
        body: "var(--font-body)",
        mono: "var(--font-mono)",
      },

      /* Four steps. 4px was folded into 6px — at this surface area
         the difference was invisible and cost a decision each time. */
      borderRadius: {
        none: "0",
        DEFAULT: "6px",
        md: "8px",
        lg: "12px",
        full: "9999px",
      },

      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        none: "none",
      },

      spacing: {
        /* Minimum comfortable touch target. Driver screens and any
           control a dispatcher taps on a tablet should use this
           rather than the 28px `sm` button height. */
        touch: "2.75rem",
      },

      transitionTimingFunction: {
        brand: "var(--ease)",
      },

      transitionDuration: {
        fast: "var(--duration-fast)",
        base: "var(--duration)",
        DEFAULT: "var(--duration)",
        slow: "var(--duration-slow)",
      },

      /* Named layers, so stacking order is a decision recorded in
         one place rather than a z-[90] guessed at the call site. */
      zIndex: {
        header: "40",
        dropdown: "60",
        slideover: "80",
        dialog: "90",
        toast: "100",
      },

      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
      },
    },
  },
  plugins: [],
};
