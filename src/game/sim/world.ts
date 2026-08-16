import { generateAsteroidName } from './names';
import {
  buildAdultTree,
  FLOWER_SPAWN_READY,
  measureRootFeed,
  rootFeedActive,
  spawnReadiness,
  treeFlowersWorld,
} from './lsystem';
import { mulberry32, range } from './rng';
import { pickRockRadius, rockRadiusAt, slotPolar } from './rock';
import { resolveCombat, seedlingMaxHp } from './combat';
import {
  DEFENSE_GROWTH_SECONDS,
  DYSON_GROWTH_SECONDS,
  DYSON_SPAWN_INTERVAL,
  ENERGY_GROWTH_SECONDS,
  ENERGY_REGEN_BASE,
  ENERGY_SPAWN_INTERVAL,
  LOCAL_SEEDLING_CAP,
  orbitBand,
  PLANT_DIVE_SPEED,
  ROCK_RADIUS_DEFAULT,
  ROCK_SURFACE_INSET,
  ROOT_FEED_REGEN,
  ROOT_FEED_SPAWN_BONUS,
  SENTINEL_SPAWN_ENERGY,
  SENTINEL_STARVE_DPS,
  SENTINEL_UPKEEP,
  SHIELD_PER_DEFENSE,
  SPAWN_START_MATURITY,
  SPROUT_DURATION,
  TRAVEL_BASE_SPEED,
  TREE_BURN_SECONDS,
  energyCapacity,
  mineralsToSlots,
  treeVisualScale,
  type Asteroid,
  type FactionId,
  type Seedling,
  type SeedlingKind,
  type Stats,
  type Tree,
  type TreeKind,
  type World,
} from './types';

export interface AsteroidSpec {
  x: number;
  y: number;
  travelRadius: number;
  name?: string;
  radius?: number;
  treeSlots?: number;
  minerals?: number;
  stats?: Stats;
  owner?: FactionId;
  seed?: number;
  coreEnergy?: number;
  maxCoreEnergy?: number;
}

export function createEmptyWorld(seed = 1): World {
  return {
    asteroids: new Map(),
    trees: new Map(),
    seedlings: new Map(),
    pendingPlants: new Map(),
    nextId: 1,
    seed,
    time: 0,
    aiAcc: 0,
    aiHomeId: null,
    difficulty: 'normal',
  };
}

export function allocId(world: World): number {
  return world.nextId++;
}

export function addAsteroid(world: World, spec: AsteroidSpec): Asteroid {
  const id = allocId(world);
  const stats = spec.stats ?? { energy: 50, strength: 50, speed: 50 };
  const minerals = spec.minerals ?? 50;
  const maxEnergyPool = energyCapacity(stats.energy);
  const asteroid: Asteroid = {
    id,
    name: spec.name ?? `A${id}`,
    x: spec.x,
    y: spec.y,
    radius: spec.radius ?? ROCK_RADIUS_DEFAULT,
    travelRadius: spec.travelRadius,
    minerals,
    treeSlots: spec.treeSlots ?? mineralsToSlots(minerals),
    stats,
    owner: spec.owner ?? 'neutral',
    seed: spec.seed ?? id,
    coreEnergy: spec.coreEnergy ?? 100,
    maxCoreEnergy: spec.maxCoreEnergy ?? 100,
    energyPool: maxEnergyPool,
    maxEnergyPool,
    shield: 0,
    maxShield: 0,
    burnTimer: 0,
  };
  world.asteroids.set(id, asteroid);
  return asteroid;
}

export function createSandboxWorld(seed = 0xa57eb100): World {
  const world = createEmptyWorld(seed);
  const rng = mulberry32(seed);

  const asteroid = addAsteroid(world, {
    name: generateAsteroidName(rng),
    x: 0,
    y: 0,
    radius: pickRockRadius(rng),
    travelRadius: range(rng, 280, 360),
    minerals: 72,
    stats: {
      energy: 80 + Math.floor(rng() * 40),
      strength: 40 + Math.floor(rng() * 50),
      speed: 50 + Math.floor(rng() * 50),
    },
    owner: 'player',
    seed: (seed ^ 0x9e3779b9) >>> 0,
  });

  const treeId = allocId(world);
  const treeSeed = (seed ^ 0x85ebca6b) >>> 0;
  const tree: Tree = {
    id: treeId,
    asteroidId: asteroid.id,
    slotIndex: 0,
    kind: 'dyson',
    seed: treeSeed,
    maturity: 0,
    faction: 'player',
    spawnAccumulator: 0,
    coreFeed: computeTreeCoreFeed(asteroid, treeSeed, 0, 'dyson'),
  };
  world.trees.set(tree.id, tree);

  return world;
}

