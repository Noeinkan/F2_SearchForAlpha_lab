import { afterEach, describe, expect, it } from 'vitest';
import {
  GAME_VERSION,
  MUTE_STORAGE_KEY,
  REDUCED_MOTION_STORAGE_KEY,
  readMuted,
  readReducedMotion,
  writeMuted,
  writeReducedMotion,
} from '../../src/game/hud/prefs';

const memory = new Map<string, string>();

afterEach(() => {
  memory.clear();
});

describe('prefs', () => {
  it('ships version 0.1.0', () => {
    expect(GAME_VERSION).toBe('0.1.0');
  });

  it('round-trips mute and reduced motion when localStorage is available', () => {
    const store: Storage = {
      get length() {
        return memory.size;
      },
      clear() {
        memory.clear();
      },
      getItem(key: string) {
        return memory.has(key) ? memory.get(key)! : null;
      },
      key(index: number) {
        return [...memory.keys()][index] ?? null;
      },
      removeItem(key: string) {
        memory.delete(key);
      },
      setItem(key: string, value: string) {
        memory.set(key, String(value));
      },
    };

    const prev = globalThis.localStorage;
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: store,
    });

    try {
      expect(readMuted()).toBe(false);
      writeMuted(true);
      expect(readMuted()).toBe(true);
      expect(memory.get(MUTE_STORAGE_KEY)).toBe('1');
      writeMuted(false);
      expect(readMuted()).toBe(false);

      expect(readReducedMotion()).toBe(false);
      writeReducedMotion(true);
      expect(readReducedMotion()).toBe(true);
      expect(memory.get(REDUCED_MOTION_STORAGE_KEY)).toBe('1');
      writeReducedMotion(false);
      expect(readReducedMotion()).toBe(false);
    } finally {
      Object.defineProperty(globalThis, 'localStorage', {
        configurable: true,
        value: prev,
      });
    }
  });
});
