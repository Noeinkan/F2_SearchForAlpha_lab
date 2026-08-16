import { describe, expect, it } from 'vitest';
import {
  accentHue,
  ATMOSPHERES,
  buildFromRecipe,
  buildScene,
  createScenePalette,
  floraPalette,
  hexToRgb,
  hueDistance,
  HUE_CYCLE_SECONDS,
  isPastel,
  mixStatsRgb,
  PALETTE_STEP_SECONDS,
  rgbToHsl,
  sceneAtTime,
  seedlingColors,
  toPastel,
} from '../../src/game/render/palette';
import type { Stats } from '../../src/game/sim/types';

const red = 0xff0000;
const cyan = 0x00e0ff;
const magenta = 0xff40a0;

describe('pastel rule', () => {
  it('toPastel lifts any hue into the pastel saturation/lightness band', () => {
    for (const hex of [red, cyan, magenta, 0x221018, 0xf2e6d4]) {
      const out = toPastel(hex);
      expect(isPastel(out)).toBe(true);
      const [h0] = rgbToHsl(...hexToRgb(hex));
      const [h1] = rgbToHsl(...hexToRgb(out));
      expect(hueDistance(h0, h1)).toBeLessThan(8);
    }
  });

  it('gameplay palettes stay a dark space void for any seed', () => {
    const odd = createScenePalette(0xc0a1f00d);
    const even = createScenePalette(0xc0a1f00e);
    expect(odd.dark).toBe(true);
    expect(even.dark).toBe(true);
    const [, , lOdd] = rgbToHsl(...hexToRgb(odd.bg));
    const [, , lEven] = rgbToHsl(...hexToRgb(even.bg));
    expect(lOdd).toBeLessThan(0.22);
    expect(lEven).toBeLessThan(0.22);
  });

  it('buildScene can still mix a light paper wash', () => {
    const light = buildScene(40, false);
    expect(light.dark).toBe(false);
    const [, , l] = rgbToHsl(...hexToRgb(light.bg));
    expect(l).toBeGreaterThan(0.8);
  });

  it('sceneAtTime walks named atmospheres and stays a dark void', () => {
    const a = sceneAtTime(1, 0);
    const b = sceneAtTime(1, PALETTE_STEP_SECONDS);
    const c = sceneAtTime(1, HUE_CYCLE_SECONDS);
    expect(a.dark).toBe(true);
    expect(b.dark).toBe(true);
    expect(c.dark).toBe(true);
    expect(b.atmosphere).not.toBe(a.atmosphere);
    expect(c.atmosphere).toBe(a.atmosphere);
    expect(hueDistance(a.hue, c.hue)).toBeLessThan(2);
  });

  it('named atmospheres are distinct dark families', () => {
    const hues = ATMOSPHERES.map((r) => r.hue);
    expect(new Set(hues).size).toBe(ATMOSPHERES.length);
    expect(ATMOSPHERES.length).toBeGreaterThanOrEqual(12);
    for (const recipe of ATMOSPHERES) {
      const scene = buildFromRecipe(recipe);
      expect(scene.dark).toBe(true);
      const [, , l] = rgbToHsl(...hexToRgb(scene.bg));
      expect(l).toBeLessThan(0.22);
      expect(recipe.woodOffset).toBeGreaterThanOrEqual(130);
    }
  });

  it('Energy/Strength/Speed mix as yellow/red/green before pastelizing', () => {
    const strong = mixStatsRgb({ energy: 0, strength: 200, speed: 0 });
    const swift = mixStatsRgb({ energy: 0, strength: 0, speed: 200 });
    const rich = mixStatsRgb({ energy: 200, strength: 0, speed: 0 });
    expect(strong[0]).toBeGreaterThan(strong[1]);
    expect(swift[1]).toBeGreaterThan(swift[0]);
    expect(rich[0]).toBeCloseTo(rich[1], 5);
    expect(rich[0]).toBeGreaterThan(rich[2]);
  });

  it('high-speed flora sits cooler than high-strength flora on the same scene', () => {
    const scene = createScenePalette(1);
    const fast: Stats = { energy: 40, strength: 20, speed: 180 };
    const tough: Stats = { energy: 40, strength: 180, speed: 20 };
    expect(accentHue(fast, scene.hue)).not.toBeCloseTo(accentHue(tough, scene.hue), 0);
    const fastH = accentHue(fast, scene.hue);
    const toughH = accentHue(tough, scene.hue);
    // Tough leans red (0°), fast leans green/cyan (120–200°).
    expect(hueDistance(toughH, 0)).toBeLessThan(hueDistance(fastH, 0));
  });

  it('wood is a muted complement of the blossom', () => {
    const scene = createScenePalette(1);
    const pal = floraPalette(
      { energy: 90, strength: 60, speed: 120 },
      99,
      scene,
    );
    const [flowerH] = rgbToHsl(...hexToRgb(pal.flower));
    const [woodH] = rgbToHsl(...hexToRgb(pal.wood));
    expect(hueDistance(flowerH, woodH)).toBeGreaterThan(80);
    expect(isPastel(pal.flower)).toBe(true);
    expect(isPastel(pal.wing)).toBe(true);
  });

  it('roots glow warm amber — visible on rock, distinct from coreWhite', () => {
    const scene = createScenePalette(0xc0a1f00d);
    for (const seed of [1, 42, 99, 0x85ebca6b]) {
      const pal = floraPalette(
        { energy: 100, strength: 50, speed: 80 },
        seed,
        scene,
      );
      const [, rootS, rootL] = rgbToHsl(...hexToRgb(pal.root));
      const [, , softL] = rgbToHsl(...hexToRgb(pal.rootSoft));
      const [, , rockL] = rgbToHsl(...hexToRgb(pal.rock));
      const [, , whiteL] = rgbToHsl(...hexToRgb(pal.coreWhite));
      expect(rootL).toBeGreaterThan(rockL + 0.18);
      expect(rootL).toBeGreaterThan(0.45);
      expect(rootS).toBeGreaterThan(0.55);
      expect(softL).toBeGreaterThan(rootL);
      expect(whiteL - rootL).toBeGreaterThan(0.2);
    }
  });

  it('seedling wings follow the same pastel operator', () => {
    const scene = createScenePalette(7);
    const { wing } = seedlingColors({ energy: 80, strength: 50, speed: 90 }, scene);
    expect(isPastel(wing)).toBe(true);
  });
});