export function slotPosition(
  asteroid: Asteroid,
  slotIndex: number,
): { x: number; y: number; angle: number } {
  const { angle, dist } = slotPolar(asteroid, slotIndex);
  return {
    x: asteroid.x + Math.cos(angle) * dist,
    y: asteroid.y + Math.sin(angle) * dist,
    angle,
  };
}

/** Bake root-to-core feed for a planted tree (deterministic for seed/slot). */
export function computeTreeCoreFeed(
  asteroid: Asteroid,
  treeSeed: number,
  slotIndex: number,
  kind: TreeKind,
): number {
  const scale = treeVisualScale(asteroid.radius, asteroid.seed);
  const polar = slotPolar(asteroid, slotIndex);
  const surfaceY = -(asteroid.radius * ROCK_SURFACE_INSET);
  const adult = buildAdultTree(
    treeSeed,
    scale,
    polar.dist,
    surfaceY,
    kind,
  );
  return measureRootFeed(adult, polar.dist);
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

export function countOrbitingKind(
  world: World,
  asteroidId: number,
  faction: FactionId,
  kind: SeedlingKind,
): number {
  let n = 0;
  for (const s of world.seedlings.values()) {
    if (s.state !== 'orbit' && s.state !== 'sprout') continue;
    if (s.asteroidId !== asteroidId) continue;
    if (s.faction !== faction) continue;
    if (s.kind !== kind) continue;
    n++;
  }
  return n;
}

export function countTrees(
  world: World,
  asteroidId: number,
  faction?: FactionId,
  kind?: TreeKind,
): number {
  let n = 0;
  for (const t of world.trees.values()) {
    if (t.asteroidId !== asteroidId) continue;
    if (faction !== undefined && t.faction !== faction) continue;
    if (kind !== undefined && t.kind !== kind) continue;
    n++;
  }
  return n;
}

export function hasHostileOrbiters(
  world: World,
  asteroidId: number,
  faction: FactionId,
): boolean {
  for (const s of world.seedlings.values()) {
    if (s.asteroidId !== asteroidId) continue;
    if (s.state !== 'orbit' && s.state !== 'sprout') continue;
    if (s.faction !== faction) return true;
  }
  return false;
}

export function hasHostileTrees(
  world: World,
  asteroidId: number,
  faction: FactionId,
): boolean {
  for (const t of world.trees.values()) {
    if (t.asteroidId !== asteroidId) continue;
    if (t.faction !== faction) return true;
  }
  return false;
}

function orbitFacing(angle: number, orbitSpeed: number): number {
  return angle + (orbitSpeed >= 0 ? Math.PI / 2 : -Math.PI / 2);
}

/** Project a spherical orbit into the XY plane; +z is toward the camera. */
function spherePoint(
  ax: number,
  ay: number,
  radius: number,
  longitude: number,
  node: number,
  inclination: number,
): { x: number; y: number; z: number } {
  const lat = Math.sin(longitude - node) * inclination;
  const c = Math.cos(lat);
  return {
    x: ax + radius * c * Math.cos(longitude),
    y: ay + radius * c * Math.sin(longitude),
    z: radius * Math.sin(lat),
  };
}

function makeSeedling(
  world: World,
  asteroid: Asteroid,
  faction: FactionId,
  kind: SeedlingKind,
  partial: Omit<
    Seedling,
    'id' | 'asteroidId' | 'faction' | 'kind' | 'stats' | 'hp' | 'maxHp' | 'z'
  > &
    Partial<Pick<Seedling, 'stats' | 'z'>>,
): Seedling {
  const stats = partial.stats ?? { ...asteroid.stats };
  const maxHp = seedlingMaxHp(kind, stats.strength);
  const id = allocId(world);
  const seedling: Seedling = {
    ...partial,
    id,
    asteroidId: asteroid.id,
    faction,
    kind,
    stats,
    hp: maxHp,
    maxHp,
    z: partial.z ?? 0,
    phase: partial.phase ?? 0,
  };
  world.seedlings.set(id, seedling);
  return seedling;
}

function spawnSeedling(world: World, tree: Tree, asteroid: Asteroid): void {
  const rng = mulberry32((world.seed ^ tree.id ^ (world.nextId * 9973)) >>> 0);
  const pos = slotPosition(asteroid, tree.slotIndex);
  const rot = pos.angle + Math.PI / 2;
  const scale = treeVisualScale(asteroid.radius, asteroid.seed);
  const polar = slotPolar(asteroid, tree.slotIndex);
  const surfaceY = -(asteroid.radius * ROCK_SURFACE_INSET);
  const flowers = treeFlowersWorld(
    tree.seed,
    tree.maturity,
    scale,
    pos.x,
    pos.y,
    rot,
    polar.dist,
    surfaceY,
    tree.kind,
    FLOWER_SPAWN_READY,
  );
  if (flowers.length === 0) return;

  const flower = flowers[Math.floor(rng() * flowers.length)]!;

  const kind: SeedlingKind = tree.kind === 'energy' ? 'sentinel' : 'basic';
  const stats = { ...asteroid.stats };
  const orbitSpeed = 0.28 + stats.speed / 560;
  const orbitAngle = Math.atan2(flower.y - asteroid.y, flower.x - asteroid.x);
  makeSeedling(world, asteroid, tree.faction, kind, {
    stats,
    state: 'sprout',
    angle: orbitAngle,
    orbitRadius: rockRadiusAt(asteroid, orbitAngle) + orbitBand(asteroid.radius) + range(rng, -4, 6),
    orbitSpeed,
    x: flower.x,
    y: flower.y,
    z: 0,
    facing: flower.angle,
    phase: rng() * Math.PI * 2,
    orbitBias: range(rng, -5, 7),
    inclination: 0.34 + rng() * 0.28,
    orbitNode: orbitAngle,
    sproutAge: 0,
    sproutDuration: SPROUT_DURATION * (0.85 + rng() * 0.3),
    sproutFromX: flower.x,
    sproutFromY: flower.y,
    sproutTipAngle: flower.angle,
  });
}


export function spawnOrbiters(
  world: World,
  asteroidId: number,
  faction: FactionId,
  n: number,
  kind: SeedlingKind = 'basic',
): void {
  const asteroid = world.asteroids.get(asteroidId);
  if (!asteroid) return;
  const rng = mulberry32((world.seed ^ asteroidId ^ n) >>> 0);
  const orbitSpeed = 0.28 + asteroid.stats.speed / 560;
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2 + rng() * 0.15;
    const orbitRadius =
      rockRadiusAt(asteroid, angle) +
      orbitBand(asteroid.radius) +
      range(rng, -4, 6);
    const speed = orbitSpeed * (0.88 + rng() * 0.24);
    const inc = 0.3 + rng() * 0.3;
    const node = angle + range(rng, -0.5, 0.5);
    const p = spherePoint(asteroid.x, asteroid.y, orbitRadius, angle, node, inc);
    makeSeedling(world, asteroid, faction, kind, {
      state: 'orbit',
      angle,
      orbitRadius,
      orbitSpeed: speed,
      x: p.x,
      y: p.y,
      z: p.z,
      facing: orbitFacing(angle, speed),
      phase: rng() * Math.PI * 2,
      orbitBias: range(rng, -5, 7),
      inclination: inc,
      orbitNode: node,
    });
  }
}

