import { describe, expect, it } from 'vitest';
import { wheelZoomFactor } from '../../src/game/input/wheelZoom';

describe('wheelZoomFactor', () => {
  it('returns 1 when delta is 0', () => {
    expect(wheelZoomFactor(0)).toBe(1);
    expect(wheelZoomFactor(0, 1)).toBe(1);
  });

  it('zooms in for negative pixel deltas and out for positive', () => {
    expect(wheelZoomFactor(-100)).toBeGreaterThan(1);
    expect(wheelZoomFactor(100)).toBeLessThan(1);
  });

  it('scales with magnitude so trackpad ticks stay small', () => {
    const tap = wheelZoomFactor(8);
    const notch = wheelZoomFactor(100);
    expect(Math.abs(1 - tap)).toBeLessThan(Math.abs(1 - notch));
    expect(tap).toBeGreaterThan(0.97);
    expect(tap).toBeLessThan(1);
  });

  it('treats line mode as larger than a raw pixel of the same number', () => {
    expect(Math.abs(1 - wheelZoomFactor(3, 1))).toBeGreaterThan(
      Math.abs(1 - wheelZoomFactor(3, 0)),
    );
  });
});
