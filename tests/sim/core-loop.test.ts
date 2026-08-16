import { describe, expect, it } from 'vitest';
import {
  debugSpawnOrbiters,
  plantDyson,
  plantTree,
  sendSeedlings,
} from '../../src/game/sim/commands';
import {
  canReach,
  isGraphConnected,
  shortestPath,
} from '../../src/game/sim/graph';
import { createCoreLoopWorld } from '../../src/game/sim/layout';
import { rockRadiusAt } from '../../src/game/sim/rock';
import {
  ENERGY_TREE_MIN_ENERGY,
  LOCAL_SEEDLING_CAP,
  PLANT_COST,
  mineralsToSlots,
} from '../../src/game/sim/types';
import {
  addAsteroid,
  countOrbitingKind,
  countOrbitingSeedlings,
  createEmptyWorld,
  createSandboxWorld,
  slotPosition,
  tick,
} from '../../src/game/sim/world';

describe('graph', () => {
  it('links asteroids within outbound travel radius', () => {
    const world = createEmptyWorld(1);
    const a = addAsteroid(world, { x: 0, y: 0, travelRadius: 200 });
    const b = addAsteroid(world, { x: 150, y: 0, travelRadius: 50 });
    expect(canReach(a, b)).toBe(true);
    expect(canReach(b, a)).toBe(false);
  });

  it('finds a multi-hop BFS path', () => {
    const world = createEmptyWorld(2);
    const a = addAsteroid(world, { x: 0, y: 0, travelRadius: 120 });
    const mid = addAsteroid(world, { x: 100, y: 0, travelRadius: 120 });
    const b = addAsteroid(world, { x: 200, y: 0, travelRadius: 120 });
    const path = shortestPath(world, a.id, b.id);
    expect(path).toEqual([a.id, mid.id, b.id]);
  });

  it('returns null when disconnected', () => {
    const world = createEmptyWorld(3);
    const a = addAsteroid(world, { x: 0, y: 0, travelRadius: 50 });
    const b = addAsteroid(world, { x: 500, y: 0, travelRadius: 50 });
    expect(shortestPath(world, a.id, b.id)).toBeNull();
  });

  it('builds a connected core-loop layout', () => {
    const world = createCoreLoopWorld(42);
    expect(world.asteroids.size).toBe(5);
    expect(isGraphConnected(world)).toBe(true);
    const home = [...world.asteroids.values()].find((a) => a.owner === 'player');
    expect(home).toBeTruthy();
    expect(world.trees.size).toBeGreaterThanOrEqual(1);
    const wild = [...world.asteroids.values()].find((a) => a.owner === 'grey');
    expect(wild).toBeTruthy();
    const enemy = [...world.asteroids.values()].find((a) => a.owner === 'enemy');
    expect(enemy).toBeTruthy();
  });

  it('maps minerals to tree slots', () => {
    expect(mineralsToSlots(20)).toBe(2);
    expect(mineralsToSlots(74)).toBeGreaterThanOrEqual(4);
    expect(mineralsToSlots(200)).toBe(6);
  });
});

describe('send', () => {
  it('moves seedlings to destination orbit along a path', () => {
    const world = createEmptyWorld(10);
    const a = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'player',
    });
    const b = addAsteroid(world, { x: 200, y: 0, travelRadius: 300 });
    debugSpawnOrbiters(world, a.id, 'player', 5);

    const result = sendSeedlings(world, a.id, b.id, 3, 'player');
    expect(result.ok).toBe(true);
    expect(countOrbitingSeedlings(world, a.id, 'player')).toBe(2);

    for (let i = 0; i < 60 * 10; i++) tick(world, 1 / 60);

    expect(countOrbitingSeedlings(world, b.id, 'player')).toBe(3);
    expect(countOrbitingSeedlings(world, a.id, 'player')).toBe(2);
  });

  it('fails with no path or over-send clamps to available', () => {
    const world = createEmptyWorld(11);
    const a = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 40,
      owner: 'player',
    });
    const b = addAsteroid(world, { x: 400, y: 0, travelRadius: 40 });
    debugSpawnOrbiters(world, a.id, 'player', 2);
    expect(sendSeedlings(world, a.id, b.id, 1, 'player').ok).toBe(false);

    const c = addAsteroid(world, { x: 100, y: 0, travelRadius: 200 });
    a.travelRadius = 200;
    c.travelRadius = 200;
    const result = sendSeedlings(world, a.id, c.id, 99, 'player');
    expect(result).toEqual({ ok: true, count: 2 });
  });
});

