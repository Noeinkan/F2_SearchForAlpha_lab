/** Pure edge-scroll axes — no DOM / Pixi. */

/** Hot zone thickness in canvas pixels (RTS-style). */
export const EDGE_MARGIN = 24;

/**
 * How far outside the canvas (px) the cursor may still count as on an edge.
 * Stops scroll once the pointer is clearly off the view.
 */
export const EDGE_OUTSIDE_SLACK = 8;

/**
 * Screen-space pan axes matching WASD in `cameraControls`:
 * +dx pans the view left, +dy pans the view up.
 * Components are in [-1, 1] with a concave falloff across the margin
 * (full speed at the pixel edge, still useful halfway in).
 */
export const EDGE_FALLOFF = 0.55;

export function edgeScrollAxes(
  sx: number,
  sy: number,
  width: number,
  height: number,
  margin: number = EDGE_MARGIN,
  outsideSlack: number = EDGE_OUTSIDE_SLACK,
): { dx: number; dy: number } {
  if (width <= 0 || height <= 0 || margin <= 0) return { dx: 0, dy: 0 };

  const tooFarLeft = sx < -outsideSlack;
  const tooFarRight = sx > width + outsideSlack;
  const tooFarTop = sy < -outsideSlack;
  const tooFarBottom = sy > height + outsideSlack;
  if (tooFarLeft || tooFarRight || tooFarTop || tooFarBottom) {
    return { dx: 0, dy: 0 };
  }

  return {
    dx: axisToward(sx, width, margin),
    dy: axisToward(sy, height, margin),
  };
}

function axisToward(pos: number, size: number, margin: number): number {
  if (pos <= margin) {
    const u = Math.min(1, Math.max(0, (margin - pos) / margin));
    return u === 0 ? 0 : u ** EDGE_FALLOFF;
  }
  if (pos >= size - margin) {
    const u = Math.min(1, Math.max(0, (pos - (size - margin)) / margin));
    return u === 0 ? 0 : -(u ** EDGE_FALLOFF);
  }
  return 0;
}
