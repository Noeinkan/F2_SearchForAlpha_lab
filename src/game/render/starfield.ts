import { Container, Graphics } from 'pixi.js';
import { mulberry32 } from '../sim/rng';
import {
  bucketHue,
  hslToHex,
  type BackgroundTheme,
  type Hex,
  type ScenePalette,
} from './palette';

type Cloud = { x: number; y: number; r: number; mist: boolean; alpha: number };
type Star = { x: number; y: number; size: number; alpha: number };

/**
 * Two themed backdrop + nebula layers stacked, with alphas driven by the
 * theme crossfade (`mix`). Layer A is the outgoing theme (alpha = 1 − mix),
 * layer B is the incoming theme (alpha = mix). When `mix` is 0 or 1 the
 * inactive layer is fully transparent so we still pay one Graphics clear per
 * frame, but no fill cost.
 */
export class Starfield {
  /** Screen-space void. Add to the stage, behind the camera. */
  readonly backdrop = new Graphics();
  /** World-space nebulae and stars. */
  readonly root = new Container();
  private nebulaA = new Graphics();
  private nebulaB = new Graphics();
  private starsFar = new Graphics();
  private starsNear = new Graphics();
  private clouds: Cloud[];
  private farStars: Star[];
  private nearStars: Star[];
  private scene: ScenePalette;
  /** Current pair of themes being crossfaded. */
  private themeA: BackgroundTheme = 'void';
  private themeB: BackgroundTheme = 'void';
  /** 0 = full A, 1 = full B. */
  private mix = 0;
  private viewW = 1;
  private viewH = 1;
  private lastHueBucket = -1;
  private lastThemeA: BackgroundTheme | undefined;
  private lastThemeB: BackgroundTheme | undefined;
  private lastMix = -1;

  constructor(seed: number, scene: ScenePalette) {
    this.scene = scene;
    this.themeA = scene.theme ?? 'void';
    this.themeB = this.themeA;
    this.backdrop.eventMode = 'none';
    this.root.eventMode = 'none';
    this.root.addChild(this.nebulaA, this.nebulaB, this.starsFar, this.starsNear);
    const layout = layoutSky(seed);
    this.clouds = layout.clouds;
    this.farStars = layout.farStars;
    this.nearStars = layout.nearStars;
    this.retheme(scene, this.themeA, this.themeB, 0);
  }

  resize(width: number, height: number): void {
    this.viewW = Math.max(1, width);
    this.viewH = Math.max(1, height);
    paintBackdropForTheme(this.backdrop, this.viewW, this.viewH, this.scene, this.themeB, 1);
  }

  /**
   * Re-paint both themed layers and the star tints. The backdrop fill itself
   * is owned by the current theme's painter; we re-paint both layers here so
   * a jump in `scene.hue` shows up immediately on the next frame.
   */
  retheme(
    scene: ScenePalette,
    themeA: BackgroundTheme,
    themeB: BackgroundTheme,
    mix: number,
  ): void {
    const newMix = clamp01(mix);
    const bucket = bucketHue(scene.hue);
    if (
      bucket === this.lastHueBucket &&
      themeA === this.lastThemeA &&
      themeB === this.lastThemeB &&
      newMix === this.lastMix
    ) {
      this.scene = scene;
      return;
    }
    this.lastHueBucket = bucket;
    this.lastThemeA = themeA;
    this.lastThemeB = themeB;
    this.lastMix = newMix;
    this.scene = scene;
    this.themeA = themeA;
    this.themeB = themeB;
    this.mix = newMix;
    paintBackdropForTheme(this.backdrop, this.viewW, this.viewH, scene, themeB, 1);
    paintNebulaeForTheme(this.nebulaA, this.clouds, scene, themeA, 1 - this.mix);
    paintNebulaeForTheme(this.nebulaB, this.clouds, scene, themeB, this.mix);
    paintStars(this.starsFar, this.farStars, scene.mist);
    paintStars(this.starsNear, this.nearStars, scene.mist);
  }

  setParallax(camX: number, camY: number): void {
    const px = -camX * 0.02;
    const py = -camY * 0.02;
    this.nebulaA.position.set(px, py);
    this.nebulaB.position.set(px, py);
    this.starsFar.position.set(-camX * 0.04, -camY * 0.04);
    this.starsNear.position.set(-camX * 0.08, -camY * 0.08);
  }

  tick(_t: number): void {
    // Still sky — no twinkle. The hue drift is handled in main.ts by calling
    // `retheme(...)` every frame.
  }
}

function layoutSky(seed: number): {
  clouds: Cloud[];
  farStars: Star[];
  nearStars: Star[];
} {
  const rng = mulberry32(seed ^ 0xa5a5a5a5);
  const clouds: Cloud[] = [];
  for (let i = 0; i < 3; i++) {
    clouds.push({
      x: (rng() - 0.5) * 2400,
      y: (rng() - 0.5) * 2400,
      r: 280 + rng() * 220,
      mist: rng() > 0.5,
      alpha: 0.04 + rng() * 0.03,
    });
  }
  return {
    clouds,
    farStars: scatterStars(rng, 55, 0.45, 0.12, 0.28),
    nearStars: scatterStars(rng, 14, 0.8, 0.2, 0.4),
  };
}

