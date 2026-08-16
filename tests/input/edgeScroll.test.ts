import { describe, expect, it } from 'vitest';
import {
  EDGE_MARGIN,
  EDGE_OUTSIDE_SLACK,
  edgeScrollAxes,
} from '../../src/game/input/edgeScroll';

const W = 800;
const H = 600;

describe('edgeScrollAxes', () => {
  it('returns zero in the center', () => {
    expect(edgeScrollAxes(W / 2, H / 2, W, H)).toEqual({ dx: 0, dy: 0 });
  });

  it('pans toward each of the four edges (WASD signs)', () => {
    expect(edgeScrollAxes(0, H / 2, W, H)).toEqual({ dx: 1, dy: 0 });
    expect(edgeScrollAxes(W, H / 2, W, H)).toEqual({ dx: -1, dy: 0 });
    expect(edgeScrollAxes(W / 2, 0, W, H)).toEqual({ dx: 0, dy: 1 });
    expect(edgeScrollAxes(W / 2, H, W, H)).toEqual({ dx: 0, dy: -1 });
  });

  it('combines axes in corners', () => {
    expect(edgeScrollAxes(0, 0, W, H)).toEqual({ dx: 1, dy: 1 });
    expect(edgeScrollAxes(W, 0, W, H)).toEqual({ dx: -1, dy: 1 });
    expect(edgeScrollAxes(0, H, W, H)).toEqual({ dx: 1, dy: -1 });
    expect(edgeScrollAxes(W, H, W, H)).toEqual({ dx: -1, dy: -1 });
  });

  it('falls off across the margin band', () => {
    expect(edgeScrollAxes(EDGE_MARGIN, H / 2, W, H)).toEqual({
      dx: 0,
      dy: 0,
    });
    expect(edgeScrollAxes(EDGE_MARGIN + 1, H / 2, W, H)).toEqual({
      dx: 0,
      dy: 0,
    });
    expect(edgeScrollAxes(EDGE_MARGIN / 2, H / 2, W, H).dx).toBeCloseTo(
      0.5 ** 0.55,
    );
    expect(edgeScrollAxes(W - EDGE_MARGIN / 2, H / 2, W, H).dx).toBeCloseTo(
      -(0.5 ** 0.55),
    );
  });

  it('keeps scrolling slightly outside the canvas (slack)', () => {
    expect(edgeScrollAxes(-EDGE_OUTSIDE_SLACK, H / 2, W, H)).toEqual({
      dx: 1,
      dy: 0,
    });
    expect(edgeScrollAxes(W + EDGE_OUTSIDE_SLACK, H / 2, W, H)).toEqual({
      dx: -1,
      dy: 0,
    });
  });

  it('stops when too far outside the viewport', () => {
    expect(
      edgeScrollAxes(-EDGE_OUTSIDE_SLACK - 1, H / 2, W, H),
    ).toEqual({ dx: 0, dy: 0 });
    expect(
      edgeScrollAxes(W + EDGE_OUTSIDE_SLACK + 1, H / 2, W, H),
    ).toEqual({ dx: 0, dy: 0 });
    expect(
      edgeScrollAxes(W / 2, -EDGE_OUTSIDE_SLACK - 1, W, H),
    ).toEqual({ dx: 0, dy: 0 });
    expect(
      edgeScrollAxes(W / 2, H + EDGE_OUTSIDE_SLACK + 1, W, H),
    ).toEqual({ dx: 0, dy: 0 });
  });

  it('returns zero when margin is 0 or size is invalid', () => {
    expect(edgeScrollAxes(0, 0, W, H, 0)).toEqual({ dx: 0, dy: 0 });
    expect(edgeScrollAxes(0, 0, 0, H)).toEqual({ dx: 0, dy: 0 });
    expect(edgeScrollAxes(0, 0, W, 0)).toEqual({ dx: 0, dy: 0 });
  });
});
