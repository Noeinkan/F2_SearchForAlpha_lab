import { describe, expect, it } from 'vitest';
import { travelCentroid } from '../../src/game/input/followSend';
import { debugSpawnOrbiters, sendSeedlings } from '../../src/game/sim/commands';
import {
  addAsteroid,
  createEmptyWorld,
} from '../../src/game/sim/world';

describe('travelCentroid', () => {
  it('returns null when no seedlings are traveling', () => {
    const world = createEmptyWorld(300);
    const a = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 400,
      owner: 'player',
    });
    debugSpawnOrbiters(world, a.id, 'player', 4);
    expect(travelCentroid(world, 'player')).toBeNull();
  });

  it('returns the mean position of traveling player seedlings', () => {
    const world = createEmptyWorld(301);
    const a = addAsteroid(world, {
      x: 0,
      y: 0,
      travelRadius: 400,
      owner: 'player',
    });
    const b = addAsteroid(world, { x: 200, y: 0, travelRadius: 400 });
    debugSpawnOrbiters(world, a.id, 'player', 4);
    sendSeedlings(world, a.id, b.id, 2, 'player');

    const travelers = [...world.seedlings.values()].filter(
      (s) => s.state === 'travel' && s.faction === 'player',
    );
    expect(travelers.length).toBe(2);
    const expectedX =
      travelers.reduce((sum, s) => sum + s.x, 0) / travelers.length;
    const expectedY =
      travelers.reduce((sum, s) => sum + s.y, 0) / travelers.length;
    const center = travelCentroid(world, 'player');
    expect(center).not.toBeNull();
    expect(center!.x).toBeCloseTo(expectedX);
    expect(center!.y).toBeCloseTo(expectedY);
  });
});
