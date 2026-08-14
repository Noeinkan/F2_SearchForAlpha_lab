import { describe, expect, it } from 'vitest';
import { buildLSystemSegments, maturityStep } from '../../src/game/sim/lsystem';
import { mulberry32, range } from '../../src/game/sim/rng';
import { LOCAL_SEEDLING_CAP } from '../../src/game/sim/types';
import { createSandboxWorld, tick } from '../../src/game/sim/world';

describe('rng', () => {
  it('is deterministic for the same seed', () => {
    const a = mulberry32(42);
    const b = mulberry32(42);
    const seqA = [a(), a(), a(), a(), a()];
    const seqB = [b(), b(), b(), b(), b()];
    expect(seqA).toEqual(seqB);
  });

  it('range stays within bounds', () => {
    const rng = mulberry32(7);
    for (let i = 0; i < 100; i++) {
      const v = range(rng, 10, 20);
      expect(v).toBeGreaterThanOrEqual(10);
      expect(v).toBeLessThan(20);
    }
  });
});

describe('lsystem', () => {
  it('produces segments and steps maturity', () => {
    const segs = buildLSystemSegments(12345, 0.8, 1);
    expect(segs.length).toBeGreaterThan(0);
    expect(maturityStep(0.0)).toBe(0);
    expect(maturityStep(0.049)).toBe(0);
    expect(maturityStep(0.05)).toBe(1);
    expect(maturityStep(1)).toBe(20);
  });
});

describe('world sandbox', () => {
  it('grows the dyson tree over time', () => {
    const world = createSandboxWorld(99);
    const treeId = [...world.trees.keys()][0]!;
    expect(world.trees.get(treeId)!.maturity).toBe(0);
    for (let i = 0; i < 60; i++) tick(world, 1 / 60);
    expect(world.trees.get(treeId)!.maturity).toBeGreaterThan(0.04);
    for (let i = 0; i < 60 * 25; i++) tick(world, 1 / 60);
    expect(world.trees.get(treeId)!.maturity).toBe(1);
  });

  it('spawns seedlings and respects the local cap of 40', () => {
    const world = createSandboxWorld(123);
    for (let i = 0; i < 60 * 90; i++) tick(world, 1 / 60);
    expect(world.seedlings.size).toBe(LOCAL_SEEDLING_CAP);
    const before = world.seedlings.size;
    for (let i = 0; i < 60 * 10; i++) tick(world, 1 / 60);
    expect(world.seedlings.size).toBe(before);
  });

  it('keeps seedlings near the asteroid orbit band', () => {
    const world = createSandboxWorld(55);
    const asteroid = [...world.asteroids.values()][0]!;
    for (let i = 0; i < 60 * 30; i++) tick(world, 1 / 60);
    expect(world.seedlings.size).toBeGreaterThan(0);
    for (const s of world.seedlings.values()) {
      if (s.state !== 'orbit') continue;
      const dist = Math.hypot(s.x - asteroid.x, s.y - asteroid.y);
      expect(dist).toBeGreaterThan(asteroid.radius);
      expect(dist).toBeLessThan(asteroid.radius + 50);
      expect(Math.abs(dist - s.orbitRadius)).toBeLessThan(0.001);
    }
  });
});
