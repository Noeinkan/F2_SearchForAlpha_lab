import { generateAsteroidName } from './names';
import { treeTipsWorld } from './lsystem';
import { mulberry32, range } from './rng';
import {
  DYSON_GROWTH_SECONDS,
  DYSON_SPAWN_INTERVAL,
  LOCAL_SEEDLING_CAP,
  ORBIT_BAND,
  PLANT_DIVE_SPEED,
  SPROUT_DURATION,
  TRAVEL_BASE_SPEED,
  type Asteroid,
  type FactionId,
  type Seedling,
  type Tree,
  type World,
} from './types';

export function createEmptyWorld(seed = 1): World {
  return {
    asteroids: new Map(),
    trees: new Map(),
    seedlings: new Map(),
    pendingPlants: new Map(),
    nextId: 1,
    seed,
    time: 0,
  };
}

export function allocId(world: World): number {
  return world.nextId++;
}

export function createSandboxWorld(seed = 0xa57eb100): World {
  const world = createEmptyWorld(seed);
  const rng = mulberry32(seed);

  const asteroid: Asteroid = {
    id: allocId(world),
    name: generateAsteroidName(rng),
    x: 0,
    y: 0,
    radius: range(rng, 72, 96),
    travelRadius: range(rng, 280, 360),
    treeSlots: 4,
    stats: {
      energy: 80 + Math.floor(rng() * 40),
      strength: 40 + Math.floor(rng() * 50),
      speed: 50 + Math.floor(rng() * 50),
    },
    owner: 'player',
    seed: (seed ^ 0x9e3779b9) >>> 0,
    coreEnergy: 100,
    maxCoreEnergy: 100,
  };
  world.asteroids.set(asteroid.id, asteroid);

  const treeId = allocId(world);
  const tree: Tree = {
    id: treeId,
    asteroidId: asteroid.id,
    slotIndex: 0,
    kind: 'dyson',
    seed: (seed ^ 0x85ebca6b) >>> 0,
    maturity: 0,
    faction: 'player',
    spawnAccumulator: 0,
  };
  world.trees.set(tree.id, tree);

  return world;
}

function slotAngle(slotIndex: number, treeSlots: number): number {
  return -Math.PI / 2 + (slotIndex / treeSlots) * Math.PI * 2;
}

export function slotPosition(
  asteroid: Asteroid,
  slotIndex: number,
): { x: number; y: number; angle: number } {
  const angle = slotAngle(slotIndex, asteroid.treeSlots);
  const r = asteroid.radius * 0.82;
  return {
    x: asteroid.x + Math.cos(angle) * r,
    y: asteroid.y + Math.sin(angle) * r,
    angle,
  };
}

export function getOccupiedSlots(
  world: World,
  asteroidId: number,
): Set<number> {
  const occupied = new Set<number>();
  for (const t of world.trees.values()) {
    if (t.asteroidId === asteroidId) occupied.add(t.slotIndex);
  }
  for (const p of world.pendingPlants.values()) {
    if (p.asteroidId === asteroidId) occupied.add(p.slotIndex);
  }
  return occupied;
}

export function countOrbitingSeedlings(
  world: World,
  asteroidId: number,
  faction?: FactionId,
): number {
  let n = 0;
  for (const s of world.seedlings.values()) {
    if (s.state !== 'orbit' && s.state !== 'sprout') continue;
    if (s.asteroidId !== asteroidId) continue;
    if (faction !== undefined && s.faction !== faction) continue;
    n++;
  }
  return n;
}

export function countSendReady(
  world: World,
  asteroidId: number,
  faction: FactionId,
): number {
  let n = 0;
  for (const s of world.seedlings.values()) {
    if (s.state !== 'orbit') continue;
    if (s.asteroidId !== asteroidId) continue;
    if (s.faction !== faction) continue;
    n++;
  }
  return n;
}

function orbitFacing(angle: number, orbitSpeed: number): number {
  return angle + (orbitSpeed >= 0 ? Math.PI / 2 : -Math.PI / 2);
}

