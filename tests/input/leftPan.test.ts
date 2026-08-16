import { describe, expect, it } from 'vitest';
import { shouldLeftPan } from '../../src/game/input/gameplay';
import { orbitBand } from '../../src/game/sim/types';
import { addAsteroid, createEmptyWorld } from '../../src/game/sim/world';

describe('shouldLeftPan', () => {
  it('pans far from every rock and not on the rock itself', () => {
    const world = createEmptyWorld(1);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      radius: 40,
      travelRadius: 200,
    });
    expect(shouldLeftPan(world, 0, 0)).toBe(false);
    const rim =
      rock.radius + orbitBand(rock.radius) + 28;
    expect(shouldLeftPan(world, rim + 8, 0)).toBe(true);
  });
});