function enterOrbit(s: Seedling, asteroid: Asteroid): void {
  s.state = 'orbit';
  s.asteroidId = asteroid.id;
  s.path = undefined;
  s.pathIndex = undefined;
  s.wait = undefined;
  s.heading = undefined;
  s.angle = Math.atan2(s.y - asteroid.y, s.x - asteroid.x);
  s.orbitRadius = Math.hypot(s.x - asteroid.x, s.y - asteroid.y);
  s.orbitSpeed = 0.28 + s.stats.speed / 560;
  if (s.inclination === undefined) {
    s.inclination = 0.28 + Math.abs(Math.sin(s.phase)) * 0.24;
  }
  if (s.orbitNode === undefined) s.orbitNode = s.angle;
}

function applyOrbit(s: Seedling, asteroid: Asteroid, dt: number, time: number): void {
  const band =
    rockRadiusAt(asteroid, s.angle) +
    orbitBand(asteroid.radius) +
    (s.orbitBias ?? 0);
  s.orbitRadius += (band - s.orbitRadius) * Math.min(1, 1.35 * dt);
  s.angle += s.orbitSpeed * dt;

  const ph = s.phase;
  const breezeR =
    Math.sin(time * 0.62 + ph) * 5.8 + Math.sin(time * 1.18 + ph * 1.37) * 2.6;
  const breezeT = Math.sin(time * 0.41 + ph * 0.73) * 0.07;
  const r = s.orbitRadius + breezeR;
  const a = s.angle + breezeT;
  const p = spherePoint(
    asteroid.x,
    asteroid.y,
    r,
    a,
    s.orbitNode ?? a,
    s.inclination ?? 0.3,
  );
  p.z += Math.sin(time * 0.7 + ph) * 2.4;

  const px = s.x;
  const py = s.y;
  const glide = 1 - Math.exp(-2.6 * dt);
  s.x += (p.x - s.x) * glide;
  s.y += (p.y - s.y) * glide;
  s.z += (p.z - s.z) * glide;

  const vx = s.x - px;
  const vy = s.y - py;
  if (vx * vx + vy * vy > 0.0004) {
    s.facing = lerpAngle(s.facing, Math.atan2(vy, vx), 3.4 * dt);
  }
}

