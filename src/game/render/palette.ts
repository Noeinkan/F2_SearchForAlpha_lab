/**
 * Eufloria-like palettes are not one swatch — they are a transform.
 *
 * Rule:
 *   1. Pick a key hue (scene atmosphere).
 *   2. Pastelize living color: keep hue, clamp saturation, lift lightness
 *      (tint with white — never neon, never chalk-grey).
 *   3. Wash large areas of the same hue: either a dark void or light paper.
 *   4. Structure (wood, ink) sits on the complement, muted (dusty, mid value).
 *   5. Energy / Strength / Speed mix as yellow / red / green, then pull
 *      toward the scene hue and pastelize — so every asteroid’s flora differs.
 */
import { mulberry32 } from '../sim/rng';
import type { Stats } from '../sim/types';

export type Hex = number;

export interface ScenePalette {
  /** 0–360 */
  hue: number;
  dark: boolean;
  bg: Hex;
  bgA: Hex;
  bgB: Hex;
  bgC: Hex;
  ink: Hex;
  inkSoft: Hex;
  mist: Hex;
  dust: Hex;
}

export interface FloraPalette {
  wood: Hex;
  tuft: Hex;
  flower: Hex;
  root: Hex;
  rootSoft: Hex;
  wing: Hex;
  seedBody: Hex;
  core: Hex;
  coreHot: Hex;
  coreWhite: Hex;
  rock: Hex;
  rockShadow: Hex;
  rockLit: Hex;
  outline: Hex;
  ring: Hex;
}

const PASTEL_S = { min: 0.22, max: 0.46 };
const PASTEL_L = { min: 0.6, max: 0.84 };

export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

export function hexToRgb(hex: Hex): [number, number, number] {
  return [((hex >> 16) & 255) / 255, ((hex >> 8) & 255) / 255, (hex & 255) / 255];
}

export function rgbToHex(r: number, g: number, b: number): Hex {
  const R = Math.round(clamp(r, 0, 1) * 255);
  const G = Math.round(clamp(g, 0, 1) * 255);
  const B = Math.round(clamp(b, 0, 1) * 255);
  return (R << 16) | (G << 8) | B;
}

/** h in 0–360, s/l in 0–1 */
export function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  else if (max === g) h = ((b - r) / d + 2) / 6;
  else h = ((r - g) / d + 4) / 6;
  return [h * 360, s, l];
}

export function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const hue = (((h % 360) + 360) % 360) / 360;
  if (s <= 0) return [l, l, l];
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [hue2rgb(p, q, hue + 1 / 3), hue2rgb(p, q, hue), hue2rgb(p, q, hue - 1 / 3)];
}

function hue2rgb(p: number, q: number, t: number): number {
  let u = t;
  if (u < 0) u += 1;
  if (u > 1) u -= 1;
  if (u < 1 / 6) return p + (q - p) * 6 * u;
  if (u < 1 / 2) return q;
  if (u < 2 / 3) return p + (q - p) * (2 / 3 - u) * 6;
  return p;
}

export function hslToHex(h: number, s: number, l: number): Hex {
  const [r, g, b] = hslToRgb(h, s, l);
  return rgbToHex(r, g, b);
}

export function cssHex(hex: Hex): string {
  return `#${hex.toString(16).padStart(6, '0')}`;
}

export function lerpHue(a: number, b: number, t: number): number {
  const d = ((((b - a) % 360) + 540) % 360) - 180;
  return (a + d * t + 360) % 360;
}

export function hueDistance(a: number, b: number): number {
  return Math.abs(((((b - a) % 360) + 540) % 360) - 180);
}

/**
 * The pastel operator: same hue, chroma in a soft band, value lifted
 * toward white. Works on any input color (title magenta, in-game cyan, …).
 */
export function toPastel(hex: Hex): Hex {
  const [h, s, l] = rgbToHsl(...hexToRgb(hex));
  const s2 = clamp(s * 0.55 + 0.18, PASTEL_S.min, PASTEL_S.max);
  const l2 = clamp(l * 0.35 + 0.58, PASTEL_L.min, PASTEL_L.max);
  return hslToHex(h, s2, l2);
}

/** Dusty mid-value cousin — trunks, ink, tufts. */
export function toMuted(hex: Hex, darkWash: boolean): Hex {
  const [h, s] = rgbToHsl(...hexToRgb(hex));
  const s2 = clamp(s * 0.5 + 0.28, 0.28, 0.5);
  const l2 = darkWash ? 0.5 : 0.36;
  return hslToHex(h, s2, l2);
}

