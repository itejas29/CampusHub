import { animate, useInView, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

/**
 * A number that counts up to its value the first time it scrolls into view.
 *
 * Only for real figures from the API — it animates what the server returned,
 * never a placeholder. It runs once per mount: a background refetch that
 * changes the value jumps straight to the new number rather than replaying.
 *
 * This is one of the "unusual" cases `lib/motion.ts` allows a component to
 * read `useReducedMotion()` for: MotionConfig cannot reach a value written into
 * text content, so the reduced-motion path renders the final number directly.
 */
export function CountUp({ value, duration = 0.7 }: { value: number; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const started = useRef(false);
  const [shown, setShown] = useState(reduce ? value : 0);

  useEffect(() => {
    if (reduce || started.current) {
      setShown(value);
      return;
    }
    if (!inView) return;
    started.current = true;
    const controls = animate(0, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setShown(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, value, reduce, duration]);

  return (
    <span ref={ref} aria-label={String(value)}>
      <span aria-hidden>{shown.toLocaleString("en-IN")}</span>
    </span>
  );
}
