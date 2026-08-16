/** Player-facing strings — never print sim ids like grey / neutral. */

import {
  canPlantKind,
  DEFENSE_TREE_MIN_ENERGY,
  ENERGY_TREE_MIN_ENERGY,
  type FactionId,
  type TreeKind,
} from '../sim/types';

export function factionLabel(faction: FactionId): string {
  switch (faction) {
    case 'player':
      return 'You';
    case 'grey':
      return 'Wild';
    case 'enemy':
      return 'Enemy';
    case 'neutral':
      return 'Empty';
  }
}

const REASON_COPY: Record<string, string> = {
  'same asteroid': 'Pick a different rock to send to',
  'count < 1': 'No seedlings to send',
  'no path': 'No path between those rocks',
  'no seedlings': 'No seedlings to send',
  'no asteroid': 'That rock is gone',
  'bad slot': 'That planting slot is not available',
  'need energy-rich rock': 'Not energy-rich enough for Energy trees',
  'need energy for shields': 'Not enough Energy here for Defense trees',
  contested: 'The rock is still contested',
  'enemy trees': 'Enemy trees still stand — wait for them to burn',
  'slot taken': 'That slot already has a tree',
  'need 10 seedlings': 'Need 10 seedlings to plant',
};

export function commandReasonCopy(reason: string): string {
  return REASON_COPY[reason] ?? reason;
}

/** Why Energy (2) or Defense (3) cannot be planted on this rock's energy stat. */
export function treeKindLockReason(
  rockEnergy: number,
  kind: TreeKind,
): string | null {
  if (kind === 'dyson') return null;
  if (canPlantKind(rockEnergy, kind)) return null;
  if (kind === 'energy') {
    return `Energy trees need Energy ${ENERGY_TREE_MIN_ENERGY}+ (this rock is ${Math.round(rockEnergy)})`;
  }
  return `Defense trees need Energy ${DEFENSE_TREE_MIN_ENERGY}+ (this rock is ${Math.round(rockEnergy)})`;
}

export function plantKindLabel(kind: TreeKind): string {
  if (kind === 'energy') return 'Energy';
  if (kind === 'defense') return 'Defense';
  return 'Dyson';
}

export const CONTROLS_HINT =
  'tap or click a rock · drag to send · tap a glowing slot (10) to plant · pause / Esc · M mute · F follow';

export const FIRST_RUN_STORAGE_KEY = 'asterbloom.firstRun.v1';

export const FIRST_RUN_STEPS = [
  'Tap a rock to select it',
  'Drag to another rock to send seedlings',
  'Tap a glowing slot to plant (needs 10)',
] as const;

export function difficultyLabel(d: 'easy' | 'normal' | 'hard'): string {
  if (d === 'easy') return 'Easy';
  if (d === 'hard') return 'Hard';
  return 'Normal';
}

export function endWinCopy(mode: 'skirmish' | 'campaign', mapTitle?: string): string {
  if (mode === 'campaign' && mapTitle) {
    return `${mapTitle} is yours.`;
  }
  return 'The grove is yours. The last hostile trees have fallen.';
}

export function endLoseCopy(): string {
  return 'The grove is gone. Too few seedlings remain to plant again.';
}

export function campaignCompleteCopy(): string {
  return 'Campaign complete. Every grove is yours.';
}
