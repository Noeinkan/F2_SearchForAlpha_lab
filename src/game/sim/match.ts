/** Match outcome — pure sim, no Pixi. */

import { PLANT_COST, type FactionId, type World } from './types';

export type MatchStatus = 'playing' | 'won' | 'lost';

export type WinRule =
  | { kind: 'eliminate' }
  | { kind: 'hold'; rocks: number; seconds: number }
  | { kind: 'claimEnergyWell'; asteroidId: number };

export interface MatchConfig {
  win: WinRule;
}

/** Continuous hold progress for hold win rules. */
export interface MatchRuntime {
  holdAcc: number;
}

export function createMatchRuntime(): MatchRuntime {
  return { holdAcc: 0 };
}

export const DEFAULT_MATCH_CONFIG: MatchConfig = {
  win: { kind: 'eliminate' },
};

function countTreesFor(world: World, faction: FactionId): number {
  let n = 0;
  for (const t of world.trees.values()) {
    if (t.faction === faction) n++;
  }
  return n;
}

function countPendingFor(world: World, faction: FactionId): number {
  let n = 0;
  for (const p of world.pendingPlants.values()) {
    if (p.faction === faction) n++;
  }
  return n;
}

function countLivingSeedlings(world: World, faction: FactionId): number {
  let n = 0;
  for (const s of world.seedlings.values()) {
    if (s.faction === faction) n++;
  }
  return n;
}

function countOwnedRocks(world: World, faction: FactionId): number {
  let n = 0;
  for (const a of world.asteroids.values()) {
    if (a.owner === faction) n++;
  }
  return n;
}

/**
 * Advance hold timer when the player meets the rock count; reset otherwise.
 * Call each sim step with the same dt as `tick`.
 */
export function tickMatchRuntime(
  world: World,
  config: MatchConfig,
  runtime: MatchRuntime,
  dt: number,
): void {
  if (config.win.kind !== 'hold') {
    runtime.holdAcc = 0;
    return;
  }
  const owned = countOwnedRocks(world, 'player');
  if (owned >= config.win.rocks) {
    runtime.holdAcc += dt;
  } else {
    runtime.holdAcc = 0;
  }
}

function winConditionMet(
  world: World,
  config: MatchConfig,
  runtime: MatchRuntime,
): boolean {
  const win = config.win;
  if (win.kind === 'eliminate') {
    const enemyTrees = countTreesFor(world, 'enemy');
    const enemyPending = countPendingFor(world, 'enemy');
    return enemyTrees === 0 && enemyPending === 0;
  }
  if (win.kind === 'hold') {
    return runtime.holdAcc >= win.seconds;
  }
  // claimEnergyWell
  const rock = world.asteroids.get(win.asteroidId);
  if (!rock || rock.owner !== 'player') return false;
  return countTreesFor(world, 'player') > 0 &&
    [...world.trees.values()].some(
      (t) => t.asteroidId === win.asteroidId && t.faction === 'player',
    );
}

/**
 * Lose: player has no trees, no pending plants, and fewer than PLANT_COST seedlings
 * (orbit / sprout / travel / plant all count). Checked before win so mutual wipe is a loss.
 * Win: depends on MatchConfig.win (default eliminate).
 */
export function matchStatus(
  world: World,
  config: MatchConfig = DEFAULT_MATCH_CONFIG,
  runtime: MatchRuntime = createMatchRuntime(),
): MatchStatus {
  const playerTrees = countTreesFor(world, 'player');
  const playerPending = countPendingFor(world, 'player');
  const playerSeedlings = countLivingSeedlings(world, 'player');

  if (
    playerTrees === 0 &&
    playerPending === 0 &&
    playerSeedlings < PLANT_COST
  ) {
    return 'lost';
  }

  if (winConditionMet(world, config, runtime)) {
    return 'won';
  }

  return 'playing';
}
