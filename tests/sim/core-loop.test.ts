import { describe, expect, it } from 'vitest';
import {
  debugSpawnOrbiters,
  plantDyson,
  sendSeedlings,
} from '../../src/game/sim/commands';
import {
  canReach,
  isGraphConnected,
  shortestPath,
} from '../../src/game/sim/graph';
import { createCoreLoopWorld } from '../../src/game/sim/layout';
import {
  LOCAL_SEEDLING_CAP,
  PLANT_COST,
  type Asteroid,
  type World,
} from '../../src/game/sim/types';
import {
  allocId,
  countOrbitingSeedlings,
  createEmptyWorld,
  createSandboxWorld,
  tick,
} from '../../src/game/sim/world';

function addAsteroid(
  world: World,
  partial: Partial<Asteroid> & Pick<Asteroid, 'x' | 'y' | 'travelRadius'>,
): Asteroid {
  const id = allocId(world);
  const a: Asteroid = {
    id,
    name: `A${id}`,
    radius: 60,
    treeSlots: 4,
    stats: { energy: 50, strength: 50, speed: 80 },
    owner: 'neutral',
    seed: id,
    coreEnergy: 100,
    maxCoreEnergy: 100,
    ...partial,
  };
  world.asteroids.set(id, a);
  return a;
}

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
    expect(world.trees.size).toBe(1);
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
});

describe('production cap with travelers', () => {
  it('ignores traveling seedlings when applying the local cap', () => {
    const world = createSandboxWorld(77);
    const home = [...world.asteroids.values()][0]!;
    home.travelRadius = 500;

    // Grow until near cap
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
