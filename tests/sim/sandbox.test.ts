import { describe, expect, it } from 'vitest';
import {
  buildAdultTree,
  buildLSystemSegments,
  buildTree,
  maturityStep,
  measureRootFeed,
  rootFeedActive,
  spawnReadiness,
} from '../../src/game/sim/lsystem';
import { mulberry32, range } from '../../src/game/sim/rng';
import {
  DYSON_GROWTH_SECONDS,
  LOCAL_SEEDLING_CAP,
  ROOT_FEED_REGEN,
  ROOT_FEED_SPAWN_BONUS,
  SPAWN_START_MATURITY,
  orbitBand,
} from '../../src/game/sim/types';
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

  it('grows neuron roots from the collar toward the core', () => {
    const surfaceY = -15;
    const coreY = 70;
    const geom = buildTree(99, 1, 1, coreY, surfaceY);
    expect(geom.roots.length).toBeGreaterThan(5);
    expect(geom.strokes.some((s) => s.kind === 'wood')).toBe(true);
    const nearSurface = (pts: { x: number; y: number }[]) =>
      pts.some((p) => Math.abs(p.y - surfaceY) < 14 && Math.abs(p.x) < 22);
    expect(geom.roots.some((r) => nearSurface(r.points))).toBe(true);
    expect(
      geom.strokes.some((s) => s.kind === 'wood' && nearSurface(s.points)),
    ).toBe(true);
    expect(Math.abs(geom.collar.y - surfaceY)).toBeLessThan(8);

    let bestTip = Infinity;
    let collarStarts = 0;
    for (const r of geom.roots) {
      const start = r.points[0]!;
      if (start.y < surfaceY + 18) collarStarts += 1;
      const tip = r.points[r.points.length - 1]!;
      bestTip = Math.min(bestTip, Math.hypot(tip.x, tip.y - coreY));
    }
    expect(collarStarts).toBeGreaterThan(2);
    expect(bestTip).toBeLessThan(coreY * 0.35);
  });

  it('extends the same adult plant instead of swapping shapes', () => {
    const len = (geom: ReturnType<typeof buildTree>) => {
      let n = 0;
      for (const s of [...geom.strokes, ...geom.roots]) {
        for (let i = 1; i < s.points.length; i++) {
          const a = s.points[i - 1]!;
          const b = s.points[i]!;
          n += Math.hypot(b.x - a.x, b.y - a.y);
        }
      }
      return n;
    };
    const sprout = buildTree(7, 0.12, 1, 70, 0);
    const young = buildTree(7, 0.35, 1, 70, 0);
    const mid = buildTree(7, 0.7, 1, 70, 0);
    const adult = buildTree(7, 1, 1, 70, 0);
    expect(sprout.roots.length).toBeGreaterThan(0);
    expect(len(sprout)).toBeLessThan(len(young));
    expect(len(young)).toBeLessThan(len(mid));
    expect(len(mid)).toBeLessThan(len(adult));
    expect(young.strokes.some((s) => s.kind === 'grass')).toBe(true);
    expect(adult.strokes.some((s) => s.kind === 'grass')).toBe(true);
    expect(adult.flowers.length).toBeGreaterThan(sprout.flowers.length);
  });

  it('measures deterministic core feed from adult roots', () => {
    const coreY = 70;
    const a = buildAdultTree(42, 1, coreY, -12);
    const b = buildAdultTree(42, 1, coreY, -12);
    const feedA = measureRootFeed(a, coreY);
    const feedB = measureRootFeed(b, coreY);
    expect(feedA).toBe(feedB);
    expect(feedA).toBeGreaterThan(0);
    expect(feedA).toBeLessThanOrEqual(1);
    expect(rootFeedActive(0, feedA)).toBe(0);
    expect(rootFeedActive(1, feedA)).toBeCloseTo(feedA, 5);
    expect(rootFeedActive(1, 1)).toBeCloseTo(1, 5);
    const spawnMulFull = 1 + ROOT_FEED_SPAWN_BONUS * rootFeedActive(1, 1);
    const spawnMulNone = 1 + ROOT_FEED_SPAWN_BONUS * rootFeedActive(0.1, 1);
    expect(spawnMulFull).toBeGreaterThan(spawnMulNone);
    expect(ROOT_FEED_REGEN * rootFeedActive(1, 1)).toBeCloseTo(
      ROOT_FEED_REGEN,
      5,
    );
    expect(ROOT_FEED_REGEN * rootFeedActive(0, 1)).toBe(0);
  });

  it('ramps spawn readiness only after side-branch tips', () => {
    expect(spawnReadiness(0, SPAWN_START_MATURITY)).toBe(0);
    expect(spawnReadiness(SPAWN_START_MATURITY - 0.01, SPAWN_START_MATURITY)).toBe(
      0,
    );
    expect(
      spawnReadiness(SPAWN_START_MATURITY, SPAWN_START_MATURITY),
    ).toBeCloseTo(0, 5);
    const mid = spawnReadiness(0.7, SPAWN_START_MATURITY);
    const adult = spawnReadiness(1, SPAWN_START_MATURITY);
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(adult);
    expect(adult).toBeCloseTo(1, 5);
  });
});

