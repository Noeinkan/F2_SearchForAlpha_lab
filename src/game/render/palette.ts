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
 *   6. Roots glow: bioluminescent filaments seeking the energy well. Warm amber
 *      bloom reads on dark rock; a slightly deeper spine keeps them from
 *      dissolving into coreWhite. Never mint-wash, never umber-into-rock.
 *      Sap rises from the nucleus through roots, trunk, branches, then crust grass.
 */
import { mulberry32 } from '../sim/rng';
import type { FactionId, SeedlingKind, Stats } from '../sim/types';

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
  leaf: Hex;
  grass: Hex;
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
  stain: Hex;
  outline: Hex;
  ring: Hex;
  /** Living crust film — pollen stain, planet-colored, not generic green. */
  film: Hex;
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

/** Linear blend of two hex colors in RGB (t=0 → a, t=1 → b). */
export function mixHex(a: Hex, b: Hex, t: number): Hex {
  const u = clamp(t, 0, 1);
  const [ar, ag, ab] = hexToRgb(a);
  const [br, bg, bb] = hexToRgb(b);
  return rgbToHex(ar + (br - ar) * u, ag + (bg - ag) * u, ab + (bb - ab) * u);
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

/** Seconds for one full hue wheel. Gameplay stays in the dark void. */
export const HUE_CYCLE_SECONDS = 180;

/** Seconds for one sap rise: core → roots → trunk → branches → crust. */
export const SAP_RISE_SECONDS = 5.55;

/** Normalized windows along `sapRiseU` (overlaps so the pulse never jumps). */
export const SAP_WINDOW = {
  core: [0, 0.14],
  roots: [0, 0.4],
  trunk: [0.26, 0.56],
  twig: [0.44, 0.76],
  grass: [0.58, 0.9],
} as const;

/** 0..1 position in the sap-rise cycle for this plant. */
export function sapRiseU(time: number, seed: number): number {
  const phase = (seed % 997) * 0.0017;
  const x = (time + phase) / SAP_RISE_SECONDS;
  return x - Math.floor(x);
}

/**
 * How far a pulse has traveled through a stage, plus leftover vein glow
 * after the head has passed.
 */
export function sapStage(
  u: number,
  start: number,
  end: number,
  fade = 0.32,
): { progress: number; glow: number; rising: boolean } {
  if (u < start) return { progress: 0, glow: 0, rising: false };
  const span = Math.max(1e-4, end - start);
  if (u <= end) {
    const p = (u - start) / span;
    return { progress: p, glow: 0.38 + 0.62 * p, rising: true };
  }
  const fadeT = Math.max(0, 1 - (u - end) / fade);
  return { progress: 1, glow: 0.3 * fadeT, rising: false };
}

export function buildScene(hue: number, dark: boolean): ScenePalette {
  const h = ((hue % 360) + 360) % 360;
  const bgA = dark ? hslToHex(h, 0.26, 0.04) : hslToHex(h, 0.12, 0.88);
  const bgB = dark
    ? hslToHex(h + 32, 0.18, 0.085)
    : hslToHex(h + 18, 0.1, 0.92);
  const bgC = dark
    ? hslToHex(h - 48, 0.24, 0.05)
    : hslToHex(h - 16, 0.14, 0.86);
  const ink = dark ? hslToHex(h, 0.16, 0.82) : hslToHex(h + 160, 0.42, 0.28);
  const inkSoft = dark ? hslToHex(h, 0.12, 0.7) : hslToHex(h + 160, 0.28, 0.38);
  const mist = toPastel(hslToHex(h, 0.4, 0.7));
  const dust = toPastel(hslToHex(h + 50, 0.45, 0.72));
  return { hue: h, dark, bg: bgB, bgA, bgB, bgC, ink, inkSoft, mist, dust };
}

export function createScenePalette(seed: number): ScenePalette {
  return sceneAtTime(seed, 0);
}

/**
 * Slow ambient cycle: hue drifts through every pastel family.
 * In-game wash stays a dark space void (paper is title-only via buildScene).
 */
export function sceneAtTime(seed: number, time: number): ScenePalette {
  const rng = mulberry32(seed >>> 0);
  const baseHue = rng() * 360;
  const t = Math.max(0, time);
  const laps = t / HUE_CYCLE_SECONDS;
  const hue = (baseHue + laps * 360) % 360;
  return buildScene(hue, true);
}

export function writeScene(dst: ScenePalette, src: ScenePalette): void {
  dst.hue = src.hue;
  dst.dark = src.dark;
  dst.bg = src.bg;
  dst.bgA = src.bgA;
  dst.bgB = src.bgB;
  dst.bgC = src.bgC;
  dst.ink = src.ink;
  dst.inkSoft = src.inkSoft;
  dst.mist = src.mist;
  dst.dust = src.dust;
}

export function floraEquals(a: FloraPalette, b: FloraPalette): boolean {
  return (
    a.wood === b.wood &&
    a.tuft === b.tuft &&
    a.leaf === b.leaf &&
    a.grass === b.grass &&
    a.flower === b.flower &&
    a.root === b.root &&
    a.rootSoft === b.rootSoft &&
    a.wing === b.wing &&
    a.seedBody === b.seedBody &&
    a.core === b.core &&
    a.coreHot === b.coreHot &&
    a.coreWhite === b.coreWhite &&
    a.rock === b.rock &&
    a.rockShadow === b.rockShadow &&
    a.rockLit === b.rockLit &&
    a.stain === b.stain &&
    a.outline === b.outline &&
    a.ring === b.ring &&
    a.film === b.film
  );
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
  const leafH = lerpHue(woodH, 118, 0.42);
  const leaf = hslToHex(leafH, 0.48, scene.dark ? 0.62 : 0.5);
  const grassH = lerpHue(h, leafH, 0.62);
  const grass = hslToHex(grassH, 0.4, scene.dark ? 0.52 : 0.5);
  const filmH = lerpHue(grassH, h, 0.45);
  const film = hslToHex(filmH, 0.46, scene.dark ? 0.5 : 0.54);
  const core = hslToHex(h, 0.42, 0.72);
  const coreHot = hslToHex(h, 0.5, 0.62);
  const coreWhite = hslToHex(h, 0.12, 0.94);
  // Rule 6: glowing roots — saturated warm amber; bloom is color, not chalk.
  const rootH = lerpHue(38, h, 0.18);
  const root = hslToHex(rootH, 0.72, 0.55);
  const rootSoft = hslToHex(rootH, 0.55, 0.68);
  const rockH = lerpHue(scene.hue, h, 0.42);
  const rockL = scene.dark ? 0.2 + rng() * 0.1 : 0.7 + rng() * 0.1;
  const rockS = (scene.dark ? 0.2 : 0.16) + rng() * 0.1;
  const rock = hslToHex(rockH, rockS, rockL);
  const rockShadow = hslToHex(rockH, rockS + 0.04, rockL - (scene.dark ? 0.08 : 0.14));
  const rockLit = hslToHex(rockH, rockS * 0.7, Math.min(0.9, rockL + 0.12));
  const stain = hslToHex(h, 0.28, scene.dark ? 0.42 : 0.62);
  const outline = hslToHex(woodH, 0.18, scene.dark ? 0.22 : 0.32);
  const ring = tuft;

  return {
    wood,
    tuft,
    leaf,
    grass,
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
    stain,
    outline,
    ring,
    film,
  };
}

export function seedlingColors(
  stats: Stats,
  scene: ScenePalette,
  extras?: { faction?: FactionId; kind?: SeedlingKind },
): { wing: Hex; body: Hex } {
  let h = accentHue(stats, scene.hue);
  let s = extras?.kind === 'sentinel' ? 0.4 : 0.3;
  let l = extras?.kind === 'sentinel' ? 0.7 : 0.74;
  if (extras?.faction === 'grey') {
    s *= 0.35;
    l = 0.62;
  } else if (extras?.faction === 'enemy') {
    h = lerpHue(h, 12, 0.55);
    s = Math.min(0.48, s + 0.08);
  }
  return {
    wing: hslToHex(h, s, l),
    body: hslToHex(
      h,
      Math.min(0.52, s + 0.12),
      extras?.kind === 'sentinel' ? 0.34 : 0.4,
    ),
  };
}

export function factionCoreHue(faction: FactionId, floraHue: number): number {
  if (faction === 'enemy') return lerpHue(floraHue, 8, 0.7);
  if (faction === 'grey') return lerpHue(floraHue, 40, 0.25);
  return floraHue;
}

export function applySceneToDocument(scene: ScenePalette): void {
  const root = document.documentElement.style;
  root.setProperty('--ab-bg', cssHex(scene.bg));
  root.setProperty('--ab-ink', cssHex(scene.ink));
  root.setProperty('--ab-ink-soft', cssHex(scene.inkSoft));
}
