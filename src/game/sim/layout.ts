import { isGraphConnected } from './graph';
import { generateAsteroidName } from './names';
import { mulberry32, range } from './rng';
import type { Asteroid, World } from './types';
import { allocId, createEmptyWorld, spawnOrbiters } from './world';

/**
 * 5 connected asteroids. Home at origin with one pre-planted Dyson.
 * Retries layout seeds until the travel graph is connected.
 */
export function createCoreLoopWorld(seed = 0xc0a1f00d): World {
  for (let attempt = 0; attempt < 64; attempt++) {
    const world = tryLayout((seed + attempt * 9973) >>> 0);
    if (isGraphConnected(world)) return world;
  }
  // Guaranteed connected fallback: ring with generous travel radii
  return tryLayout(seed, true);
}

function tryLayout(seed: number, forceConnected = false): World {
  const world = createEmptyWorld(seed);
  const rng = mulberry32(seed);

  const home: Asteroid = {
    id: allocId(world),
    name: generateAsteroidName(rng),
    x: 0,
    y: 0,
    radius: range(rng, 72, 92),
    travelRadius: forceConnected ? 520 : range(rng, 300, 380),
    treeSlots: 4,
    stats: {
      energy: 90 + Math.floor(rng() * 40),
      strength: 45 + Math.floor(rng() * 40),
      speed: 55 + Math.floor(rng() * 40),
    },
    owner: 'player',
    seed: (seed ^ 0x9e3779b9) >>> 0,
    coreEnergy: 100,
    maxCoreEnergy: 100,
  };
  world.asteroids.set(home.id, home);

  const homeTreeId = allocId(world);
  world.trees.set(homeTreeId, {
    id: homeTreeId,
    asteroidId: home.id,
    slotIndex: 0,
    kind: 'dyson',
    seed: (seed ^ 0x85ebca6b) >>> 0,
    maturity: 0.62,
    faction: 'player',
    spawnAccumulator: 0,
  });

  spawnOrbiters(world, home.id, 'player', 8);

  const angles = [0.2, 1.4, 2.6, 4.0];
  for (let i = 0; i < 4; i++) {
    const a = angles[i]! + range(rng, -0.15, 0.15);
    const dist = forceConnected
      ? 260 + i * 40
      : range(rng, 240, 420);
    const rock: Asteroid = {
      id: allocId(world),
      name: generateAsteroidName(rng),
      x: Math.cos(a) * dist,
      y: Math.sin(a) * dist,
      radius: range(rng, 58, 88),
      travelRadius: forceConnected
        ? 520
        : range(rng, 280, 400),
      treeSlots: 4,
      stats: {
        energy: 30 + Math.floor(rng() * 140),
        strength: 30 + Math.floor(rng() * 140),
        speed: 30 + Math.floor(rng() * 140),
      },
      owner: 'neutral',
      seed: (seed ^ ((i + 1) * 0x27d4eb2d)) >>> 0,
      coreEnergy: 100,
      maxCoreEnergy: 100,
    };
    world.asteroids.set(rock.id, rock);
  }

  return world;
}
