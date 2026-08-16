import { describe, expect, it } from 'vitest';
import { debugSpawnOrbiters, plantDyson, sendSeedlings } from '../../src/game/sim/commands';
import { TREE_BURN_SECONDS } from '../../src/game/sim/types';
import {
  addAsteroid,
  allocId,
  countOrbitingSeedlings,
  createEmptyWorld,
  tick,
} from '../../src/game/sim/world';

function run(world: ReturnType<typeof createEmptyWorld>, seconds: number): void {
  const steps = Math.ceil(seconds * 60);
  for (let i = 0; i < steps; i++) tick(world, 1 / 60);
}

describe('combat', () => {
  it('lets a larger basic swarm beat a smaller one', () => {
    const world = createEmptyWorld(40);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'grey',
      stats: { energy: 50, strength: 50, speed: 50 },
    });
    debugSpawnOrbiters(world, rock.id, 'player', 14);
    debugSpawnOrbiters(world, rock.id, 'grey', 4);
    run(world, 8);
    expect(countOrbitingSeedlings(world, rock.id, 'player')).toBeGreaterThan(0);
    expect(countOrbitingSeedlings(world, rock.id, 'grey')).toBe(0);
  });

  it('lets equal-count Sentinels beat basics', () => {
    const world = createEmptyWorld(41);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'neutral',
      stats: { energy: 80, strength: 50, speed: 50 },
    });
    debugSpawnOrbiters(world, rock.id, 'player', 5, 'sentinel');
    debugSpawnOrbiters(world, rock.id, 'grey', 5, 'basic');
    run(world, 10);
    expect(countOrbitingSeedlings(world, rock.id, 'player')).toBeGreaterThan(0);
    expect(countOrbitingSeedlings(world, rock.id, 'grey')).toBe(0);
  });

  it('lets a mass of basics beat a handful of Sentinels', () => {
    const world = createEmptyWorld(42);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'neutral',
      stats: { energy: 80, strength: 50, speed: 50 },
    });
    debugSpawnOrbiters(world, rock.id, 'player', 22, 'basic');
    debugSpawnOrbiters(world, rock.id, 'grey', 4, 'sentinel');
    run(world, 12);
    expect(countOrbitingSeedlings(world, rock.id, 'player')).toBeGreaterThan(0);
    expect(countOrbitingSeedlings(world, rock.id, 'grey')).toBe(0);
  });

  it('does not fight when landing on an empty asteroid', () => {
    const world = createEmptyWorld(43);
    const a = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 400,
      owner: 'player',
    });
    const b = addAsteroid(world, { x: 180, y: 0, travelRadius: 400 });
    debugSpawnOrbiters(world, a.id, 'player', 6);
    sendSeedlings(world, a.id, b.id, 6, 'player');
    run(world, 6);
    expect(countOrbitingSeedlings(world, b.id, 'player')).toBe(6);
    expect(world.seedlings.size).toBe(6);
  });
});

describe('capture', () => {
  it('turns a cleared wild rock neutral so it can be planted', () => {
    const world = createEmptyWorld(50);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'grey',
    });
    debugSpawnOrbiters(world, rock.id, 'player', 16);
    debugSpawnOrbiters(world, rock.id, 'grey', 3);
    run(world, 10);
    expect(world.asteroids.get(rock.id)!.owner).toBe('neutral');
    expect(plantDyson(world, rock.id, 0, 'player').ok).toBe(true);
  });

  it('burns undefended enemy trees then opens the rock', () => {
    const world = createEmptyWorld(51);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'enemy',
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: rock.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 9,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    debugSpawnOrbiters(world, rock.id, 'player', 20);
    run(world, TREE_BURN_SECONDS + 1.5);
    expect(world.trees.size).toBe(0);
    expect(world.asteroids.get(rock.id)!.owner).toBe('neutral');
  });
});
