/** Persistent player prefs — localStorage with safe fallbacks. */

export const MUTE_STORAGE_KEY = 'asterbloom.mute.v1';
export const REDUCED_MOTION_STORAGE_KEY = 'asterbloom.reducedMotion.v1';

/** Ship version — keep in sync with package.json. */
export const GAME_VERSION = '0.1.0';

function storageGet(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(key, value);
  } catch {
    /* ignore quota / private mode */
  }
}

export function readMuted(): boolean {
  return storageGet(MUTE_STORAGE_KEY) === '1';
}

export function writeMuted(muted: boolean): void {
  storageSet(MUTE_STORAGE_KEY, muted ? '1' : '0');
}

export function readReducedMotion(): boolean {
  return storageGet(REDUCED_MOTION_STORAGE_KEY) === '1';
}

export function writeReducedMotion(enabled: boolean): void {
  storageSet(REDUCED_MOTION_STORAGE_KEY, enabled ? '1' : '0');
}

export function applyReducedMotionClass(enabled: boolean): void {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('ab-reduced-motion', enabled);
}
