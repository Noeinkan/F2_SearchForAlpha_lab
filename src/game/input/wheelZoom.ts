/**
 * Multiplicative zoom from a wheel event (1 = unchanged).
 * Pixel deltas (trackpads) stay small; line/page modes match mouse notches.
 */
export function wheelZoomFactor(deltaY: number, deltaMode = 0): number {
  let dy = deltaY;
  if (deltaMode === 1) dy *= 16;
  else if (deltaMode === 2) dy *= 400;
  dy = Math.max(-480, Math.min(480, dy));
  if (dy === 0) return 1;
  return Math.exp(-dy * 0.0014);
}
