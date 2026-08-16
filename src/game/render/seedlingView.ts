import { Container, Graphics } from 'pixi.js';
import type { Seedling, SeedlingState } from '../sim/types';
import { bucketHue, type ScenePalette } from './palette';
import { paintSeedHull } from './seedlingPaint';

interface TrackedSprite {
  gfx: Graphics;
  lastHp: number;
  flashUntil: number;
  state: SeedlingState;
  x: number;
  y: number;
  z: number;
}

interface DeathMote {
  gfx: Graphics;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
}

export class SeedlingLayer {
  readonly back = new Container();
  readonly front = new Container();
  private sprites = new Map<number, TrackedSprite>();
  private motes: DeathMote[] = [];
  private moteLayer = new Container();
  private scene: ScenePalette;
  private units: Map<number, Seedling> | null = null;
  private lastHueBucket = -1;
  private lastTheme: ScenePalette['theme'] | undefined;

  constructor(scene: ScenePalette) {
    this.scene = scene;
    this.front.addChild(this.moteLayer);
  }

  destroy(): void {
    this.back.destroy({ children: true });
    this.front.destroy({ children: true });
  }

  retheme(scene: ScenePalette): void {
    const bucket = bucketHue(scene.hue);
    const themeChanged = scene.theme !== undefined && scene.theme !== this.lastTheme;
    this.scene = scene;
    if (bucket === this.lastHueBucket && !themeChanged) return;
    this.lastHueBucket = bucket;
    this.lastTheme = scene.theme;
    if (!this.units) return;
    for (const [id, tracked] of this.sprites) {
      const s = this.units.get(id);
      if (s) {
        tracked.gfx.cacheAsTexture(false);
        paintSeedling(tracked.gfx, s, scene);
        tracked.gfx.cacheAsTexture(true);
      }
    }
  }

  sync(seedlings: Map<number, Seedling>): void {
    this.units = seedlings;
    const seen = new Set<number>();
    const now = performance.now();

    for (const s of seedlings.values()) {
      seen.add(s.id);
      let tracked = this.sprites.get(s.id);
      if (!tracked) {
        const gfx = new Graphics();
        paintSeedling(gfx, s, this.scene);
        tracked = {
          gfx,
          lastHp: s.hp,
          flashUntil: 0,
          state: s.state,
          x: s.x,
          y: s.y,
          z: s.z,
        };
        this.sprites.set(s.id, tracked);
        this.front.addChild(gfx);
        gfx.cacheAsTexture(true);
      }

      if (s.hp < tracked.lastHp - 0.01) {
        tracked.flashUntil = now + 120;
      }
      tracked.lastHp = s.hp;
      tracked.state = s.state;
      tracked.x = s.x;
      tracked.y = s.y;

      const g = tracked.gfx;
      const t = now / 1000;
      const z = s.z;
      const dz = z - tracked.z;
      tracked.z = z;
      const bucket = z < 0 ? this.back : this.front;
      if (g.parent !== bucket) bucket.addChild(g);
      g.position.set(s.x, s.y);
      g.rotation = visualFacing(s, t);
      const flashing = now < tracked.flashUntil;
      const flashBoost = flashing ? 1.18 : 1;
      const persp = depthScale(z);
      const flatten = 1 - Math.min(0.3, Math.abs(dz) * 2.4);
      const scale = visualScale(s, t) * flashBoost * persp;
      g.scale.set(scale, scale * flatten);
      const hurt = Math.max(0.35, s.hp / Math.max(1, s.maxHp));
      const plantFade = s.state === 'plant' && (s.wait ?? 0) <= 0 ? 0.85 : 1;
      const depthAlpha = 0.7 + 0.3 * clamp01(0.5 + z / 70);
      g.alpha = plantFade * (flashing ? 1 : 0.45 + 0.55 * hurt) * depthAlpha;
      g.tint = flashing ? 0xfff8ef : 0xffffff;
    }

    for (const [id, tracked] of this.sprites) {
      if (seen.has(id)) continue;
      if (tracked.state !== 'plant') {
        spawnDeathMotes(this.motes, this.moteLayer, tracked.x, tracked.y);
      }
      tracked.gfx.parent?.removeChild(tracked.gfx);
      tracked.gfx.destroy();
      this.sprites.delete(id);
    }

    tickMotes(this.motes, this.moteLayer, 1 / 60);
  }
}

function spawnDeathMotes(
  motes: DeathMote[],
  layer: Container,
  x: number,
  y: number,
): void {
  const n = 4 + Math.floor(Math.random() * 3);
  for (let i = 0; i < n; i++) {
    const gfx = new Graphics();
    const r = 1.2 + Math.random() * 1.8;
    gfx.circle(0, 0, r);
    gfx.fill({ color: 0xf4e8d8, alpha: 0.85 });
    gfx.position.set(x, y);
    layer.addChild(gfx);
    const angle = Math.random() * Math.PI * 2;
    const speed = 18 + Math.random() * 42;
    const life = 0.35 + Math.random() * 0.25;
    motes.push({
      gfx,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 12,
      life,
      maxLife: life,
    });
  }
}

function tickMotes(motes: DeathMote[], layer: Container, dt: number): void {
  for (let i = motes.length - 1; i >= 0; i--) {
    const m = motes[i]!;
    m.life -= dt;
    if (m.life <= 0) {
      layer.removeChild(m.gfx);
      m.gfx.destroy();
      motes.splice(i, 1);
      continue;
    }
    m.gfx.x += m.vx * dt;
    m.gfx.y += m.vy * dt;
    m.vy += 40 * dt;
    const t = m.life / m.maxLife;
    m.gfx.alpha = Math.max(0, t);
    m.gfx.scale.set(0.6 + t * 0.5);
  }
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function depthScale(z: number): number {
  const zc = Math.max(-70, Math.min(70, z));
  return 1 + zc / 280;
}

function visualFacing(s: Seedling, t: number): number {
  const wobble = s.state === 'sprout' ? 0.05 : 0.08;
  return s.facing + Math.sin(t * 1.15 + s.phase) * wobble;
}

function visualScale(s: Seedling, t: number): number {
  const kindScale = s.kind === 'sentinel' ? 1.1 : 1;
  const energyScale = 0.94 + (s.stats.energy / 200) * 0.1;
  const breathe = 1 + Math.sin(t * 1.35 + s.phase * 0.8) * 0.03;
  let unfurl = 1;
  if (s.state === 'sprout') {
    const dur = Math.max(0.01, s.sproutDuration ?? 3.2);
    unfurl = 0.18 + Math.min(1, (s.sproutAge ?? 0) / dur) * 0.82;
  }
  return unfurl * kindScale * energyScale * breathe;
}

function paintSeedling(g: Graphics, s: Seedling, scene: ScenePalette): void {
  g.clear();
  paintSeedHull(g, {
    stats: s.stats,
    scene,
    faction: s.faction,
    kind: s.kind,
    id: s.id,
    open: 1,
  });
}
