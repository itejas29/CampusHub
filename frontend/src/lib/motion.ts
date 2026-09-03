import type { Transition, Variants } from "framer-motion";

/**
 * Shared motion tokens.
 *
 * These deliberately mirror the CSS animation timings already in
 * `tailwind.config.js` (160-180ms, ease-out) so a Framer Motion transition and
 * a Tailwind `transition-colors` on the same element read as one system rather
 * than two competing ones.
 *
 * Motion here is functional, not decorative: it shows where a thing came from
 * and where it went. Anything longer than ~260ms starts to feel like lag in a
 * dense admin UI, so the scale tops out there.
 *
 * Reduced motion is handled globally by `<MotionConfig reducedMotion="user">`
 * in App.tsx — it strips transform and layout animation while keeping opacity,
 * so screens still read as responsive. Individual components therefore should
 * NOT branch on `useReducedMotion()` unless they do something unusual.
 */

export const DURATION = {
  fast: 0.14,
  base: 0.18,
  slow: 0.26,
} as const;

/** Matches the `ease-out` used by the CSS keyframes. */
export const EASE = [0.16, 1, 0.3, 1] as const;

export const transition: Transition = {
  duration: DURATION.base,
  ease: EASE,
};

export const fastTransition: Transition = {
  duration: DURATION.fast,
  ease: EASE,
};

/** For anything the user is driving directly (drawers, drags). */
export const spring: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 36,
};

export const fade: Variants = {
  hidden: { opacity: 0 },
  shown: { opacity: 1, transition: fastTransition },
  exit: { opacity: 0, transition: fastTransition },
};

/**
 * The default page/section entrance.
 *
 * Vertical only — a horizontal translate on a full-width page can push the
 * document sideways mid-transition, and the portal's layout rule is that the
 * page body never scrolls horizontally.
 */
export const slideUp: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition },
  exit: { opacity: 0, y: -4, transition: fastTransition },
};

/** Dialog panels: a slight scale reads as "in front of" rather than "below". */
export const dialogPanel: Variants = {
  hidden: { opacity: 0, y: 8, scale: 0.98 },
  shown: { opacity: 1, y: 0, scale: 1, transition },
  exit: { opacity: 0, y: 4, scale: 0.98, transition: fastTransition },
};

/** Popovers and dropdowns, anchored to their trigger. */
export const popoverPanel: Variants = {
  hidden: { opacity: 0, y: -4, scale: 0.98 },
  shown: { opacity: 1, y: 0, scale: 1, transition: fastTransition },
  exit: { opacity: 0, y: -4, scale: 0.98, transition: fastTransition },
};

/** The mobile navigation drawer, which enters from the left edge. */
export const drawerLeft: Variants = {
  hidden: { x: "-100%" },
  shown: { x: 0, transition: spring },
  exit: { x: "-100%", transition: { duration: DURATION.base, ease: EASE } },
};

/**
 * List/grid orchestration. Put `listContainer` on the wrapper and `listItem` on
 * each child; the stagger then belongs to the container, so it stays correct
 * when the list length changes instead of needing a computed per-item delay.
 */
export const listContainer: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.035, delayChildren: 0.02 } },
};

export const listItem: Variants = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition },
};
