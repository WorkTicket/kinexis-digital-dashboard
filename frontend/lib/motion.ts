/**
 * Canonical motion tokens — import these; do not hand-write duration-/ease- in components.
 * CSS implementations live in globals.css as `.motion-*` utilities.
 */

export const motion = {
  /** Load-in entrance */
  loadIn: "animate-fade-up",
  fadeIn: "animate-fade-in",
  scaleIn: "animate-scale-in",

  /** 140ms micro hover / color */
  micro: "motion-micro",
  /** 140ms transform (chevrons, sidebar) */
  microTransform: "motion-micro-transform",
  /** 300ms general property changes */
  state: "motion-state",
  /** Gauge / ring stroke fill (~700ms) */
  gauge: "motion-gauge",
  /** Progress bar width (~500ms) */
  bar: "motion-bar",

  settle: "animate-state-settle",
  resolve: "animate-state-resolve",
  busy: "animate-state-busy",

  /** Stagger delay style for inline use */
  stagger(i: number): { animationDelay: string } {
    return { animationDelay: `${i * 50}ms` };
  },

  /** Named stagger class (1–4) for animate-fade-up companions */
  staggerClass(i: number): string {
    const n = Math.min(Math.max(Math.floor(i) + 1, 1), 4);
    return `animate-stagger-${n}`;
  },
} as const;

export type MotionKey = Exclude<keyof typeof motion, "stagger" | "staggerClass">;