function lerpAngle(from: number, to: number, t: number): number {
  const k = Math.min(1, Math.max(0, t));
  return from + shortestAngle(from, to) * k;
}

function shortestAngle(from: number, to: number): number {
  let d = to - from;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
}

/**
 * 3D Alsomitra soar: helix around the tree, then hand off to an
 * inclined orbit around the planet. x/y are the camera projection.
 */
function applySproutGlide(s: Seedling, world: World, dt: number): void {
  const asteroid = world.asteroids.get(s.asteroidId);
  if (!asteroid) return;
  const dur = s.sproutDuration ?? SPROUT_DURATION;
  s.sproutAge = (s.sproutAge ?? 0) + dt;
  const age = s.sproutAge;
  const t = Math.min(1, age / dur);
  const hold = 0.06;
  const fromX = s.sproutFromX ?? s.x;
  const fromY = s.sproutFromY ?? s.y;
  const tipA = s.sproutTipAngle ?? s.facing;
  const ax = asteroid.x;
  const ay = asteroid.y;
  const fromA = Math.atan2(fromY - ay, fromX - ax);
  const fromR = Math.hypot(fromX - ax, fromY - ay);
  const period = 1.32 + Math.sin(s.phase) * 0.12;
  const omega = (Math.PI * 2) / period;
  const inc = s.inclination ?? 0.4;
  const node = s.orbitNode ?? fromA;

  if (t <= hold) {
    s.x = fromX;
    s.y = fromY;
    s.z = 0;
    s.facing = tipA;
  } else {
    const u = (t - hold) / (1 - hold);
    const linger = 0.18;
    const descendU = u < linger ? 0 : (u - linger) / (1 - linger);
    const descend = descendU * descendU * (3 - 2 * descendU);
    const damp = 1 - u * u;
    const phugoid = Math.sin(age * omega) * (10 + Math.sin(s.phase) * 3) * damp;
    const turn = s.orbitSpeed >= 0 ? 1 : -1;

    const tx = Math.cos(fromA);
    const ty = Math.sin(fromA);
    const nx = -ty;
    const ny = tx;
    const wraps = 0.72 + Math.cos(s.phase) * 0.18;
    const psi = turn * wraps * Math.PI * 2 * (u * u * (3 - 2 * u));
    const rho =
      8 + Math.sin(s.phase) * 3 + 20 * Math.sin(Math.min(1, u * 1.2) * Math.PI * 0.5);
    const h = fromR + (s.orbitRadius - fromR) * descend + phugoid;
    const treeX = ax + tx * h + nx * rho * Math.cos(psi);
    const treeY = ay + ty * h + ny * rho * Math.cos(psi);
    const treeZ = rho * Math.sin(psi) + phugoid * 0.4;

    const helix = turn * (0.7 + Math.cos(s.phase) * 0.12) * (u * u * (3 - 2 * u));
    const a = fromA + helix;
    const r = Math.max(rockRadiusAt(asteroid, a) + 8, s.orbitRadius + phugoid * 0.35);
    const planet = spherePoint(ax, ay, r, a, node, inc);

    const handoff = u < 0.36 ? 0 : (u - 0.36) / 0.64;
    const w = handoff * handoff * (3 - 2 * handoff);
    const px = s.x;
    const py = s.y;
    s.x = treeX + (planet.x - treeX) * w;
    s.y = treeY + (planet.y - treeY) * w;
    s.z = treeZ + (planet.z - treeZ) * w;

    const vx = s.x - px;
    const vy = s.y - py;
    if (vx * vx + vy * vy > 1e-8) {
      const climb = Math.cos(age * omega) * damp;
      const desired = Math.atan2(vy, vx) + climb * 0.2;
      s.facing = lerpAngle(s.facing, desired, 2.5 * dt);
    }
  }

  if (t >= 1) enterOrbit(s, asteroid);
}

