/**
 * Colonization along the crust of a cross-section.
 * `angleDelta` is the shortest arc from the tree, 0..π.
 *
 * Grass lags the tree: a young plant keeps a grove at the scar; pollen
 * creeps the sward outward over the whole growth, never jumping to a ring.
 */

/** Angular reach (radians) of the grass front from the planting scar. */
export function lifeReach(maturity: number): number {
  const m = Math.min(1, Math.max(0, maturity));
  const delayed = Math.max(0, (m - 0.22) / 0.78);
  const ease = Math.pow(delayed, 4.8);
  return 0.12 + 0.9 * ease;
}

export function lifeSpread(
  maturity: number,
  angleDelta: number,
  jitter = 0.5,
): number {
  const j = Math.min(1, Math.max(0, jitter));
  const delta = Math.min(Math.PI, Math.max(0, angleDelta));
  const reach = lifeReach(maturity);
  const edge = 0.22 + j * 0.3;
  const warped = delta * (0.88 + j * 0.24);
  return smoothstep(0, 1, (reach - warped) / Math.max(1e-4, edge));
}

/** Origin grove at the scar — lush before the rest of the rim greens. */
export function groveSpread(maturity: number, jitter = 0.5): number {
  const m = Math.min(1, Math.max(0, maturity));
  const j = Math.min(1, Math.max(0, jitter));
  return smoothstep(0.02, 0.34, m) * (1 - j * 0.22);
}

/**
 * How close a crust point sits to the life origin (1 at the scar).
 * Used to scale blade height / density — independent of colonization reach.
 */
export function lifeProximity(angleDelta: number): number {
  const delta = Math.min(Math.PI, Math.max(0, angleDelta));
  return Math.pow(1 - smoothstep(0, 0.95, delta), 1.75);
}

/** Length/width scale from proximity: tall at origin, stubby far away. */
export function lifeLushScale(proximity: number): number {
  const p = Math.min(1, Math.max(0, proximity));
  return 0.1 + 1.7 * Math.pow(p, 1.55);
}

/**
 * Fraction of potential blades that should show.
 * Near the tree almost every bit draws; the far rim stays thin.
 */
export function lifeDensity(proximity: number, grow: number): number {
  const p = Math.min(1, Math.max(0, proximity));
  const g = Math.min(1, Math.max(0, grow));
  return g * (0.52 + 0.48 * Math.pow(p, 0.55));
}

export function shortestAngle(from: number, to: number): number {
  let d = to - from;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  if (edge1 <= edge0) return x >= edge1 ? 1 : 0;
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
