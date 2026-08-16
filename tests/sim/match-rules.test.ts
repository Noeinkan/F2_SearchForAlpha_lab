import { describe, expect, it } from 'vitest';
import {
  createMatchRuntime,
  matchStatus,
  tickMatchRuntime,
} from '../../src/game/sim/match';
import { PLANT_COST } from '../../src/game/sim/types';
import {
  addAsteroid,
  allocId,
  createEmptyWorld,
  spawnOrbiters,
} from '../../src/game/sim/world';

describe('match win rules', () => {
  it('wins hold after continuous ownership duration', () => {
    const world = createEmptyWorld(400);
    for (let i = 0; i < 3; i++) {
      addAsteroid(world, {
        x: i * 200,
        y: 0,
        travelRadius: 300,
        owner: 'player',
      });
    }
    const home = [...world.asteroids.values()][0]!;
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: home.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'player',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    // Enemy presence so eliminate would not win.
    const enemy = addAsteroid(world, {
      x: 800,
      y: 0,
      travelRadius: 300,
      owner: 'enemy',
    });
    const et = allocId(world);
    world.trees.set(et, {
      id: et,
      asteroidId: enemy.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 2,
      maturity: 1,
      faction: 'enemy',
      spawnAccumulator: 0,
      coreFeed: 0,
    });

    const config = { win: { kind: 'hold' as const, rocks: 3, seconds: 5 } };
    const runtime = createMatchRuntime();
    expect(matchStatus(world, config, runtime)).toBe('playing');
    tickMatchRuntime(world, config, runtime, 4.5);
    expect(matchStatus(world, config, runtime)).toBe('playing');
    tickMatchRuntime(world, config, runtime, 1);
    expect(matchStatus(world, config, runtime)).toBe('won');
  });

  it('resets hold progress when ownership drops', () => {
    const world = createEmptyWorld(401);
    const a = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'player',
    });
    const b = addAsteroid(world, {
      x: 200,
      y: 0,
      travelRadius: 300,
      owner: 'player',
    });
    const treeId = allocId(world);
    world.trees.set(treeId, {
      id: treeId,
      asteroidId: a.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'player',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    const config = { win: { kind: 'hold' as const, rocks: 2, seconds: 3 } };
    const runtime = createMatchRuntime();
    tickMatchRuntime(world, config, runtime, 2.5);
    expect(runtime.holdAcc).toBeGreaterThan(2);
    b.owner = 'neutral';
    tickMatchRuntime(world, config, runtime, 0.1);
    expect(runtime.holdAcc).toBe(0);
  });

  it('wins claimEnergyWell when the target rock is owned and planted', () => {
    const world = createEmptyWorld(402);
    const home = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 300,
      owner: 'player',
    });
    const well = addAsteroid(world, {
      x: 300,
      y: 0,
      travelRadius: 300,
      owner: 'neutral',
      stats: { energy: 120, strength: 50, speed: 50 },
    });
    const homeTree = allocId(world);
    world.trees.set(homeTree, {
      id: homeTree,
      asteroidId: home.id,
      slotIndex: 0,
      kind: 'dyson',
      seed: 1,
      maturity: 1,
      faction: 'player',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    const config = {
      win: { kind: 'claimEnergyWell' as const, asteroidId: well.id },
    };
    const runtime = createMatchRuntime();
    expect(matchStatus(world, config, runtime)).toBe('playing');

    well.owner = 'player';
    const wellTree = allocId(world);
    world.trees.set(wellTree, {
      id: wellTree,
      asteroidId: well.id,
      slotIndex: 0,
      kind: 'energy',
      seed: 2,
      maturity: 0.2,
      faction: 'player',
      spawnAccumulator: 0,
      coreFeed: 0,
    });
    expect(matchStatus(world, config, runtime)).toBe('won');
  });

  it('still prefers lose on mutual wipe before eliminate win', () => {
    const world = createEmptyWorld(403);
    addAsteroid(world, { x: 0, y: 0, travelRadius: 200 });
    expect(matchStatus(world)).toBe('lost');
  });

  it('stays playing with seedlings enough to plant under hold rule', () => {
    const world = createEmptyWorld(404);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 200,
      owner: 'neutral',
    });
    spawnOrbiters(world, rock.id, 'player', PLANT_COST);
    const config = { win: { kind: 'hold' as const, rocks: 2, seconds: 10 } };
    expect(matchStatus(world, config, createMatchRuntime())).toBe('playing');
  });
});
