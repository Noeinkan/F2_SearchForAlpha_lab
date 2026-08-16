/** Pure simulation types — no Pixi imports. */

export type FactionId = 'player' | 'neutral' | 'enemy' | 'grey';

export type TreeKind = 'dyson' | 'energy' | 'defense';

export type SeedlingKind = 'basic' | 'sentinel';

export type SeedlingState = 'sprout' | 'orbit' | 'travel' | 'plant';

export interface Stats {
  energy: number;
  strength: number;
  speed: number;
}

export interface Asteroid {
  id: number;
  name: string;
  x: number;
  y: number;
  radius: number;
  travelRadius: number;
  /** Fertility: more minerals → more tree slots and faster seedling production. */
  minerals: number;
  treeSlots: number;
  stats: Stats;
  owner: FactionId;
  seed: number;
  /**
   * Core HP unused: Phase 4 left siege-the-core off.
   * Capture stays burn-then-plant.
   */
  coreEnergy: number;
  maxCoreEnergy: number;
  /** Regenerating pool used by Sentinels and shields. */
  energyPool: number;
  maxEnergyPool: number;
  shield: number;
  maxShield: number;
  /** Seconds occupying seedlings have been burning undefended trees. */
  burnTimer: number;
}

export interface Tree {
  id: number;
  asteroidId: number;
  slotIndex: number;
  kind: TreeKind;
  seed: number;
  /** 0..1 growth progress */
  maturity: number;
  faction: FactionId;
  spawnAccumulator: number;
  /** How well adult roots reached the core well (0..1), baked at plant time. */
  coreFeed: number;
}

export interface Seedling {
  id: number;
  asteroidId: number;
  faction: FactionId;
  kind: SeedlingKind;
  stats: Stats;
  hp: number;
  maxHp: number;
  state: SeedlingState;
  /** Orbit angle radians */
  angle: number;
  orbitRadius: number;
  orbitSpeed: number;
  x: number;
  y: number;
  /** Camera-depth; +z is toward the viewer, 0 is the equatorial plane. */
  z: number;
  /** Orbital-plane tilt for 3D planet-glide (radians). */
  inclination?: number;
  /** Longitude where the orbit crosses the equator (radians). */
  orbitNode?: number;
  /** Render heading, radians. */
  facing: number;
  /** Unique phase for breeze / glide (radians). */
  phase: number;
  /** Per-seed orbit radius offset. */
  orbitBias?: number;
  /** Smoothed travel / dive heading. */
  heading?: number;
  sproutAge?: number;
  sproutDuration?: number;
  sproutFromX?: number;
  sproutFromY?: number;
  sproutTipAngle?: number;
  /** Seconds before travel/plant motion starts (streamed peel-off). */
  wait?: number;
  /** Asteroid id path including destination; next hop is path[pathIndex]. */
  path?: number[];
  pathIndex?: number;
  /** Pending plant this seedling is diving for. */
  plantId?: number;
  plantTargetX?: number;
  plantTargetY?: number;
}

export interface PendingPlant {
  id: number;
  asteroidId: number;
  slotIndex: number;
  faction: FactionId;
  kind: TreeKind;
  seedlingIds: number[];
  arrived: number;
}

export type Difficulty = 'easy' | 'normal' | 'hard';

export interface World {
  asteroids: Map<number, Asteroid>;
  trees: Map<number, Tree>;
  seedlings: Map<number, Seedling>;
  pendingPlants: Map<number, PendingPlant>;
  nextId: number;
  seed: number;
  time: number;
  aiAcc: number;
  /** Enemy starting rock; AI prioritizes retaking it when lost. */
  aiHomeId: number | null;
  /** Skirmish / campaign AI tempo. */
  difficulty: Difficulty;
}

/** Continuous rock size range. Layout skews toward the small end. */
export const ROCK_RADIUS_MIN = 97;
export const ROCK_RADIUS_MAX = 181;
/** Player home disc vs the same size roll without this scale. */
export const HOME_RADIUS_SCALE = 1.3;
/** Fallback when a fixture omits radius. */
export const ROCK_RADIUS_DEFAULT = 124;
/** Minimum rim gap kept between discs when laying out a map. */
export const ROCK_GAP = 48;
/** Tree collar sits this fraction of mean radius in from the local rim. */
export const ROCK_SURFACE_INSET = 0.18;
/**
 * Adult spine height at scale 1 (`buildAdultTree`). Groves are sized as a
 * fraction of disc radius so the rock stays the larger body.
 */