describe('plant', () => {
  it('spends 10 seedlings, creates a tree, and claims neutral', () => {
    const world = createEmptyWorld(20);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'neutral',
    });
    debugSpawnOrbiters(world, rock.id, 'player', 12);

    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(true);
    for (let i = 0; i < 60 * 8 && world.pendingPlants.size > 0; i++) {
      tick(world, 1 / 60);
    }

    expect(world.trees.size).toBe(1);
    expect(world.asteroids.get(rock.id)!.owner).toBe('player');
    expect(world.pendingPlants.size).toBe(0);
    expect(countOrbitingSeedlings(world, rock.id, 'player')).toBeGreaterThanOrEqual(2);
  });

  it('skims the crust then dips at the slot instead of cutting through', () => {
    const world = createEmptyWorld(24);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'player',
    });
    debugSpawnOrbiters(world, rock.id, 'player', 12);
    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(true);
    const slot = slotPosition(rock, 0);
    const slotAngle = slot.angle;
    for (let i = 0; i < 60 * 10 && world.pendingPlants.size > 0; i++) {
      tick(world, 1 / 60);
      for (const s of world.seedlings.values()) {
        if (s.state !== 'plant' || (s.wait ?? 0) > 0) continue;
        const dist = Math.hypot(s.x - rock.x, s.y - rock.y);
        const ang = Math.atan2(s.y - rock.y, s.x - rock.x);
        let err = ang - slotAngle;
        while (err > Math.PI) err -= Math.PI * 2;
        while (err < -Math.PI) err += Math.PI * 2;
        if (Math.abs(err) > 0.28) {
          expect(dist).toBeGreaterThan(rockRadiusAt(rock, ang) - 2);
        }
      }
    }
    expect(world.trees.size).toBe(1);
    expect(world.pendingPlants.size).toBe(0);
  });

  it('fails below 10 or on occupied slot', () => {
    const world = createEmptyWorld(21);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'player',
    });
    debugSpawnOrbiters(world, rock.id, 'player', 5);
    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(false);

    debugSpawnOrbiters(world, rock.id, 'player', 10);
    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(true);
    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(false);
    expect(PLANT_COST).toBe(10);
  });

  it('refuses Energy trees on low-energy rocks', () => {
    const world = createEmptyWorld(22);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'player',
      stats: { energy: ENERGY_TREE_MIN_ENERGY - 10, strength: 40, speed: 40 },
    });
    debugSpawnOrbiters(world, rock.id, 'player', 12);
    expect(plantTree(world, rock.id, 0, 'player', 'energy').ok).toBe(false);
    rock.stats.energy = ENERGY_TREE_MIN_ENERGY;
    expect(plantTree(world, rock.id, 0, 'player', 'energy').ok).toBe(true);
  });

  it('plants at a chosen crust angle', () => {
    const world = createEmptyWorld(25);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'player',
    });
    debugSpawnOrbiters(world, rock.id, 'player', 12);
    const angle = 0.85;
    expect(plantTree(world, rock.id, 0, 'player', 'dyson', angle).ok).toBe(
      true,
    );
    const pending = [...world.pendingPlants.values()][0]!;
    expect(pending.plantAngle).toBe(angle);
    const target = slotPosition(rock, 0, angle);
    for (const s of world.seedlings.values()) {
      if (s.state !== 'plant') continue;
      expect(s.plantTargetX).toBeCloseTo(target.x, 5);
      expect(s.plantTargetY).toBeCloseTo(target.y, 5);
    }
    for (let i = 0; i < 60 * 8 && world.pendingPlants.size > 0; i++) {
      tick(world, 1 / 60);
    }
    const tree = [...world.trees.values()][0]!;
    expect(tree.plantAngle).toBe(angle);
  });

  it('rejects a crust plant too close to another tree', () => {
    const world = createEmptyWorld(26);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'player',
      treeSlots: 4,
    });
    debugSpawnOrbiters(world, rock.id, 'player', 24);
    expect(plantTree(world, rock.id, 0, 'player', 'dyson', 0).ok).toBe(true);
    expect(plantTree(world, rock.id, 1, 'player', 'dyson', 0.05).ok).toBe(
      false,
    );
  });

  it('blocks planting while wild defenders remain', () => {
    const world = createEmptyWorld(23);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'grey',
    });
    debugSpawnOrbiters(world, rock.id, 'grey', 4);
    debugSpawnOrbiters(world, rock.id, 'player', 12);
    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(false);
  });
});

describe('production cap with travelers', () => {
  it('ignores traveling seedlings when applying the local cap', () => {
    const world = createSandboxWorld(77);
    const home = [...world.asteroids.values()][0]!;
    home.travelRadius = 500;

    for (let i = 0; i < 60 * 80; i++) tick(world, 1 / 60);
    expect(countOrbitingSeedlings(world, home.id)).toBe(LOCAL_SEEDLING_CAP);

    const other = addAsteroid(world, {
      x: 200,
      y: 0,
      travelRadius: 500,
    });
    const sent = sendSeedlings(world, home.id, other.id, 15, 'player');
    expect(sent.ok).toBe(true);
    expect(countOrbitingSeedlings(world, home.id)).toBe(
      LOCAL_SEEDLING_CAP - 15,
    );

    for (let i = 0; i < 60 * 40; i++) tick(world, 1 / 60);
    expect(countOrbitingSeedlings(world, home.id)).toBe(LOCAL_SEEDLING_CAP);
  });
});

describe('energy trees', () => {
  it('spawns Sentinels from an Energy tree', () => {
    const world = createEmptyWorld(30);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'player',
      minerals: 80,
      stats: { energy: 140, strength: 60, speed: 60 },
    });
    world.trees.set(1, {
      id: 1,
      asteroidId: rock.id,
      slotIndex: 0,
      kind: 'energy',
      seed: 1,
      maturity: 1,
      faction: 'player',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    world.nextId = 2;
    for (let i = 0; i < 60 * 20; i++) tick(world, 1 / 60);
    expect(countOrbitingKind(world, rock.id, 'player', 'sentinel')).toBeGreaterThan(0);
  });
});
