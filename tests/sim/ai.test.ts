import { describe, expect, it } from 'vitest';
import { tickAi } from '../../src/game/sim/ai';
import { debugSpawnOrbiters } from '../../src/game/sim/commands';
import {
  AI_GARRISON,
  AI_THINK_INTERVAL,
  DEFENSE_TREE_MIN_ENERGY,
  ENERGY_TREE_MIN_ENERGY,
  PLANT_COST,
} from '../../src/game/sim/types';
import {
  addAsteroid,
  allocId,
  countSendReady,
  createEmptyWorld,
} from '../../src/game/sim/world';

function think(world: ReturnType<typeof createEmptyWorld>): void {
  tickAi(world, AI_THINK_INTERVAL);
}

describe('AI planting', () => {
  it('plants Energy on a high-energy held rock', () => {
    const world = createEmptyWorld(100);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'enemy',
      treeSlots: 4,
      stats: {
        energy: ENERGY_TREE_MIN_ENERGY + 20,
        strength: 50,
        speed: 50,
      },
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: rock.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    debugSpawnOrbiters(world, rock.id, 'enemy', PLANT_COST + AI_GARRISON);

    think(world);

    const pending = [...world.pendingPlants.values()].find(
      (p) => p.asteroidId === rock.id && p.faction === 'enemy',
    );
    expect(pending?.kind).toBe('energy');
  });

  it('plants Defense on a border rock that cannot take Energy', () => {
    const world = createEmptyWorld(101);
    const home = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'enemy',
      treeSlots: 4,
      stats: {
        energy: DEFENSE_TREE_MIN_ENERGY + 5,
        strength: 50,
        speed: 50,
      },
    });
    addAsteroid(world, {
      x: 200,
      y: 0,
      travelRadius: 300,
      owner: 'player',
      stats: { energy: 40, strength: 40, speed: 40 },
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: home.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    debugSpawnOrbiters(world, home.id, 'enemy', PLANT_COST + AI_GARRISON);

    think(world);

    const pending = [...world.pendingPlants.values()].find(
      (p) => p.asteroidId === home.id && p.faction === 'enemy',
    );
    expect(pending?.kind).toBe('defense');
  });

  it('does not strip a held rock below garrison to plant', () => {
    const world = createEmptyWorld(102);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'enemy',
      treeSlots: 4,
      stats: { energy: 40, strength: 50, speed: 50 },
    });
    addAsteroid(world, {
      x: 200,
      y: 0,
      travelRadius: 300,
      owner: 'player',
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: rock.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    const ready = AI_GARRISON + Math.floor(PLANT_COST / 2);
    expect(ready).toBeGreaterThan(AI_GARRISON);
    expect(ready).toBeLessThan(AI_GARRISON + PLANT_COST);
    debugSpawnOrbiters(world, rock.id, 'enemy', ready);

    think(world);

    expect(world.pendingPlants.size).toBe(0);
    expect(countSendReady(world, rock.id, 'enemy')).toBeGreaterThanOrEqual(
      AI_GARRISON,
    );
  });
});

describe('AI retake home', () => {
  it('sends surplus toward a lost aiHomeId', () => {
    const world = createEmptyWorld(103);
    const home = addAsteroid(world, {
      x: 200,
      y: 0,
      travelRadius: 300,
      owner: 'player',
    });
    world.aiHomeId = home.id;

    const base = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'enemy',
      treeSlots: 1,
      stats: { energy: 40, strength: 50, speed: 50 },
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: base.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    debugSpawnOrbiters(world, base.id, 'enemy', AI_GARRISON + 10);

    think(world);

    const travelers = [...world.seedlings.values()].filter(
      (s) =>
        s.faction === 'enemy' &&
        s.state === 'travel' &&
        s.path?.includes(home.id),
    );
    expect(travelers.length).toBeGreaterThan(0);
    expect(countSendReady(world, base.id, 'enemy')).toBeGreaterThanOrEqual(
      AI_GARRISON,
    );
  });
});
