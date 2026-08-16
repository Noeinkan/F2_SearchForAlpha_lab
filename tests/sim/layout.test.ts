import { describe, expect, it } from 'vitest';
import { isGraphConnected } from '../../src/game/sim/graph';
import {
  createCoreLoopWorld,
  createSkirmishWorld,
  mstDegree,
} from '../../src/game/sim/layout';
import { ENERGY_TREE_MIN_ENERGY, HOME_RADIUS_SCALE, ROCK_GAP, ROCK_RADIUS_MAX, ROCK_RADIUS_MIN } from '../../src/game/sim/types';

describe('createSkirmishWorld', () => {
  it('builds a connected 12–25 rock layout with roles', () => {
    const world = createSkirmishWorld(0xabc12345);
    expect(world.asteroids.size).toBeGreaterThanOrEqual(12);
    expect(world.asteroids.size).toBeLessThanOrEqual(25);
    expect(isGraphConnected(world)).toBe(true);

    const home = [...world.asteroids.values()].find((a) => a.owner === 'player');
    expect(home).toBeTruthy();
    expect(mstDegree(world, home!.id)).toBe(1);

    const enemy = [...world.asteroids.values()].filter((a) => a.owner === 'enemy');
    expect(enemy.length).toBeGreaterThanOrEqual(1);
    expect(world.aiHomeId).not.toBeNull();
    expect(world.asteroids.get(world.aiHomeId!)?.owner).toBe('enemy');

    const energyCapable = [...world.asteroids.values()].filter(
      (a) =>
        a.owner !== 'player' &&
        a.owner !== 'enemy' &&
        a.stats.energy >= ENERGY_TREE_MIN_ENERGY,
    );
    expect(energyCapable.length).toBeGreaterThanOrEqual(1);
  });

  it('mixes rock sizes and keeps discs from overlapping', () => {
    let widest = 0;
    for (const seed of [1, 42, 0xabc12345]) {
      const world = createSkirmishWorld(seed);
      const rocks = [...world.asteroids.values()];
      const radii = rocks.map((a) => a.radius);
      const minR = Math.min(...radii);
      const maxR = Math.max(...radii);
      const home = rocks.find((a) => a.owner === 'player')!;
      expect(minR).toBeGreaterThanOrEqual(ROCK_RADIUS_MIN);
      expect(home.radius / HOME_RADIUS_SCALE).toBeLessThanOrEqual(ROCK_RADIUS_MAX + 0.01);
      expect(home.radius / HOME_RADIUS_SCALE).toBeGreaterThanOrEqual(ROCK_RADIUS_MIN);
      for (const a of rocks) {
        if (a.id === home.id) {
          expect(a.radius).toBeLessThanOrEqual(ROCK_RADIUS_MAX * HOME_RADIUS_SCALE + 0.01);
        } else {
          expect(a.radius).toBeLessThanOrEqual(ROCK_RADIUS_MAX);
        }
      }
      widest = Math.max(widest, maxR - minR);
      for (let i = 0; i < rocks.length; i++) {
        for (let j = i + 1; j < rocks.length; j++) {
          const a = rocks[i]!;
          const b = rocks[j]!;
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          expect(d).toBeGreaterThanOrEqual(a.radius + b.radius + ROCK_GAP - 0.01);
        }
      }
    }
    expect(widest).toBeGreaterThan(40);
  });

  it('spreads sizes continuously instead of a few bands', () => {
    const radii: number[] = [];
    for (const seed of [7, 99, 0xabc12345, 0x11111111]) {
      radii.push(
        ...[...createSkirmishWorld(seed).asteroids.values()].map((a) => a.radius),
      );
    }
    expect(radii.some((r) => r > 110 && r < 122)).toBe(true);
    expect(radii.some((r) => r > 148 && r < 160)).toBe(true);
  });

  it('varies layout across seeds', () => {
    const a = createSkirmishWorld(111);
    const b = createSkirmishWorld(999_001);
    const coords = (w: typeof a) =>
      [...w.asteroids.values()]
        .map((r) => `${Math.round(r.x)},${Math.round(r.y)}`)
        .sort()
        .join('|');
    const sameCount = a.asteroids.size === b.asteroids.size;
    const sameCoords = coords(a) === coords(b);
    expect(sameCount && sameCoords).toBe(false);
  });

  it('places player home on an MST leaf for several seeds', () => {
    for (const seed of [1, 42, 0xc0a1f00d, 0x55aa55aa]) {
      const world = createSkirmishWorld(seed);
      const home = [...world.asteroids.values()].find((a) => a.owner === 'player')!;
      expect(mstDegree(world, home.id)).toBe(1);
    }
  });
});

describe('createCoreLoopWorld fixture', () => {
  it('still builds the 5-rock test bed', () => {
    const world = createCoreLoopWorld(42);
    expect(world.asteroids.size).toBe(5);
    expect(isGraphConnected(world)).toBe(true);
  });
});
