import { describe, expect, it } from 'vitest';
import { hitRockCrust, rockRadiusAt, slotPolar } from '../../src/game/sim/rock';
import { ROCK_SURFACE_INSET } from '../../src/game/sim/types';
import { addAsteroid, createEmptyWorld } from '../../src/game/sim/world';

describe('hitRockCrust', () => {
  it('hits a point on the lumpy rim and misses the interior', () => {
    const world = createEmptyWorld(1);
    const rock = addAsteroid(world, {
      x: 40,
      y: -20,
      travelRadius: 200,
    });
    const angle = 0.4;
    const rim = rockRadiusAt(rock, angle);
    const onRim = {
      x: rock.x + Math.cos(angle) * rim,
      y: rock.y + Math.sin(angle) * rim,
    };
    const hit = hitRockCrust(world.asteroids.values(), onRim.x, onRim.y, 18);
    expect(hit).not.toBeNull();
    expect(hit!.id).toBe(rock.id);
    expect(hit!.angle).toBeCloseTo(angle, 5);

    const inside = hitRockCrust(
      world.asteroids.values(),
      rock.x,
      rock.y,
      18,
    );
    expect(inside).toBeNull();
  });
});

describe('crust collar', () => {
  it('nests the plant in the crust film instead of the hollow', () => {
    const world = createEmptyWorld(2);
    const rock = addAsteroid(world, {
      x: 0,
      y: 0,
      radius: 140,
      travelRadius: 400,
      treeSlots: 5,
      seed: 9,
    });
    const polar = slotPolar(rock, 0);
    expect(polar.rim - polar.dist).toBeLessThan(rock.radius * 0.06);
    expect(polar.rim - polar.dist).toBeCloseTo(
      rock.radius * ROCK_SURFACE_INSET,
      5,
    );
    expect(polar.dist).toBeGreaterThan(polar.rim * 0.92);
    expect(polar.surfaceY).toBeCloseTo(polar.dist - polar.rim, 5);
    expect(polar.surfaceY).toBeLessThan(0);
  });
});