export function isPastel(hex: Hex): boolean {
  const [, s, l] = rgbToHsl(...hexToRgb(hex));
  return s >= PASTEL_S.min - 0.02 && s <= PASTEL_S.max + 0.02 && l >= PASTEL_L.min - 0.02 && l <= PASTEL_L.max + 0.02;
}

/** Strength → red, Speed → green (+ a little blue), Energy → yellow. */
export function mixStatsRgb(stats: Stats): [number, number, number] {
  const e = clamp(stats.energy / 200, 0, 1);
  const k = clamp(stats.strength / 200, 0, 1);
  const v = clamp(stats.speed / 200, 0, 1);
  let r = k + e;
  let g = v + e;
  let b = v * 0.45;
  const m = Math.max(r, g, b, 1e-6);
  return [r / m, g / m, b / m];
}

export function accentHue(stats: Stats, sceneHue: number): number {
  const [h] = rgbToHsl(...mixStatsRgb(stats));
  return lerpHue(h, sceneHue, 0.35);
}

export function createScenePalette(seed: number): ScenePalette {
  const rng = mulberry32(seed >>> 0);
  const hue = rng() * 360;
  // Odd seeds → dark void (in-game), even → light paper (title).
  const dark = (seed & 1) === 1;

  const bgA = dark ? hslToHex(hue, 0.2, 0.08) : hslToHex(hue, 0.12, 0.88);
  const bgB = dark
    ? hslToHex(hue + 26, 0.14, 0.13)
    : hslToHex(hue + 18, 0.1, 0.92);
  const bgC = dark
    ? hslToHex(hue - 38, 0.18, 0.09)
    : hslToHex(hue - 16, 0.14, 0.86);
  const ink = dark ? hslToHex(hue, 0.16, 0.82) : hslToHex(hue + 160, 0.42, 0.28);
  const inkSoft = dark ? hslToHex(hue, 0.12, 0.7) : hslToHex(hue + 160, 0.28, 0.38);
  const mist = toPastel(hslToHex(hue, 0.4, 0.7));
  const dust = toPastel(hslToHex(hue + 50, 0.45, 0.72));

  return { hue, dark, bg: bgB, bgA, bgB, bgC, ink, inkSoft, mist, dust };
}

export function floraPalette(
  stats: Stats,
  seed: number,
  scene: ScenePalette,
): FloraPalette {
  const rng = mulberry32(seed >>> 0);
  const h = accentHue(stats, scene.hue);
  const woodH = (h + 150 + rng() * 36 - 18 + 360) % 360;

  const flower = hslToHex(h, 0.34, scene.dark ? 0.78 : 0.7);
  const wing = hslToHex(h, 0.3, 0.74);
  const seedBody = hslToHex(h, 0.42, 0.4);
  const wood = hslToHex(woodH, 0.38, scene.dark ? 0.52 : 0.34);
  const tuft = hslToHex(woodH, 0.4, scene.dark ? 0.58 : 0.4);
  const root = hslToHex(woodH, 0.48, 0.46);
  const rootSoft = hslToHex(woodH, 0.32, 0.68);
  const core = hslToHex(h, 0.42, 0.72);
  const coreHot = hslToHex(h, 0.5, 0.62);
  const coreWhite = hslToHex(h, 0.12, 0.94);
  const rockH = lerpHue(scene.hue, h, 0.25);
  const rockL = 0.62 + rng() * 0.12;
  const rock = hslToHex(rockH, 0.06 + rng() * 0.05, rockL);
  const rockShadow = hslToHex(rockH, 0.08, rockL - 0.14);
  const rockLit = hslToHex(rockH, 0.05, Math.min(0.88, rockL + 0.12));
  const outline = hslToHex(woodH, 0.18, scene.dark ? 0.28 : 0.26);
  const ring = tuft;

  return {
    wood,
    tuft,
    flower,
    root,
    rootSoft,
    wing,
    seedBody,
    core,
    coreHot,
    coreWhite,
    rock,
    rockShadow,
    rockLit,
    outline,
    ring,
  };
}

export function seedlingColors(
  stats: Stats,
  scene: ScenePalette,
): { wing: Hex; body: Hex } {
  const h = accentHue(stats, scene.hue);
  return {
    wing: hslToHex(h, 0.3, 0.74),
    body: hslToHex(h, 0.42, 0.4),
  };
}

export function applySceneToDocument(scene: ScenePalette): void {
  const root = document.documentElement.style;
  root.setProperty('--ab-bg', cssHex(scene.bg));
  root.setProperty('--ab-ink', cssHex(scene.ink));
  root.setProperty('--ab-ink-soft', cssHex(scene.inkSoft));
}