function glideToward(
  s: Seedling,
  tx: number,
  ty: number,
  dist: number,
  dx: number,
  dy: number,
  step: number,
  dt: number,
  time: number,
  breezeAmt: number,
): void {
  const inv = 1 / Math.max(dist, 1e-4);
  const nx = -dy * inv;
  const ny = dx * inv;
  const fade = Math.min(1, dist / 140);
  const dutch = Math.sin(time * 0.52 + s.phase) * 14 * breezeAmt * fade;
  const phugoid = Math.sin(time * 2.05 + s.phase * 0.7) * 7 * breezeAmt * fade;
  const desired = Math.atan2(
    ty + ny * dutch + (dy * inv) * phugoid - s.y,
    tx + nx * dutch + (dx * inv) * phugoid - s.x,
  );
  if (s.heading === undefined) s.heading = s.facing;
  const turn = 1.15 + (1 - fade) * 2.1;
  s.heading = lerpAngle(s.heading, desired, turn * dt);
  s.x += Math.cos(s.heading) * step;
  s.y += Math.sin(s.heading) * step;
  const zBob = Math.sin(time * 2.05 + s.phase) * 9 * breezeAmt * fade;
  s.z += (zBob - s.z) * Math.min(1, 1.6 * dt);
  s.facing = lerpAngle(s.facing, s.heading, 2.8 * dt);
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
  const treeSeed = (world.seed ^ treeId ^ pending.slotIndex * 7919) >>> 0;
  world.trees.set(treeId, {
    id: treeId,
    asteroidId: pending.asteroidId,
    slotIndex: pending.slotIndex,
    kind: pending.kind,
    seed: treeSeed,
    maturity: 0,
    faction: pending.faction,
    spawnAccumulator: 0,
    coreFeed: computeTreeCoreFeed(
      asteroid,
      treeSeed,
      pending.slotIndex,
      pending.kind,
    ),
  });

  asteroid.owner = pending.faction;
  asteroid.burnTimer = 0;

  world.pendingPlants.delete(plantId);
}

function growthSeconds(kind: TreeKind): number {
  if (kind === 'energy') return ENERGY_GROWTH_SECONDS;
  if (kind === 'defense') return DEFENSE_GROWTH_SECONDS;
  return DYSON_GROWTH_SECONDS;
}

function spawnInterval(tree: Tree, asteroid: Asteroid): number {
  const base =
    tree.kind === 'energy' ? ENERGY_SPAWN_INTERVAL : DYSON_SPAWN_INTERVAL;
  const ready = spawnReadiness(tree.maturity, SPAWN_START_MATURITY);
  // Avoid divide-by-zero; callers should not spawn when readiness is 0.
  const maturityMul = Math.max(0.05, ready);
  const mineralMul = 0.55 + asteroid.minerals / 100;
  const energyMul = 0.75 + asteroid.stats.energy / 280;
  const feedMul = 1 + ROOT_FEED_SPAWN_BONUS * rootFeedActive(tree.maturity, tree.coreFeed);
  return base / (maturityMul * mineralMul * energyMul * feedMul);
}

