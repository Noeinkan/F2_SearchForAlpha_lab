/** Pure send-count helpers — no DOM / Pixi. */

export type SendMode = 'all' | 'scout' | 'fixed';

/**
 * Resolve how many seedlings to send given orbiters available and mode.
 * - all: send every ready orbiter
 * - scout: send at most 1
 * - fixed: keep the chosen count, clamped to [0, max] (or [1, max] when max > 0 and count was > 0)
 */
export function resolveSendCount(
  max: number,
  mode: SendMode,
  fixedCount: number,
): number {
  if (max < 1) return 0;
  if (mode === 'scout') return 1;
  if (mode === 'all') return max;
  return Math.min(max, Math.max(0, fixedCount | 0));
}

/** Bump a fixed send count by delta, clamped to orbiters. Sets mode to fixed. */
export function bumpSendCount(
  max: number,
  current: number,
  delta: number,
): number {
  if (max < 1) return 0;
  return Math.min(max, Math.max(1, current + delta));
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
