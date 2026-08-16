import { SpatialHash } from './spatial';
import {
  BASIC_DPS,
  BASIC_HP,
  COMBAT_RANGE,
  SENTINEL_DPS,
  SENTINEL_HP,
  type FactionId,
  type Seedling,
  type SeedlingKind,
  type World,
} from './types';

export function isHostile(a: FactionId, b: FactionId): boolean {
  return a !== b;
}

export function seedlingMaxHp(kind: SeedlingKind, strength: number): number {
  const base = kind === 'sentinel' ? SENTINEL_HP : BASIC_HP;
  return base * (0.7 + strength / 250);
}

export function seedlingDps(kind: SeedlingKind, strength: number): number {
  const base = kind === 'sentinel' ? SENTINEL_DPS : BASIC_DPS;
  return base * (0.7 + strength / 250);
}

function isOrbiting(s: Seedling): boolean {
  return s.state === 'orbit' || (s.state === 'travel' && (s.wait ?? 0) > 0);
}

function canFight(s: Seedling): boolean {
  return s.state === 'orbit' || s.state === 'travel';
}

function nearestHostile(
  s: Seedling,
  others: Seedling[],
): Seedling | null {
  let best: Seedling | null = null;
  let bestD = Infinity;
  for (const other of others) {
    if (other.id === s.id) continue;
    if (!canFight(other)) continue;
    if (!isHostile(s.faction, other.faction)) continue;
    const d = (other.x - s.x) ** 2 + (other.y - s.y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = other;
    }
  }
  return best;
}

function absorbShield(
  world: World,
  target: Seedling,
  damage: number,
): number {
  if (damage <= 0) return 0;
  if (!isOrbiting(target)) return damage;
  const asteroid = world.asteroids.get(target.asteroidId);
  if (!asteroid || asteroid.owner !== target.faction || asteroid.shield <= 0) {
    return damage;
  }
  const absorbed = Math.min(damage, asteroid.shield);
  asteroid.shield -= absorbed;
  return damage - absorbed;
}

function addHit(
  incoming: Map<number, number>,
  face: Map<number, number>,
  attacker: Seedling,
  target: Seedling,
  dt: number,
): void {
  const dps = seedlingDps(attacker.kind, attacker.stats.strength);
  incoming.set(target.id, (incoming.get(target.id) ?? 0) + dps * dt);
  face.set(attacker.id, Math.atan2(target.y - attacker.y, target.x - attacker.x));
}

/**
 * Real-time combat. Co-orbiters on the same rock always fight (mass + type
 * decide). Travelers only clash when they actually meet in space.
 */
export function resolveCombat(world: World, dt: number): void {
  const incoming = new Map<number, number>();
  const face = new Map<number, number>();

  const byRock = new Map<number, Seedling[]>();
  const inFlight: Seedling[] = [];
  for (const s of world.seedlings.values()) {
    if (!canFight(s)) continue;
    if (isOrbiting(s)) {
      const list = byRock.get(s.asteroidId);
      if (list) list.push(s);
      else byRock.set(s.asteroidId, [s]);
    } else {
      inFlight.push(s);
    }
  }

  for (const group of byRock.values()) {
    let mixed = false;
    const faction0 = group[0]?.faction;
    for (const s of group) {
      if (s.faction !== faction0) {
        mixed = true;
        break;
      }
    }
    if (!mixed) continue;
    for (const s of group) {
      const target = nearestHostile(s, group);
      if (target) addHit(incoming, face, s, target, dt);
    }
  }

  if (inFlight.length > 0) {
    const hash = new SpatialHash(COMBAT_RANGE * 2);
    for (const s of inFlight) hash.insert(s.id, s.x, s.y);
    for (const s of inFlight) {
      const nearby = hash.query(s.x, s.y, COMBAT_RANGE, world.seedlings);
      const target = nearestHostile(s, nearby);
      if (target) addHit(incoming, face, s, target, dt);
    }
  }

  for (const [id, heading] of face) {
    const s = world.seedlings.get(id);
    if (s) s.facing = heading;
  }

  const dead: number[] = [];
  for (const [id, raw] of incoming) {
    const s = world.seedlings.get(id);
    if (!s) continue;
    s.hp -= absorbShield(world, s, raw);
    if (s.hp <= 0) dead.push(id);
  }
  for (const id of dead) world.seedlings.delete(id);
}
