import { describe, expect, it } from 'vitest';
import {
  bumpSendCount,
  resolveSendCount,
} from '../../src/game/input/sendCount';

describe('resolveSendCount', () => {
  it('returns 0 when no orbiters', () => {
    expect(resolveSendCount(0, 'all', 99)).toBe(0);
    expect(resolveSendCount(0, 'scout', 1)).toBe(0);
    expect(resolveSendCount(0, 'fixed', 5)).toBe(0);
  });

  it('sends all orbiters in all mode', () => {
    expect(resolveSendCount(12, 'all', 3)).toBe(12);
  });

  it('sends one in scout mode', () => {
    expect(resolveSendCount(12, 'scout', 99)).toBe(1);
  });

  it('clamps fixed count to available orbiters', () => {
    expect(resolveSendCount(10, 'fixed', 4)).toBe(4);
    expect(resolveSendCount(10, 'fixed', 40)).toBe(10);
    expect(resolveSendCount(10, 'fixed', 0)).toBe(0);
    expect(resolveSendCount(10, 'fixed', -3)).toBe(0);
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
});
