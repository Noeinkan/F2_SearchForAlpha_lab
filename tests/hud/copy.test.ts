import { describe, expect, it } from 'vitest';
import {
  commandReasonCopy,
  factionLabel,
  FIRST_RUN_STEPS,
  treeKindLockReason,
} from '../../src/game/hud/copy';
import {
  DEFENSE_TREE_MIN_ENERGY,
  ENERGY_TREE_MIN_ENERGY,
} from '../../src/game/sim/types';

describe('factionLabel', () => {
  it('maps factions to player copy without grey or neutral', () => {
    expect(factionLabel('player')).toBe('You');
    expect(factionLabel('grey')).toBe('Wild');
    expect(factionLabel('enemy')).toBe('Enemy');
    expect(factionLabel('neutral')).toBe('Empty');
    for (const id of ['player', 'grey', 'enemy', 'neutral'] as const) {
      const label = factionLabel(id);
      expect(label.toLowerCase()).not.toContain('grey');
      expect(label.toLowerCase()).not.toContain('neutral');
    }
  });
});

describe('FIRST_RUN_STEPS', () => {
  it('uses tap/drag language that works for touch and mouse', () => {
    expect(FIRST_RUN_STEPS).toHaveLength(3);
    expect(FIRST_RUN_STEPS[0]).toMatch(/Tap a rock/i);
    expect(FIRST_RUN_STEPS[1]).toMatch(/Drag/i);
    expect(FIRST_RUN_STEPS[2]).toMatch(/Tap a glowing slot/i);
  });
});

describe('commandReasonCopy', () => {
  it('covers roadmap failure cases', () => {
    expect(commandReasonCopy('need 10 seedlings')).toBe(
      'Need 10 seedlings to plant',
    );
    expect(commandReasonCopy('contested')).toBe('The rock is still contested');
    expect(commandReasonCopy('no path')).toBe('No path between those rocks');
    expect(commandReasonCopy('need energy-rich rock')).toBe(
      'Not energy-rich enough for Energy trees',
    );
  });

  it('passes through unknown reasons', () => {
    expect(commandReasonCopy('mysterious')).toBe('mysterious');
  });
});

describe('treeKindLockReason', () => {
  it('explains locked Energy and Defense on low-energy rocks', () => {
    const low = ENERGY_TREE_MIN_ENERGY - 10;
    expect(treeKindLockReason(low, 'energy')).toMatch(/Energy trees need/);
    expect(treeKindLockReason(low, 'energy')).toContain(String(ENERGY_TREE_MIN_ENERGY));
    expect(treeKindLockReason(DEFENSE_TREE_MIN_ENERGY - 5, 'defense')).toMatch(
      /Defense trees need/,
    );
    expect(treeKindLockReason(ENERGY_TREE_MIN_ENERGY, 'energy')).toBeNull();
    expect(treeKindLockReason(DEFENSE_TREE_MIN_ENERGY, 'defense')).toBeNull();
    expect(treeKindLockReason(0, 'dyson')).toBeNull();
  });
});
