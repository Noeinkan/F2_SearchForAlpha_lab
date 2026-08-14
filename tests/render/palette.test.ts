import { describe, expect, it } from 'vitest';
import {
  accentHue,
  createScenePalette,
  floraPalette,
  hexToRgb,
  hueDistance,
  isPastel,
  mixStatsRgb,
  rgbToHsl,
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

  it('odd seeds wash a dark void; even seeds wash light paper', () => {
    const dark = createScenePalette(0xc0a1f00d);
    const light = createScenePalette(0xc0a1f00e);
    expect(dark.dark).toBe(true);
    expect(light.dark).toBe(false);
    const [, , lDark] = rgbToHsl(...hexToRgb(dark.bg));
    const [, , lLight] = rgbToHsl(...hexToRgb(light.bg));
    expect(lDark).toBeLessThan(0.22);
    expect(lLight).toBeGreaterThan(0.8);
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

  it('seedling wings follow the same pastel operator', () => {
    const scene = createScenePalette(7);
    const { wing } = seedlingColors({ energy: 80, strength: 50, speed: 90 }, scene);
    expect(isPastel(wing)).toBe(true);
  });
});