function spawnSeedling(world: World, tree: Tree, asteroid: Asteroid): void {
  const rng = mulberry32((world.seed ^ tree.id ^ (world.nextId * 9973)) >>> 0);
  const pos = slotPosition(asteroid, tree.slotIndex);
  const rot = pos.angle + Math.PI / 2;
  const scale = asteroid.radius / 82;
  const tips = treeTipsWorld(
    tree.seed,
    tree.maturity,
    scale,
    pos.x,
    pos.y,
    rot,
    asteroid.radius * 0.78,
  );
  const tip = tips.length > 0 ? tips[Math.floor(rng() * tips.length)]! : {
    x: pos.x,
    y: pos.y,
    angle: pos.angle,
  };

  const stats = { ...asteroid.stats };
  const orbitSpeed = 0.32 + stats.speed / 520;
  const orbitAngle = Math.atan2(tip.y - asteroid.y, tip.x - asteroid.x);
  const seedling: Seedling = {
    id: allocId(world),
    asteroidId: asteroid.id,
    faction: tree.faction,
    stats,
    state: 'sprout',
    angle: orbitAngle,
    orbitRadius: asteroid.radius + ORBIT_BAND,
    orbitSpeed,
    x: tip.x,
    y: tip.y,
    facing: tip.angle,
    sproutAge: 0,
    sproutDuration: SPROUT_DURATION * (0.85 + rng() * 0.3),
    sproutFromX: tip.x,
    sproutFromY: tip.y,
  };
  world.seedlings.set(seedling.id, seedling);
}

export function spawnOrbiters(
  world: World,
  asteroidId: number,
  faction: FactionId,
  n: number,
): void {
  const asteroid = world.asteroids.get(asteroidId);
  if (!asteroid) return;
  const rng = mulberry32((world.seed ^ asteroidId ^ n) >>> 0);
  const orbitSpeed = 0.32 + asteroid.stats.speed / 520;
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2 + rng() * 0.15;
    const orbitRadius = asteroid.radius + ORBIT_BAND + range(rng, -3, 5);
    const id = allocId(world);
    world.seedlings.set(id, {
      id,
      asteroidId,
      faction,
      stats: { ...asteroid.stats },
      state: 'orbit',
      angle,
      orbitRadius,
      orbitSpeed,
      x: asteroid.x + Math.cos(angle) * orbitRadius,
      y: asteroid.y + Math.sin(angle) * orbitRadius,
      facing: orbitFacing(angle, orbitSpeed),
    });
  }
}

function enterOrbit(s: Seedling, asteroid: Asteroid): void {
  s.state = 'orbit';
  s.asteroidId = asteroid.id;
  s.path = undefined;
  s.pathIndex = undefined;
  s.wait = undefined;
  s.angle = Math.atan2(s.y - asteroid.y, s.x - asteroid.x);
  const band = asteroid.radius + ORBIT_BAND;
  s.orbitRadius = band;
  s.orbitSpeed = 0.32 + s.stats.speed / 520;
  s.x = asteroid.x + Math.cos(s.angle) * s.orbitRadius;
  s.y = asteroid.y + Math.sin(s.angle) * s.orbitRadius;
  s.facing = orbitFacing(s.angle, s.orbitSpeed);
}

function applyOrbit(s: Seedling, asteroid: Asteroid, dt: number): void {
  const band = asteroid.radius + ORBIT_BAND;
  s.orbitRadius += (band - s.orbitRadius) * Math.min(1, 1.8 * dt);
  s.angle += s.orbitSpeed * dt;
  s.x = asteroid.x + Math.cos(s.angle) * s.orbitRadius;
  s.y = asteroid.y + Math.sin(s.angle) * s.orbitRadius;
  s.facing = orbitFacing(s.angle, s.orbitSpeed);
}

function completePlant(world: World, plantId: number): void {
  const pending = world.pendingPlants.get(plantId);
  if (!pending) return;

  const asteroid = world.asteroids.get(pending.asteroidId);
  if (!asteroid) {
    world.pendingPlants.delete(plantId);
    return;
  }

  for (const sid of pending.seedlingIds) {
    world.seedlings.delete(sid);
  }

  const treeId = allocId(world);
  world.trees.set(treeId, {
    id: treeId,
    asteroidId: pending.asteroidId,
    slotIndex: pending.slotIndex,
    kind: 'dyson',
    seed: (world.seed ^ treeId ^ pending.slotIndex * 7919) >>> 0,
    maturity: 0,
    faction: pending.faction,
    spawnAccumulator: 0,
  });

  if (asteroid.owner === 'neutral') {
    asteroid.owner = pending.faction;
  }

  world.pendingPlants.delete(plantId);
}

