import { neighbors } from './graph';
import {
  AI_DEFENSE_TREES_PER_ROCK,
  AI_ENERGY_TREES_PER_ROCK,
  PLANT_COST,
  aiKnobs,
  canPlantKind,
  type FactionId,
  type TreeKind,
  type World,
} from './types';
import { plantTree, sendSeedlings } from './commands';
import {
  countSendReady,
  countTrees,
  getOccupiedSlots,
  hasHostileOrbiters,
} from './world';

const AI_FACTION: FactionId = 'enemy';

/**
 * Rival empire tick: plant Energy/Defense/Dyson, retake home,
 * reinforce threatened rocks, then raid with surplus above garrison.
 */
export function tickAi(world: World, dt: number): void {
  const knobs = aiKnobs(world.difficulty);
  world.aiAcc += dt;
  if (world.aiAcc < knobs.think) return;
  world.aiAcc = 0;

  const held: number[] = [];
  for (const a of world.asteroids.values()) {
    if (a.owner === AI_FACTION) held.push(a.id);
  }
  if (held.length === 0) {
    for (const a of world.asteroids.values()) {
      if (countSendReady(world, a.id, AI_FACTION) >= PLANT_COST) {
        held.push(a.id);
      }
    }
  }

  for (const id of held) {
    tryPlant(world, id, knobs.garrison);
  }

  const homeLost =
    world.aiHomeId !== null &&
    world.asteroids.get(world.aiHomeId)?.owner !== AI_FACTION;

  if (homeLost && world.aiHomeId !== null) {
    for (const id of held) {
      if (id === world.aiHomeId) continue;
      if (trySendSurplus(world, id, world.aiHomeId, knobs)) return;
    }
  }

  const threatened = findThreatened(world, held);
  if (threatened.length > 0) {
    threatened.sort(
      (a, b) =>
        countSendReady(world, a, AI_FACTION) -
        countSendReady(world, b, AI_FACTION),
    );
    const weakest = threatened[0]!;
    for (const id of held) {
      if (id === weakest) continue;
      if (threatened.includes(id)) continue;
      if (trySendSurplus(world, id, weakest, knobs)) return;
    }
  }

  for (const id of held) {
    tryRaid(world, id, knobs);
  }
}

function tryPlant(world: World, asteroidId: number, garrison: number): void {
  const asteroid = world.asteroids.get(asteroidId);
  if (!asteroid) return;
  const ready = countSendReady(world, asteroidId, AI_FACTION);
  if (ready < PLANT_COST) return;

  const occupied = getOccupiedSlots(world, asteroidId);
  if (occupied.size >= asteroid.treeSlots) return;

  const friendlyTrees = countTrees(world, asteroidId, AI_FACTION);
  const friendlyPending = countPending(world, asteroidId);
  const claiming = friendlyTrees === 0 && friendlyPending === 0;
  if (!claiming && ready - PLANT_COST < garrison) return;

  const kind = pickPlantKind(world, asteroidId);
  for (let slot = 0; slot < asteroid.treeSlots; slot++) {
    if (occupied.has(slot)) continue;
    const planted = plantTree(world, asteroidId, slot, AI_FACTION, kind);
    if (planted.ok) return;
  }
}

function pickPlantKind(world: World, asteroidId: number): TreeKind {
  const asteroid = world.asteroids.get(asteroidId)!;
  const energy = asteroid.stats.energy;

  const energyCount =
    countTrees(world, asteroidId, AI_FACTION, 'energy') +
    countPendingKind(world, asteroidId, 'energy');
  if (
    canPlantKind(energy, 'energy') &&
    energyCount < AI_ENERGY_TREES_PER_ROCK
  ) {
    return 'energy';
  }

  const defenseCount =
    countTrees(world, asteroidId, AI_FACTION, 'defense') +
    countPendingKind(world, asteroidId, 'defense');
  if (
    isBorder(world, asteroidId) &&
    canPlantKind(energy, 'defense') &&
    defenseCount < AI_DEFENSE_TREES_PER_ROCK
  ) {
    return 'defense';
  }

  return 'dyson';
}

function isBorder(world: World, asteroidId: number): boolean {
  for (const id of neighbors(world, asteroidId)) {
    const a = world.asteroids.get(id);
    if (!a || a.owner !== AI_FACTION) return true;
  }
  return false;
}

function tryRaid(
  world: World,
  asteroidId: number,
  knobs: { garrison: number; raid: number },
): void {
  const ready = countSendReady(world, asteroidId, AI_FACTION);
  if (ready <= knobs.garrison) return;

  const raid = Math.min(knobs.raid, ready - knobs.garrison);
  const target = pickRaidTarget(world, asteroidId);
  if (target === null) return;
  sendSeedlings(world, asteroidId, target, raid, AI_FACTION);
}

function trySendSurplus(
  world: World,
  fromId: number,
  toId: number,
  knobs: { garrison: number; raid: number },
): boolean {
  const ready = countSendReady(world, fromId, AI_FACTION);
  if (ready <= knobs.garrison) return false;
  const n = Math.min(knobs.raid, ready - knobs.garrison);
  const result = sendSeedlings(world, fromId, toId, n, AI_FACTION);
  return result.ok;
}

function findThreatened(world: World, held: number[]): number[] {
  const out: number[] = [];
  for (const id of held) {
    if (isThreatened(world, id)) out.push(id);
  }
  return out;
}

function isThreatened(world: World, asteroidId: number): boolean {
  if (hasHostileOrbiters(world, asteroidId, AI_FACTION)) return true;
  for (const id of neighbors(world, asteroidId)) {
    const a = world.asteroids.get(id);
    if (a?.owner === 'player') return true;
  }
  return false;
}

function pickRaidTarget(world: World, fromId: number): number | null {
  const hops = neighbors(world, fromId);
  let best: number | null = null;
  let bestScore = -Infinity;
  for (const id of hops) {
    const a = world.asteroids.get(id);
    if (!a || a.owner === AI_FACTION) continue;
    const defenders = countSendReady(
      world,
      id,
      a.owner === 'neutral' ? 'grey' : a.owner,
    );
    const playerDef = countSendReady(world, id, 'player');
    const greyDef = countSendReady(world, id, 'grey');
    const totalDef = Math.max(defenders, playerDef + greyDef);
    let score = 40 - totalDef;
    if (a.owner === 'player') score += 12;
    if (a.owner === 'neutral' || a.owner === 'grey') score += 6;
    score += a.minerals * 0.08;
    if (score > bestScore) {
      bestScore = score;
      best = id;
    }
  }
  return best;
}

function countPending(world: World, asteroidId: number): number {
  let n = 0;
  for (const p of world.pendingPlants.values()) {
    if (p.asteroidId === asteroidId && p.faction === AI_FACTION) n++;
  }
  return n;
}

function countPendingKind(
  world: World,
  asteroidId: number,
  kind: TreeKind,
): number {
  let n = 0;
  for (const p of world.pendingPlants.values()) {
    if (
      p.asteroidId === asteroidId &&
      p.faction === AI_FACTION &&
      p.kind === kind
    ) {
      n++;
    }
  }
  return n;
}