function tickEnergy(world: World, dt: number): void {
  const sentinelCount = new Map<number, number>();
  for (const s of world.seedlings.values()) {
    if (s.kind !== 'sentinel') continue;
    if (s.state !== 'orbit' && s.state !== 'sprout') continue;
    sentinelCount.set(
      s.asteroidId,
      (sentinelCount.get(s.asteroidId) ?? 0) + 1,
    );
  }

  for (const asteroid of world.asteroids.values()) {
    asteroid.maxEnergyPool = energyCapacity(asteroid.stats.energy);
    let rootRegen = 0;
    for (const tree of world.trees.values()) {
      if (tree.asteroidId !== asteroid.id) continue;
      rootRegen +=
        ROOT_FEED_REGEN * rootFeedActive(tree.maturity, tree.coreFeed);
    }
    const regen =
      (ENERGY_REGEN_BASE + asteroid.stats.energy / 40 + rootRegen) * dt;
    asteroid.energyPool = Math.min(
      asteroid.maxEnergyPool,
      asteroid.energyPool + regen,
    );
    const upkeep = (sentinelCount.get(asteroid.id) ?? 0) * SENTINEL_UPKEEP * dt;
    asteroid.energyPool = Math.max(0, asteroid.energyPool - upkeep);
  }

  if (sentinelCount.size === 0) return;
  const starving = new Set<number>();
  for (const asteroid of world.asteroids.values()) {
    if (asteroid.energyPool <= 0.05 && (sentinelCount.get(asteroid.id) ?? 0) > 0) {
      starving.add(asteroid.id);
    }
  }
  if (starving.size === 0) return;
  const dead: number[] = [];
  for (const s of world.seedlings.values()) {
    if (s.kind !== 'sentinel') continue;
    if (s.state !== 'orbit' && s.state !== 'sprout') continue;
    if (!starving.has(s.asteroidId)) continue;
    s.hp -= SENTINEL_STARVE_DPS * dt;
    if (s.hp <= 0) dead.push(s.id);
  }
  for (const id of dead) world.seedlings.delete(id);
}

function tickShields(world: World, dt: number): void {
  const defenseByRock = new Map<number, number>();
  for (const t of world.trees.values()) {
    if (t.kind !== 'defense' || t.maturity < 0.35) continue;
    defenseByRock.set(
      t.asteroidId,
      (defenseByRock.get(t.asteroidId) ?? 0) + t.maturity,
    );
  }
  for (const asteroid of world.asteroids.values()) {
    const def = defenseByRock.get(asteroid.id) ?? 0;
    asteroid.maxShield =
      def * SHIELD_PER_DEFENSE * (0.5 + asteroid.stats.energy / 200);
    if (asteroid.maxShield <= 0) {
      asteroid.shield = 0;
      continue;
    }
    asteroid.shield = Math.min(asteroid.shield, asteroid.maxShield);
    if (asteroid.energyPool <= 0) continue;
    const regen = asteroid.maxShield * 0.12 * dt;
    asteroid.shield = Math.min(asteroid.maxShield, asteroid.shield + regen);
    asteroid.energyPool = Math.max(0, asteroid.energyPool - regen * 0.08);
  }
}

function tickTrees(world: World, dt: number): void {
  for (const tree of world.trees.values()) {
    const asteroid = world.asteroids.get(tree.asteroidId);
    if (!asteroid) continue;

    if (tree.maturity < 1) {
      tree.maturity = Math.min(1, tree.maturity + dt / growthSeconds(tree.kind));
    }

    if (tree.kind === 'defense') continue;

    if (tree.maturity < SPAWN_START_MATURITY) {
      tree.spawnAccumulator = 0;
      continue;
    }

    if (
      hasHostileOrbiters(world, asteroid.id, tree.faction) &&
      countSendReady(world, asteroid.id, tree.faction) === 0
    ) {
      continue;
    }

    const interval = spawnInterval(tree, asteroid);
    tree.spawnAccumulator += dt;
    while (tree.spawnAccumulator >= interval) {
      tree.spawnAccumulator -= interval;
      if (countOrbitingSeedlings(world, asteroid.id) >= LOCAL_SEEDLING_CAP) {
        break;
      }
      if (tree.kind === 'energy') {
        if (asteroid.energyPool < SENTINEL_SPAWN_ENERGY) break;
        asteroid.energyPool -= SENTINEL_SPAWN_ENERGY * 0.35;
      }
      spawnSeedling(world, tree, asteroid);
    }
  }
}

function occupierOf(
  world: World,
  asteroidId: number,
): FactionId | null {
  const counts = new Map<FactionId, number>();
  for (const s of world.seedlings.values()) {
    if (s.asteroidId !== asteroidId) continue;
    if (s.state !== 'orbit' && s.state !== 'sprout') continue;
    counts.set(s.faction, (counts.get(s.faction) ?? 0) + 1);
  }
  let best: FactionId | null = null;
  let bestN = 0;
  let tied = false;
  for (const [faction, n] of counts) {
    if (n > bestN) {
      best = faction;
      bestN = n;
      tied = false;
    } else if (n === bestN) {
      tied = true;
    }
  }
  if (tied || bestN === 0) return null;
  return best;
}

