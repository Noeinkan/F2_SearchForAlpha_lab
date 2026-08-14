/** Pure simulation types — no Pixi imports. */

export type FactionId = 'player' | 'neutral' | 'enemy' | 'grey';

export type TreeKind = 'dyson' | 'defense';

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
  treeSlots: number;
  stats: Stats;
  owner: FactionId;
  seed: number;
  /** Core HP for capture (future); sandbox keeps full. */
  coreEnergy: number;
  maxCoreEnergy: number;
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
}

export interface Seedling {
  id: number;
  asteroidId: number;
  faction: FactionId;
  stats: Stats;
  state: SeedlingState;
  /** Orbit angle radians */
  angle: number;
  orbitRadius: number;
  orbitSpeed: number;
  x: number;
  y: number;
  /** Render heading, radians. */
  facing: number;
  sproutAge?: number;
  sproutDuration?: number;
  sproutFromX?: number;
  sproutFromY?: number;
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
  seedlingIds: number[];
  arrived: number;
}

export interface World {
  asteroids: Map<number, Asteroid>;
  trees: Map<number, Tree>;
  seedlings: Map<number, Seedling>;
  pendingPlants: Map<number, PendingPlant>;
  nextId: number;
  seed: number;
  time: number;
}

export const LOCAL_SEEDLING_CAP = 40;
export const DYSON_GROWTH_SECONDS = 20;
export const DYSON_SPAWN_INTERVAL = 0.9;
export const PLANT_COST = 10;
export const TRAVEL_BASE_SPEED = 110;
export const PLANT_DIVE_SPEED = 95;
export const ORBIT_BAND = 26;
export const SEND_STAGGER = 0.07;
export const PLANT_STAGGER = 0.05;
export const SPROUT_DURATION = 1.15;
