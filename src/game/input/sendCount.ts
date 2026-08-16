/** Pure send-count helpers — no DOM / Pixi. */

export type SendMode = 'all' | 'scout' | 'half' | 'fixed';

/**
 * Resolve how many seedlings to send given orbiters available and mode.
 * - all: send every ready orbiter
 * - scout: send at most 1
 * - half: send roughly half of the ready orbiters (rounded up, at least 1)
 * - fixed: keep the chosen count, clamped to [0, max]
 */
export function resolveSendCount(
  max: number,
  mode: SendMode,
  fixedCount: number,
): number {
  if (max < 1) return 0;
  if (mode === 'scout') return 1;
  if (mode === 'all') return max;
  if (mode === 'half') return Math.max(1, Math.ceil(max / 2));
  return Math.min(max, Math.max(0, fixedCount | 0));
}

/**
 * Clamp a desired exact count to the available orbiters (no mode switching).
 * Returns 0 when no orbiters are available.
 */
export function resolveSendExact(max: number, exact: number): number {
  if (max < 1) return 0;
  return Math.min(max, Math.max(0, exact | 0));
}

/**
 * Bump an exact count by delta, clamped to [0, max]. Used by the slider/+/-
 * controls while the player is fine-tuning a number.
 */
export function adjustSendCount(max: number, current: number, delta: number): number {
  if (max < 1) return 0;
  const next = (current | 0) + (delta | 0);
  return Math.min(max, Math.max(0, next));
}

/**
 * Bump a fixed send count by delta, clamped to [1, max] (or 0 when max < 1).
 * Convenience wrapper around `adjustSendCount` for the legacy -/+ stepper.
 */
export function bumpSendCount(
  max: number,
  current: number,
  delta: number,
): number {
  if (max < 1) return 0;
  const next = Math.min(max, Math.max(1, current + delta));
  return next;
}

/**
 * Snap to the nearest preset for a given amount. Used by the dock to keep the
 * preset chips (`Scout`, `Half`, `All`) in sync with the displayed count.
 */
export function closestPreset(
  max: number,
  count: number,
): 'scout' | 'half' | 'all' | 'fixed' {
  if (max < 1 || count <= 0) return 'fixed';
  if (count >= max) return 'all';
  if (count === 1) return 'scout';
  const half = Math.max(1, Math.ceil(max / 2));
  if (count === half) return 'half';
  return 'fixed';
}

export function isCoarsePointer(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    if (window.matchMedia('(pointer: coarse)').matches) return true;
  } catch {
    /* ignore */
  }
  return 'ontouchstart' in window;
}