function scatterStars(
  rng: () => number,
  count: number,
  size: number,
  a0: number,
  a1: number,
): Star[] {
  const stars: Star[] = [];
  for (let i = 0; i < count; i++) {
    stars.push({
      x: (rng() - 0.5) * 3600,
      y: (rng() - 0.5) * 3600,
      size: size * (0.7 + rng() * 0.6),
      alpha: a0 + rng() * (a1 - a0),
    });
  }
  return stars;
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

/**
 * Backdrop per theme. The void + paper themes use a flat wash + a soft
 * radial bloom; aurora adds a vertical gradient stripe; nebula leans on
 * the warm-cool contrast of `scene.bgA` vs `scene.bgC`.
 */
function paintBackdropForTheme(
  g: Graphics,
  w: number,
  h: number,
  scene: ScenePalette,
  theme: BackgroundTheme,
  alpha: number,
): void {
  g.clear();
  if (alpha <= 0.001) return;
  const base = baseBackdropColor(scene, theme);
  g.rect(0, 0, w, h);
  g.fill({ color: base, alpha });

  switch (theme) {
    case 'void':
      paintVoidWash(g, w, h, scene, alpha);
      break;
    case 'paper':
      paintPaperWash(g, w, h, scene, alpha);
      break;
    case 'aurora':
      paintAuroraWashes(g, w, h, scene, alpha);
      break;
    case 'nebula':
      paintNebulaWash(g, w, h, scene, alpha);
      break;
  }
}

function paintNebulaeForTheme(
  g: Graphics,
  clouds: Cloud[],
  scene: ScenePalette,
  theme: BackgroundTheme,
  alpha: number,
): void {
  g.clear();
  if (alpha <= 0.001) return;
  for (const cloud of clouds) {
    const tint = cloudTint(scene, theme, cloud);
    g.circle(cloud.x, cloud.y, cloud.r);
    g.fill({ color: tint, alpha: cloud.alpha * 0.45 * alpha });
    g.circle(cloud.x, cloud.y, cloud.r * 0.55);
    g.fill({ color: tint, alpha: cloud.alpha * alpha });
  }
}

function paintStars(g: Graphics, stars: Star[], tint: Hex): void {
  g.clear();
  for (const s of stars) {
    g.circle(s.x, s.y, s.size);
    g.fill({ color: s.alpha > 0.32 ? 0xf0ebe3 : tint, alpha: s.alpha });
  }
}

function baseBackdropColor(scene: ScenePalette, theme: BackgroundTheme): Hex {
  // Each theme picks a base from the scene palette it built. Void + nebula
  // use the darkest field; paper uses the lightest; aurora uses the mid
  // field so the stripes read against something darker than the wash.
  switch (theme) {
    case 'void':
      return hslToHex(scene.hue, 0.26, 0.035);
    case 'paper':
      return scene.bgA;
    case 'aurora':
      return scene.bgC;
    case 'nebula':
      return hslToHex(scene.hue, 0.32, 0.045);
  }
}

function cloudTint(scene: ScenePalette, theme: BackgroundTheme, cloud: Cloud): Hex {
  switch (theme) {
    case 'void':
      return cloud.mist ? scene.mist : scene.dust;
    case 'paper':
      // Paper sky uses warm dust clouds; mist reads as a cooler wash.
      return cloud.mist ? scene.inkSoft : scene.dust;
    case 'aurora':
      // Aurora's highlights are the mist field; dust trails below them.
      return cloud.mist ? scene.mist : scene.dust;
    case 'nebula':
      return cloud.mist ? scene.mist : scene.dust;
  }
}

function paintVoidWash(g: Graphics, w: number, h: number, scene: ScenePalette, alpha: number): void {
  g.circle(w * 0.5, h * 0.48, Math.max(w, h) * 0.7);
  g.fill({ color: scene.bgB, alpha: 0.35 * alpha });
}

function paintPaperWash(g: Graphics, w: number, h: number, scene: ScenePalette, alpha: number): void {
  // A soft inner highlight so the paper doesn't read as flat. Offset
  // toward the upper third where the "sun" would be.
  g.circle(w * 0.55, h * 0.32, Math.max(w, h) * 0.55);
  g.fill({ color: scene.bgB, alpha: 0.45 * alpha });
  g.circle(w * 0.4, h * 0.7, Math.max(w, h) * 0.42);
  g.fill({ color: scene.bgC, alpha: 0.35 * alpha });
}

function paintAuroraWashes(g: Graphics, w: number, h: number, scene: ScenePalette, alpha: number): void {
  // Two diagonal bands, mist then dust, at low alpha. Reads as a curtain
  // rolling across the screen rather than a single stripe.
  g.ellipse(w * 0.4, h * 0.32, w * 0.55, h * 0.12);
  g.fill({ color: scene.mist, alpha: 0.4 * alpha });
  g.ellipse(w * 0.6, h * 0.6, w * 0.6, h * 0.14);
  g.fill({ color: scene.dust, alpha: 0.3 * alpha });
  // Floor wash so HUD ink still sits on a dim base.
  g.rect(0, h * 0.78, w, h * 0.22);
  g.fill({ color: scene.bgC, alpha: 0.55 * alpha });
}

function paintNebulaWash(g: Graphics, w: number, h: number, scene: ScenePalette, alpha: number): void {
  // Magenta core + cyan halo. Two stacked soft rings like the planet cores.
  g.circle(w * 0.5, h * 0.55, Math.max(w, h) * 0.55);
  g.fill({ color: scene.bgB, alpha: 0.4 * alpha });
  g.circle(w * 0.5, h * 0.5, Math.max(w, h) * 0.35);
  g.fill({ color: scene.dust, alpha: 0.18 * alpha });
}