import { shortestPath } from './graph';
import {
  PLANT_COST,
  PLANT_STAGGER,
  SEND_STAGGER,
  type FactionId,
  type PendingPlant,
  type World,
} from './types';
import {
  allocId,
  countSendReady,
  getOccupiedSlots,
  slotPosition,
  spawnOrbiters,
} from './world';

export type CommandResult =
  | { ok: true; count?: number }
  | { ok: false; reason: string };

export function sendSeedlings(
  world: World,
  fromId: number,
  toId: number,
  count: number,
  faction: FactionId,
): CommandResult {
  if (fromId === toId) return { ok: false, reason: 'same asteroid' };
  if (count < 1) return { ok: false, reason: 'count < 1' };

  const path = shortestPath(world, fromId, toId);
  if (!path || path.length < 2) return { ok: false, reason: 'no path' };

  const available: number[] = [];
  for (const s of world.seedlings.values()) {
    if (
      s.state === 'orbit' &&
      s.asteroidId === fromId &&
      s.faction === faction
    ) {
      available.push(s.id);
    }
  }
  if (available.length === 0) return { ok: false, reason: 'no seedlings' };

  const n = Math.min(count, available.length);
  for (let i = 0; i < n; i++) {
    const s = world.seedlings.get(available[i]!)!;
    s.state = 'travel';
    s.path = path;
    s.pathIndex = 1;
    s.wait = i * SEND_STAGGER;
  }
  return { ok: true, count: n };
}

export function plantDyson(
  world: World,
  asteroidId: number,
  slotIndex: number,
  faction: FactionId,
): CommandResult {
  const asteroid = world.asteroids.get(asteroidId);
  if (!asteroid) return { ok: false, reason: 'no asteroid' };
  if (slotIndex < 0 || slotIndex >= asteroid.treeSlots) {
    return { ok: false, reason: 'bad slot' };
  }

  const occupied = getOccupiedSlots(world, asteroidId);
  if (occupied.has(slotIndex)) return { ok: false, reason: 'slot taken' };

  // Block if another pending plant already targets this slot
  for (const p of world.pendingPlants.values()) {
    if (p.asteroidId === asteroidId && p.slotIndex === slotIndex) {
      return { ok: false, reason: 'slot taken' };
    }
  }

  const candidates: number[] = [];
  for (const s of world.seedlings.values()) {
    if (
      s.state === 'orbit' &&
      s.asteroidId === asteroidId &&
      s.faction === faction
    ) {
      candidates.push(s.id);
    }
  }
  if (candidates.length < PLANT_COST) {
    return { ok: false, reason: 'need 10 seedlings' };
  }

  const pos = slotPosition(asteroid, slotIndex);
  const chosen = candidates.slice(0, PLANT_COST);
  const plantId = allocId(world);
  const pending: PendingPlant = {
    id: plantId,
    asteroidId,
    slotIndex,
    faction,
    seedlingIds: chosen,
    arrived: 0,
  };
  world.pendingPlants.set(plantId, pending);

  for (let i = 0; i < chosen.length; i++) {
    const s = world.seedlings.get(chosen[i]!)!;
    s.state = 'plant';
    s.plantId = plantId;
    s.plantTargetX = pos.x;
    s.plantTargetY = pos.y;
    s.wait = i * PLANT_STAGGER;
  }

  return { ok: true, count: PLANT_COST };
}

export function countFactionOrbiting(
  world: World,
  asteroidId: number,
  faction: FactionId,
): number {
  return countSendReady(world, asteroidId, faction);
}

/** Helper for tests: force-spawn orbiting seedlings on an asteroid. */
export function debugSpawnOrbiters(
  world: World,
  asteroidId: number,
  faction: FactionId,
  n: number,
): void {
  spawnOrbiters(world, asteroidId, faction, n);
}