export const TREE_SPINE_HEIGHT = 148;
/** Mature tree (spine + canopy) as a fraction of mean disc radius. */
export const TREE_TO_ROCK = 0.62;

export function treeVisualScale(radius: number, seed = 0): number {
  const wobble =
    seed === 0
      ? 0
      : (((Math.imul(seed ^ 0x27d4eb2d, 0x9e3779b9) >>> 8) & 255) / 255) *
          0.06 -
        0.03;
  return (TREE_TO_ROCK * radius) / TREE_SPINE_HEIGHT + wobble;
}

/** Phase 4 pacing: opening scout, mid wells/chokes, late fights not mopping. */
export const LOCAL_SEEDLING_CAP = 24;
export const DYSON_GROWTH_SECONDS = 20;
export const ENERGY_GROWTH_SECONDS = 24;
export const DEFENSE_GROWTH_SECONDS = 16;
export const DYSON_SPAWN_INTERVAL = 1.7;
export const ENERGY_SPAWN_INTERVAL = 2.0;
/** Maturity when canopy blooms open and seedlings may begin to drop. */
export const SPAWN_START_MATURITY = 0.55;
export const PLANT_COST = 10;
export const TRAVEL_BASE_SPEED = 96;
export const PLANT_DIVE_SPEED = 78;
export const ORBIT_BAND = 16;

export function orbitBand(radius: number): number {
  return ORBIT_BAND + radius * 0.14;
}
export const SEND_STAGGER = 0.07;
export const PLANT_STAGGER = 0.05;
export const SPROUT_DURATION = 3.2;

export const ENERGY_TREE_MIN_ENERGY = 70;
export const DEFENSE_TREE_MIN_ENERGY = 50;
export const SENTINEL_UPKEEP = 2.2;
export const SENTINEL_SPAWN_ENERGY = 6;
export const SENTINEL_STARVE_DPS = 4;
export const ENERGY_REGEN_BASE = 2.4;
/** Max spawn-rate boost when roots fully feed from the core. */
export const ROOT_FEED_SPAWN_BONUS = 0.18;
/** Extra energy-pool regen per second from one fully fed mature tree. */
export const ROOT_FEED_REGEN = 0.35;
export const COMBAT_RANGE = 28;
export const BASIC_HP = 12;
export const SENTINEL_HP = 34;
export const BASIC_DPS = 3.8;
export const SENTINEL_DPS = 11.5;
export const SHIELD_PER_DEFENSE = 72;
export const TREE_BURN_SECONDS = 4.8;
/** AI difficulty: seconds between empire decisions (normal baseline). */
export const AI_THINK_INTERVAL = 7.5;
/** AI difficulty: orbiters kept on a held rock before raiding/planting. */
export const AI_GARRISON = 10;
/** AI difficulty: max seedlings sent per raid. */
export const AI_RAID = 6;
/** Cap Energy trees per rock so Sentinels are not starved by over-planting. */
export const AI_ENERGY_TREES_PER_ROCK = 1;
/** Cap Defense trees per border rock. */
export const AI_DEFENSE_TREES_PER_ROCK = 1;

export function aiKnobs(d: Difficulty): {
  think: number;
  garrison: number;
  raid: number;
} {
  if (d === 'easy') {
    return { think: 10, garrison: 12, raid: 4 };
  }
  if (d === 'hard') {
    return { think: 5, garrison: 8, raid: 8 };
  }
  return {
    think: AI_THINK_INTERVAL,
    garrison: AI_GARRISON,
    raid: AI_RAID,
  };
}

export function mineralsToSlots(minerals: number): number {
  return Math.max(2, Math.min(6, 2 + Math.floor(minerals / 22)));
}

export function energyCapacity(energy: number): number {
  return 20 + energy * 0.45;
}

export function canPlantKind(energy: number, kind: TreeKind): boolean {
  if (kind === 'energy') return energy >= ENERGY_TREE_MIN_ENERGY;
  if (kind === 'defense') return energy >= DEFENSE_TREE_MIN_ENERGY;
  return true;
}