describe('world sandbox', () => {
  it('grows the dyson tree over time', () => {
    const world = createSandboxWorld(99);
    const treeId = [...world.trees.keys()][0]!;
    expect(world.trees.get(treeId)!.maturity).toBe(0);
    expect(world.trees.get(treeId)!.coreFeed).toBeGreaterThan(0);
    for (let i = 0; i < 60; i++) tick(world, 1 / 60);
    expect(world.trees.get(treeId)!.maturity).toBeGreaterThan(0.04);
    for (let i = 0; i < 60 * 25; i++) tick(world, 1 / 60);
    expect(world.trees.get(treeId)!.maturity).toBe(1);
  });

  it('does not drop seedlings until branches emerge', () => {
    const world = createSandboxWorld(201);
    const treeId = [...world.trees.keys()][0]!;
    const preGateSec = DYSON_GROWTH_SECONDS * SPAWN_START_MATURITY * 0.9;
    for (let i = 0; i < 60 * preGateSec; i++) tick(world, 1 / 60);
    expect(world.trees.get(treeId)!.maturity).toBeLessThan(SPAWN_START_MATURITY);
    expect(world.seedlings.size).toBe(0);
    expect(world.trees.get(treeId)!.spawnAccumulator).toBe(0);

    for (let i = 0; i < 60 * 14 && world.seedlings.size === 0; i++) {
      tick(world, 1 / 60);
    }
    expect(world.trees.get(treeId)!.maturity).toBeGreaterThanOrEqual(
      SPAWN_START_MATURITY,
    );
    expect(world.seedlings.size).toBeGreaterThan(0);
  });


  it('spawns faster when adult than just past the gate', () => {
    const juvenile = spawnReadiness(SPAWN_START_MATURITY + 0.05, SPAWN_START_MATURITY);
    const adult = spawnReadiness(1, SPAWN_START_MATURITY);
    expect(adult).toBeGreaterThan(juvenile * 2);
  });

  it('spawns seedlings and respects the local cap', () => {
    const world = createSandboxWorld(123);
    for (let i = 0; i < 60 * 90; i++) tick(world, 1 / 60);
    expect(world.seedlings.size).toBe(LOCAL_SEEDLING_CAP);
    const before = world.seedlings.size;
    for (let i = 0; i < 60 * 10; i++) tick(world, 1 / 60);
    expect(world.seedlings.size).toBe(before);
  });

  it('lets a sprout glide into orbit instead of staying on the tree', () => {
    const world = createSandboxWorld(77);
    let sprout = [...world.seedlings.values()].find((s) => s.state === 'sprout');
    for (let i = 0; i < 60 * 40 && !sprout; i++) {
      tick(world, 1 / 60);
      sprout = [...world.seedlings.values()].find((s) => s.state === 'sprout');
    }
    expect(sprout).toBeTruthy();
    const id = sprout!.id;
    const fromX = sprout!.sproutFromX ?? sprout!.x;
    const fromY = sprout!.sproutFromY ?? sprout!.y;
    for (let i = 0; i < 60 * 6; i++) tick(world, 1 / 60);
    const grown = world.seedlings.get(id);
    expect(grown).toBeTruthy();
    expect(grown!.state).toBe('orbit');
    expect(Math.hypot(grown!.x - fromX, grown!.y - fromY)).toBeGreaterThan(8);
  });

  it('keeps seedlings near the asteroid orbit band', () => {
    const world = createSandboxWorld(55);
    const asteroid = [...world.asteroids.values()][0]!;
    for (let i = 0; i < 60 * 30; i++) tick(world, 1 / 60);
    expect(world.seedlings.size).toBeGreaterThan(0);
    for (const s of world.seedlings.values()) {
      if (s.state !== 'orbit') continue;
      const dist = Math.hypot(s.x - asteroid.x, s.y - asteroid.y);
      expect(dist).toBeGreaterThan(asteroid.radius * 0.92);
      expect(dist).toBeLessThan(
        asteroid.radius + orbitBand(asteroid.radius) + 55,
      );
    }
  });
});
