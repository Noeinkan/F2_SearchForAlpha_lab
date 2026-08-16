import { Container, Graphics } from 'pixi.js';
import { mulberry32 } from '../sim/rng';
import { hslToHex, type Hex, type ScenePalette } from './palette';

type Cloud = { x: number; y: number; r: number; mist: boolean; alpha: number };
type Star = { x: number; y: number; size: number; alpha: number };

export class Starfield {
  /** Screen-space void. Add to the stage, behind the camera. */
  readonly backdrop = new Graphics();
  /** World-space nebulae and stars. */
  readonly root = new Container();
  private nebula = new Graphics();
  private starsFar = new Graphics();
  private starsNear = new Graphics();
  private clouds: Cloud[];
  private farStars: Star[];
  private nearStars: Star[];
  private scene: ScenePalette;
  private viewW = 1;
  private viewH = 1;

  constructor(seed: number, scene: ScenePalette) {
    this.scene = scene;
    this.backdrop.eventMode = 'none';
    this.root.eventMode = 'none';
    this.root.addChild(this.nebula, this.starsFar, this.starsNear);
    const layout = layoutSky(seed);
    this.clouds = layout.clouds;
    this.farStars = layout.farStars;
    this.nearStars = layout.nearStars;
    this.retheme(scene);
  }

  resize(width: number, height: number): void {
    this.viewW = Math.max(1, width);
    this.viewH = Math.max(1, height);
    paintBackdrop(this.backdrop, this.viewW, this.viewH, this.scene);
  }

  retheme(scene: ScenePalette): void {
    this.scene = scene;
    paintBackdrop(this.backdrop, this.viewW, this.viewH, scene);
    paintNebulae(this.nebula, this.clouds, scene);
    paintStars(this.starsFar, this.farStars, scene.mist);
    paintStars(this.starsNear, this.nearStars, scene.mist);
  }

  setParallax(camX: number, camY: number): void {
    this.nebula.position.set(-camX * 0.02, -camY * 0.02);
    this.starsFar.position.set(-camX * 0.04, -camY * 0.04);
    this.starsNear.position.set(-camX * 0.08, -camY * 0.08);
  }

  tick(_t: number): void {
    // Still sky — no twinkle.
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

function paintBackdrop(
  g: Graphics,
  w: number,
  h: number,
  scene: ScenePalette,
): void {
  g.clear();
  const voidColor = hslToHex(scene.hue, 0.26, 0.035);
  g.rect(0, 0, w, h);
  g.fill({ color: voidColor });
  g.circle(w * 0.5, h * 0.48, Math.max(w, h) * 0.7);
  g.fill({ color: scene.bgB, alpha: 0.35 });
}

function paintNebulae(g: Graphics, clouds: Cloud[], scene: ScenePalette): void {
  g.clear();
  for (const cloud of clouds) {
    const color: Hex = cloud.mist ? scene.mist : scene.dust;
    g.circle(cloud.x, cloud.y, cloud.r);
    g.fill({ color, alpha: cloud.alpha * 0.45 });
    g.circle(cloud.x, cloud.y, cloud.r * 0.55);
    g.fill({ color, alpha: cloud.alpha });
  }
}

function paintStars(g: Graphics, stars: Star[], tint: Hex): void {
  g.clear();
  for (const s of stars) {
    g.circle(s.x, s.y, s.size);
    g.fill({ color: s.alpha > 0.32 ? 0xf0ebe3 : tint, alpha: s.alpha });
  }
}