export function tick(world: World, dt: number): void {
  world.time += dt;

  for (const tree of world.trees.values()) {
    if (tree.kind !== 'dyson') continue;
    const asteroid = world.asteroids.get(tree.asteroidId);
    if (!asteroid) continue;

    if (tree.maturity < 1) {
      tree.maturity = Math.min(1, tree.maturity + dt / DYSON_GROWTH_SECONDS);
    }

    const spawnRate =
      DYSON_SPAWN_INTERVAL / (0.55 + tree.maturity * 0.9);
    tree.spawnAccumulator += dt;
    while (tree.spawnAccumulator >= spawnRate) {
      tree.spawnAccumulator -= spawnRate;
      if (
        countOrbitingSeedlings(world, asteroid.id) >= LOCAL_SEEDLING_CAP
      ) {
        break;
      }
      spawnSeedling(world, tree, asteroid);
    }
  }

  const toDelete: number[] = [];
  const completedPlants = new Set<number>();

  for (const s of world.seedlings.values()) {
    if (s.state === 'sprout') {
      const asteroid = world.asteroids.get(s.asteroidId);
      if (!asteroid) continue;
      const dur = s.sproutDuration ?? SPROUT_DURATION;
      s.sproutAge = (s.sproutAge ?? 0) + dt;
      const t = Math.min(1, s.sproutAge / dur);
      const hold = 0.28;
      const fromX = s.sproutFromX ?? s.x;
      const fromY = s.sproutFromY ?? s.y;
      const toX = asteroid.x + Math.cos(s.angle) * s.orbitRadius;
      const toY = asteroid.y + Math.sin(s.angle) * s.orbitRadius;
      if (t <= hold) {
        s.x = fromX;
        s.y = fromY;
      } else {
        const u = (t - hold) / (1 - hold);
        const e = u * u * (3 - 2 * u);
        s.x = fromX + (toX - fromX) * e;
        s.y = fromY + (toY - fromY) * e;
        s.facing = Math.atan2(toY - fromY, toX - fromX);
      }
      if (t >= 1) enterOrbit(s, asteroid);
      continue;
    }

    if (s.state === 'orbit') {
      const asteroid = world.asteroids.get(s.asteroidId);
      if (!asteroid) continue;
      applyOrbit(s, asteroid, dt);
      continue;
    }

    if (s.state === 'travel') {
      const home = world.asteroids.get(s.asteroidId);
      if ((s.wait ?? 0) > 0) {
        s.wait = (s.wait ?? 0) - dt;
        if (home) applyOrbit(s, home, dt);
        continue;
      }
      const path = s.path;
      const pathIndex = s.pathIndex ?? 1;
      if (!path || pathIndex >= path.length) {
        const dest = world.asteroids.get(s.asteroidId);
        if (dest) enterOrbit(s, dest);
        continue;
      }
      const hopId = path[pathIndex]!;
      const hop = world.asteroids.get(hopId);
      if (!hop) continue;

      const dx = hop.x - s.x;
      const dy = hop.y - s.y;
      const dist = Math.hypot(dx, dy);
      const arriveAt = hop.radius + ORBIT_BAND;
      const speed = TRAVEL_BASE_SPEED * (0.55 + s.stats.speed / 200);
      const step = speed * dt;
      s.facing = Math.atan2(dy, dx);
      if (dist <= arriveAt + 6 || dist <= step) {
        s.asteroidId = hopId;
        if (pathIndex >= path.length - 1) {
          enterOrbit(s, hop);
        } else {
          s.pathIndex = pathIndex + 1;
        }
      } else {
        s.x += (dx / dist) * step;
        s.y += (dy / dist) * step;
      }
      continue;
    }

    if (s.state === 'plant') {
      const home = world.asteroids.get(s.asteroidId);
      if ((s.wait ?? 0) > 0) {
        s.wait = (s.wait ?? 0) - dt;
        if (home) applyOrbit(s, home, dt);
        continue;
      }
      const tx = s.plantTargetX ?? s.x;
      const ty = s.plantTargetY ?? s.y;
      const dx = tx - s.x;
      const dy = ty - s.y;
      const dist = Math.hypot(dx, dy);
      const step = PLANT_DIVE_SPEED * dt;
      s.facing = Math.atan2(dy, dx);
      if (dist <= step || dist < 3) {
        s.x = tx;
        s.y = ty;
        const plantId = s.plantId;
        if (plantId !== undefined) {
          const pending = world.pendingPlants.get(plantId);
          if (pending) {
            pending.arrived += 1;
            toDelete.push(s.id);
            if (pending.arrived >= pending.seedlingIds.length) {
              completedPlants.add(plantId);
            }
          } else {
            toDelete.push(s.id);
          }
        }
      } else {
        s.x += (dx / dist) * step;
        s.y += (dy / dist) * step;
      }
    }
  }

  for (const id of toDelete) {
    world.seedlings.delete(id);
  }
  for (const plantId of completedPlants) {
    completePlant(world, plantId);
  }
}
