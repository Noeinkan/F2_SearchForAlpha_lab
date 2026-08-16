import { describe, expect, it } from 'vitest';
import {
  debugSpawnOrbiters,
  plantTree,
} from '../../src/game/sim/commands';
import { createCoreLoopWorld } from '../../src/game/sim/layout';
import { matchStatus } from '../../src/game/sim/match';
import { PLANT_COST } from '../../src/game/sim/types';
import {
  addAsteroid,
  allocId,
  createEmptyWorld,
  spawnOrbiters,
} from '../../src/game/sim/world';

describe('matchStatus', () => {
  it('reports playing on a fresh core-loop world', () => {
    const world = createCoreLoopWorld(42);
    expect(matchStatus(world)).toBe('playing');
  });

  it('reports won when enemy trees are gone', () => {
    const world = createCoreLoopWorld(42);
    for (const t of [...world.trees.values()]) {
      if (t.faction === 'enemy') world.trees.delete(t.id);
    }
    expect(matchStatus(world)).toBe('won');
  });

  it('reports lost when player has no trees and fewer than PLANT_COST seedlings', () => {
    const world = createCoreLoopWorld(42);
    for (const t of [...world.trees.values()]) {
      if (t.faction === 'player') world.trees.delete(t.id);
    }
    for (const s of [...world.seedlings.values()]) {
      if (s.faction === 'player') world.seedlings.delete(s.id);
    }
    debugSpawnOrbiters(world, [...world.asteroids.keys()][0]!, 'player', 5);
    expect(matchStatus(world)).toBe('lost');
  });

  it('stays playing with no trees but enough seedlings to plant', () => {
    const world = createEmptyWorld(7);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'neutral',
    });
    spawnOrbiters(world, rock.id, 'player', PLANT_COST);
    const enemyRock = addAsteroid(world, {
      x: 300,
      y: 0,
      travelRadius: 200,
      owner: 'enemy',
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: enemyRock.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    expect(matchStatus(world)).toBe('playing');
  });

  it('stays playing with no trees but a player pending plant', () => {
    const world = createEmptyWorld(8);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      minerals: 74,
      owner: 'neutral',
    });
    spawnOrbiters(world, rock.id, 'player', PLANT_COST);
    const result = plantTree(world, rock.id, 0, 'player', 'dyson');
    expect(result.ok).toBe(true);
    expect(world.pendingPlants.size).toBe(1);
    const enemyRock = addAsteroid(world, {
      x: 300,
      y: 0,
      travelRadius: 200,
      owner: 'enemy',
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: enemyRock.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    expect(matchStatus(world)).toBe('playing');
  });

  it('does not report won while enemy has a pending plant', () => {
    const world = createEmptyWorld(9);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      minerals: 74,
      owner: 'neutral',
    });
    // Player presence so we are not lost
    spawnOrbiters(world, rock.id, 'player', PLANT_COST);
    plantTree(world, rock.id, 0, 'player', 'dyson');

    const enemyRock = addAsteroid(world, {
      x: 300,
      y: 0,
      travelRadius: 200,
      minerals: 74,
      owner: 'neutral',
    });
    spawnOrbiters(world, enemyRock.id, 'enemy', PLANT_COST);
    const enemyPlant = plantTree(world, enemyRock.id, 0, 'enemy', 'dyson');
    expect(enemyPlant.ok).toBe(true);

    for (const t of [...world.trees.values()]) {
      if (t.faction === 'enemy') world.trees.delete(t.id);
    }
    expect(matchStatus(world)).toBe('playing');
  });

  it('reports lost when both empires are wiped', () => {
    const world = createEmptyWorld(10);
    addAsteroid(world, { x: 0, y: 0, travelRadius: 200 });
    expect(matchStatus(world)).toBe('lost');
  });
});