function tickCapture(world: World, dt: number): void {
  for (const asteroid of world.asteroids.values()) {
    const occupier = occupierOf(world, asteroid.id);
    const ownerOrbiters = countOrbitingSeedlings(
      world,
      asteroid.id,
      asteroid.owner,
    );
    const contested =
      occupier !== null &&
      occupier !== asteroid.owner &&
      ownerOrbiters === 0;

    if (!contested) {
      asteroid.burnTimer = 0;
      continue;
    }

    const ownerTrees: Tree[] = [];
    for (const t of world.trees.values()) {
      if (t.asteroidId === asteroid.id && t.faction === asteroid.owner) {
        ownerTrees.push(t);
      }
    }

    if (ownerTrees.length === 0) {
      asteroid.owner = 'neutral';
      asteroid.burnTimer = 0;
      continue;
    }

    asteroid.burnTimer += dt;
    if (asteroid.burnTimer < TREE_BURN_SECONDS) continue;
    asteroid.burnTimer = 0;
    ownerTrees.sort((a, b) => a.maturity - b.maturity);
    const victim = ownerTrees[0]!;
    world.trees.delete(victim.id);
    if (ownerTrees.length <= 1) {
      asteroid.owner = 'neutral';
    }
  }
}

export function tick(world: World, dt: number): void {
  world.time += dt;
  tickEnergy(world, dt);
  tickTrees(world, dt);
  tickShields(world, dt);

  const toDelete: number[] = [];
  const completedPlants = new Set<number>();

  const time = world.time;

  for (const s of world.seedlings.values()) {
    if (s.state === 'sprout') {
      applySproutGlide(s, world, dt);
      continue;
    }

    if (s.state === 'orbit') {
      const asteroid = world.asteroids.get(s.asteroidId);
      if (!asteroid) continue;
      applyOrbit(s, asteroid, dt, time);
      continue;
    }

    if (s.state === 'travel') {
      const home = world.asteroids.get(s.asteroidId);
      if ((s.wait ?? 0) > 0) {
        s.wait = (s.wait ?? 0) - dt;
        if (home) applyOrbit(s, home, dt, time);
        if ((s.wait ?? 0) <= 0) s.heading = s.facing;
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
      const arriveAt = hop.radius + orbitBand(hop.radius);
      const speed = TRAVEL_BASE_SPEED * (0.55 + s.stats.speed / 200);
      const pulse = 0.9 + 0.1 * Math.sin(time * 2.05 + s.phase);
      const step = speed * pulse * dt;
      if (dist <= arriveAt + 8 || dist <= step) {
        s.asteroidId = hopId;
        s.heading = undefined;
        if (pathIndex >= path.length - 1) {
          enterOrbit(s, hop);
        } else {
          s.pathIndex = pathIndex + 1;
        }
      } else {
        glideToward(s, hop.x, hop.y, dist, dx, dy, step, dt, time, 0.5);
      }
      continue;
    }

    if (s.state === 'plant') {
      const home = world.asteroids.get(s.asteroidId);
      if ((s.wait ?? 0) > 0) {
        s.wait = (s.wait ?? 0) - dt;
        if (home) applyOrbit(s, home, dt, time);
        if ((s.wait ?? 0) <= 0) s.heading = s.facing;
        continue;
      }
      const tx = s.plantTargetX ?? s.x;
      const ty = s.plantTargetY ?? s.y;
      const dx = tx - s.x;
      const dy = ty - s.y;
      const dist = Math.hypot(dx, dy);
      const pulse = 0.88 + 0.12 * Math.sin(time * 1.7 + s.phase);
      const step = PLANT_DIVE_SPEED * pulse * dt;
      if (dist <= Math.max(step, 10)) {
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
        glideToward(s, tx, ty, dist, dx, dy, step, dt, time, 0.32);
        s.z += (0 - s.z) * Math.min(1, 3.2 * dt);
      }
    }
  }

  for (const id of toDelete) {
    world.seedlings.delete(id);
  }
  for (const plantId of completedPlants) {
    completePlant(world, plantId);
  }

  resolveCombat(world, dt);
  tickCapture(world, dt);
}
