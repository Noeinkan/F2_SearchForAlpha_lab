import { describe, expect, it } from 'vitest';
import {
  adjustSendCount,
  bumpSendCount,
  closestPreset,
  resolveSendCount,
  resolveSendExact,
} from '../../src/game/input/sendCount';

describe('resolveSendCount', () => {
  it('returns 0 when no orbiters', () => {
    expect(resolveSendCount(0, 'all', 99)).toBe(0);
    expect(resolveSendCount(0, 'scout', 1)).toBe(0);
    expect(resolveSendCount(0, 'half', 1)).toBe(0);
    expect(resolveSendCount(0, 'fixed', 5)).toBe(0);
  });

  it('sends all orbiters in all mode', () => {
    expect(resolveSendCount(12, 'all', 3)).toBe(12);
  });

  it('sends one in scout mode', () => {
    expect(resolveSendCount(12, 'scout', 99)).toBe(1);
  });

  it('sends half rounded up in half mode', () => {
    expect(resolveSendCount(1, 'half', 0)).toBe(1);
    expect(resolveSendCount(6, 'half', 0)).toBe(3);
    expect(resolveSendCount(7, 'half', 0)).toBe(4);
    expect(resolveSendCount(12, 'half', 0)).toBe(6);
  });

  it('clamps fixed count to available orbiters', () => {
    expect(resolveSendCount(10, 'fixed', 4)).toBe(4);
    expect(resolveSendCount(10, 'fixed', 40)).toBe(10);
    expect(resolveSendCount(10, 'fixed', 0)).toBe(0);
    expect(resolveSendCount(10, 'fixed', -3)).toBe(0);
  });
});

describe('resolveSendExact', () => {
  it('clamps a target count to the available orbiters', () => {
    expect(resolveSendExact(0, 5)).toBe(0);
    expect(resolveSendExact(10, 4)).toBe(4);
    expect(resolveSendExact(10, 40)).toBe(10);
    expect(resolveSendExact(10, -2)).toBe(0);
  });

  it('ignores fractional inputs', () => {
    expect(resolveSendExact(10, 3.7)).toBe(3);
  });
});

describe('adjustSendCount', () => {
  it('returns 0 when empty', () => {
    expect(adjustSendCount(0, 5, 1)).toBe(0);
  });

  it('clamps between 0 and max', () => {
    expect(adjustSendCount(10, 5, 1)).toBe(6);
    expect(adjustSendCount(10, 5, -1)).toBe(4);
    expect(adjustSendCount(10, 10, 1)).toBe(10);
    expect(adjustSendCount(10, 0, -1)).toBe(0);
  });

  it('allows jumping by negative offsets', () => {
    expect(adjustSendCount(10, 5, -10)).toBe(0);
  });
});

describe('bumpSendCount', () => {
  it('returns 0 when empty', () => {
    expect(bumpSendCount(0, 5, 1)).toBe(0);
  });

  it('clamps between 1 and max', () => {
    expect(bumpSendCount(10, 5, 1)).toBe(6);
    expect(bumpSendCount(10, 5, -1)).toBe(4);
    expect(bumpSendCount(10, 10, 1)).toBe(10);
    expect(bumpSendCount(10, 1, -1)).toBe(1);
  });

  it('stays at 1 when stepping down past 1', () => {
    expect(bumpSendCount(10, 1, -5)).toBe(1);
  });
});

describe('closestPreset', () => {
  it('returns fixed when no orbiters', () => {
    expect(closestPreset(0, 0)).toBe('fixed');
  });

  it('matches scout, half, all when count matches', () => {
    expect(closestPreset(12, 1)).toBe('scout');
    expect(closestPreset(12, 6)).toBe('half');
    expect(closestPreset(12, 12)).toBe('all');
  });

  it('falls back to fixed for arbitrary counts', () => {
    expect(closestPreset(12, 5)).toBe('fixed');
    expect(closestPreset(12, 7)).toBe('fixed');
  });
});
