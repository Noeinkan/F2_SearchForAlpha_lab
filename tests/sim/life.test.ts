import { describe, expect, it } from 'vitest';
import {
  groveSpread,
  lifeDensity,
  lifeLushScale,
  lifeProximity,
  lifeReach,
  lifeSpread,
} from '../../src/game/sim/life';

describe('life spread', () => {
  it('stays a grove at the scar while the tree is young', () => {
    expect(lifeSpread(0.12, 0.05, 0.2)).toBeGreaterThan(0.1);
    expect(lifeSpread(0.12, 1.2, 0.4)).toBe(0);
    expect(groveSpread(0.2, 0.1)).toBeGreaterThan(0.3);
    expect(groveSpread(0.01, 0.1)).toBe(0);
  });

  it('creeps outward slowly instead of ringing the far side', () => {
    const far = Math.PI * 0.92;
    expect(lifeSpread(0.45, far, 0.3)).toBe(0);
    expect(lifeSpread(1, far, 0.3)).toBe(0);
    expect(lifeSpread(0.5, 0.8, 0.3)).toBe(0);
    expect(lifeSpread(0.5, 0.25, 0.3)).toBe(0);
    expect(lifeSpread(1, 0.8, 0.3)).toBeGreaterThan(0.15);
    expect(lifeSpread(0.9, 0.22, 0.3)).toBeGreaterThan(
      lifeSpread(0.45, 0.22, 0.3),
    );
  });

  it('keeps reach near the scar until the tree is well grown', () => {
    expect(lifeReach(0.12)).toBeLessThan(0.16);
    expect(lifeReach(0.5)).toBeLessThan(0.18);
    expect(lifeReach(0.75)).toBeLessThan(0.35);
    expect(lifeReach(1)).toBeGreaterThan(0.85);
    expect(lifeReach(1)).toBeLessThan(Math.PI);
  });
});

describe('life proximity', () => {
  it('is strongest at the scar and falls off along the rim', () => {
    expect(lifeProximity(0)).toBeCloseTo(1, 5);
    expect(lifeProximity(0.08)).toBeGreaterThan(0.8);
    expect(lifeProximity(0.55)).toBeGreaterThan(0.15);
    expect(lifeProximity(0.55)).toBeLessThan(lifeProximity(0.08));
    expect(lifeProximity(Math.PI)).toBeCloseTo(0, 5);
  });

  it('scales blade lushness taller near the origin', () => {
    expect(lifeLushScale(1)).toBeGreaterThan(lifeLushScale(0.4));
    expect(lifeLushScale(0.4)).toBeGreaterThan(lifeLushScale(0));
    expect(lifeLushScale(0)).toBeCloseTo(0.1, 5);
    expect(lifeLushScale(1)).toBeCloseTo(1.8, 5);
  });

  it('keeps a continuous sward, thicker near the origin', () => {
    expect(lifeDensity(1, 1)).toBeGreaterThan(0.9);
    expect(lifeDensity(0.25, 1)).toBeLessThan(lifeDensity(0.8, 1));
    expect(lifeDensity(0.5, 1)).toBeGreaterThan(0.6);
    expect(lifeDensity(0.2, 0.4)).toBeLessThan(0.4);
  });
});
