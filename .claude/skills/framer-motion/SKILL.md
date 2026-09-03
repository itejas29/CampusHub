---
name: framer-motion
description: "Use framer-motion (Motion for React) for animation and interaction work in any React project - page and route transitions, modals/drawers/dropdowns entering and leaving, list add/remove/reorder, hover and tap feedback, scroll reveals, drag, shared-element and layout transitions, loading and skeleton states. Reach for this skill whenever a request involves motion in a React UI even if framer-motion is never named: 'animate this', 'add a transition', 'make it slide/fade in', 'smooth this out', 'make it feel polished/less janky', 'animate the modal', 'stagger the cards', or when reviewing code that hand-rolls animation with setTimeout, requestAnimationFrame, CSS keyframes, or manual mount/unmount delays. Covers installing it when the project does not have it yet, and the accessibility, performance, and API conventions to follow once it is there."
---

# framer-motion

The preferred animation library for React work here. The point of standardising
on it is that animation code stops being bespoke: mount/unmount, layout changes,
and gesture feedback all get expressed declaratively instead of as timers and
class-toggling, which is where animation bugs actually live.

## Get it into the project first

Check `package.json` before writing any `motion.*` JSX — importing a package
that isn't installed produces a confusing build error rather than an obvious one.

Install with whatever the repo already uses; the lockfile tells you:

| Lockfile | Command |
|---|---|
| `package-lock.json` | `npm i framer-motion` |
| `pnpm-lock.yaml` | `pnpm add framer-motion` |
| `yarn.lock` | `yarn add framer-motion` |
| `bun.lockb` / `bun.lock` | `bun add framer-motion` |

Commit the lockfile change alongside `package.json`.

### Which package name

The library was renamed **Motion**, and `motion` and `framer-motion` now ship
the same releases from the same version line. Both are current — `framer-motion`
is not deprecated.

- Project already imports from `framer-motion` → keep using it. Don't migrate a
  working codebase for a name.
- Greenfield, or the project already has `motion` → `import { motion } from 'motion/react'`.

Never leave both installed. Two copies means two contexts, and `AnimatePresence`
silently stops seeing children that were created by the other copy.

## Patterns worth following

### Respect reduced motion — this is not optional polish

Vestibular disorders make large motion genuinely unpleasant, and some people
have the OS setting on for good reason. The cheap global fix:

```tsx
import { MotionConfig } from 'framer-motion'

<MotionConfig reducedMotion="user">
  <App />
</MotionConfig>
```

That disables transform and layout animation for those users while keeping
opacity and colour, so interfaces still read as responsive rather than dead.
When one component needs to branch on it, `useReducedMotion()` returns the
boolean.

### Animate transform and opacity, not layout properties

`x`, `y`, `scale`, `rotate` and `opacity` are handled by the compositor. `width`,
`height`, `top`, `left` and `margin` force layout and paint on every frame, which
is what "the animation is janky on my laptop" usually turns out to be.

When the size or position genuinely changes, don't animate the box — hand it to
the `layout` prop, which measures the before/after and plays the difference back
as a transform:

```tsx
<motion.div layout />
```

### AnimatePresence, and the two rules that break it

Exit animations need the element to stay mounted while it plays, which React
won't do on its own — that's the whole job of `AnimatePresence`.

```tsx
<AnimatePresence>
  {open && (
    <motion.div
      key="panel"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
    />
  )}
</AnimatePresence>
```

It fails silently in two situations, both of which look like "exit doesn't work":

1. **The child has no stable `key`.** Presence is tracked by key; without one
   there's nothing to tell "left" from "changed".
2. **The animating element isn't a direct child.** A wrapper `<div>` or a
   component that doesn't forward the props to a `motion` element hides it.

For route/page transitions use `mode="wait"` so the outgoing screen finishes
before the incoming one starts — otherwise both are on screen and the page
jumps.

### Variants for anything with more than one moving part

Variants let a parent drive its children by name, so staggering a list is a
property of the container rather than a hand-computed `delay` on each item —
which matters because the hand-computed version breaks the moment the list
length changes.

```tsx
const list = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0 },
}

<motion.ul variants={list} initial="hidden" animate="shown">
  {rows.map((r) => <motion.li key={r.id} variants={item} />)}
</motion.ul>
```

Hoist shared variants to module scope — they're reusable config, not per-render
state.

### Prefer the built-in gesture and viewport props

`whileHover`, `whileTap`, `whileFocus`, `whileDrag` and `whileInView` replace
hover state, `onMouseEnter` handlers, and IntersectionObserver boilerplate.
`whileInView` with `viewport={{ once: true }}` is the whole of a scroll reveal.

For shared-element transitions (a card expanding into a detail view), give both
elements the same `layoutId` rather than measuring and animating positions
yourself.

### Watch the bundle

`motion` pulls in the full feature set. On a bundle you care about, `LazyMotion`
with the lighter `m` component loads features on demand:

```tsx
import { LazyMotion, domAnimation, m } from 'framer-motion'

<LazyMotion features={domAnimation}>
  <m.div animate={{ opacity: 1 }} />
</LazyMotion>
```

`domAnimation` covers animation and gestures; `domMax` adds layout and drag.
Inside a `LazyMotion` tree use `m.*`, not `motion.*` — mixing them defeats the
point by pulling the full bundle back in. Check the build output rather than
assuming the win.

### Next.js App Router

Motion components use hooks and context, so any file with them needs
`'use client'` at the top. A server component rendering `motion.div` fails at
build.

## Choosing a transition

Springs feel right for anything the user is driving — drags, toggles, gestures —
because they carry momentum and can be interrupted mid-flight:

```tsx
transition={{ type: 'spring', stiffness: 400, damping: 30 }}
```

Duration-based easing suits things that just need to appear or leave. Keep UI
feedback short — roughly 150–250ms; much beyond that and the interface feels
like it's lagging rather than animating. These are starting points, not rules;
match whatever the project already uses.

## When not to reach for it

A skill that gets used indiscriminately stops being useful. A one-off hover
colour change, a spinner, or a simple fade is a two-line CSS `transition` with
no runtime cost — don't add a component tree for it. Reach for framer-motion
when there's exit animation, layout change, orchestration across elements, or
gesture involvement, which is where CSS starts requiring timers and manual
class management.

Also: fit the project's conventions. If there's a design system with animation
tokens or existing durations and easings, use those values rather than inventing
new ones — inconsistent motion reads as sloppier than no motion.
