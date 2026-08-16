import { describe, expect, it } from 'vitest';
import {
  CAMPAIGN_MAPS,
  startCampaignMap,
} from '../../src/game/sim/campaign';
import { isGraphConnected } from '../../src/game/sim/graph';
import { aiKnobs } from '../../src/game/sim/types';

describe('campaign maps', () => {
  it('defines eight authored maps', () => {
    expect(CAMPAIGN_MAPS).toHaveLength(8);
  });

  it('builds a connected graph with a player home for every map', () => {
    for (let i = 0; i < CAMPAIGN_MAPS.length; i++) {
      const started = startCampaignMap(i);
      expect(isGraphConnected(started.world)).toBe(true);
      const home = [...started.world.asteroids.values()].find(
        (a) => a.owner === 'player',
      );
      expect(home).toBeTruthy();
      expect(started.config.win).toBeTruthy();
      expect(started.title).toBe(CAMPAIGN_MAPS[i]!.title);
    }
  });

  it('exposes a claimEnergyWell target on Energy Claim', () => {
    const idx = CAMPAIGN_MAPS.findIndex((m) => m.id === 'energy-claim');
    expect(idx).toBeGreaterThanOrEqual(0);
    const started = startCampaignMap(idx);
    expect(started.config.win.kind).toBe('claimEnergyWell');
    if (started.config.win.kind === 'claimEnergyWell') {
      const rock = started.world.asteroids.get(started.config.win.asteroidId);
      expect(rock).toBeTruthy();
      expect(rock!.owner).not.toBe('player');
    }
  });
});

describe('aiKnobs', () => {
  it('makes easy slower and smaller than hard', () => {
    const easy = aiKnobs('easy');
    const hard = aiKnobs('hard');
    const normal = aiKnobs('normal');
    expect(easy.think).toBeGreaterThan(normal.think);
    expect(hard.think).toBeLessThan(normal.think);
    expect(easy.raid).toBeLessThan(hard.raid);
    expect(easy.garrison).toBeGreaterThan(hard.garrison);
  });
});
