import { Container, Graphics } from 'pixi.js';
import type { Seedling, SeedlingState } from '../sim/types';
import { seedlingColors, type ScenePalette } from './palette';

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

  constructor(scene: ScenePalette) {
    this.scene = scene;
    this.back.sortableChildren = true;
    this.front.sortableChildren = true;
    this.front.addChild(this.moteLayer);
  }

  destroy(): void {
    this.back.destroy({ children: true });
    this.front.destroy({ children: true });
  }

  retheme(scene: ScenePalette): void {
    this.scene = scene;
    if (!this.units) return;
    for (const [id, tracked] of this.sprites) {
      const s = this.units.get(id);
      if (s) paintSeedling(tracked.gfx, s, scene);
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
      g.zIndex = z;
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
  const zc = Math.max(-90, Math.min(90, z));
  return 220 / (220 - zc);
}

function visualFacing(s: Seedling, t: number): number {
  const wobble = s.state === 'sprout' ? 0.05 : 0.08;
  return s.facing + Math.sin(t * 1.15 + s.phase) * wobble;
}

function visualScale(s: Seedling, t: number): number {
  const kindScale = s.kind === 'sentinel' ? 1.12 : 1;
  const breathe = 1 + Math.sin(t * 1.35 + s.phase * 0.8) * 0.03;
  let unfurl = 1;
  if (s.state === 'sprout') {
    const dur = Math.max(0.01, s.sproutDuration ?? 3.2);
    unfurl = 0.18 + Math.min(1, (s.sproutAge ?? 0) / dur) * 0.82;
  }
  return unfurl * kindScale * breathe;
}

/**
 * Plump seed hull with two swept membrane wings — organic fighter, not a
 * flying triangle. Span follows speed, hull energy, nose strength.
 */
function paintSeedling(g: Graphics, s: Seedling, scene: ScenePalette): void {
  g.clear();
  const { wing, body: bodyColor } = seedlingColors(s.stats, scene, {
    faction: s.faction,
    kind: s.kind,
  });
  const energy = s.stats.energy / 200;
  const strength = s.stats.strength / 200;
  const speed = s.stats.speed / 200;
  const sentinel = s.kind === 'sentinel';
  const k = sentinel ? 1.14 : 1;

  const span = (3.5 + speed * 2.65) * k;
  const bodyL = (3.75 + energy * 1.3 + strength * 0.28) * k;
  const bodyW = (1.6 + energy * 0.7) * k;
  const nose = bodyL * 0.5;
  const rump = -bodyL * 0.46;

  g.circle(0, 0, Math.max(span * 0.55, bodyL * 0.42));
  g.fill({ color: wing, alpha: sentinel ? 0.12 : 0.07 });

  const rootLead = bodyL * 0.06;
  const rootTrail = rump * 0.55;
  const tipX = -bodyL * 0.08;
  paintWing(g, rootLead, rootTrail, tipX, span, bodyW, wing, sentinel);
  paintWing(g, rootLead, rootTrail, tipX, -span, bodyW, wing, sentinel);

  g.moveTo(nose, 0);
  g.quadraticCurveTo(nose * 0.28, bodyW * 1.02, 0, bodyW);
  g.quadraticCurveTo(rump * 0.58, bodyW * 0.98, rump, 0);
  g.quadraticCurveTo(rump * 0.58, -bodyW * 0.98, 0, -bodyW);
  g.quadraticCurveTo(nose * 0.28, -bodyW * 1.02, nose, 0);
  g.closePath();
  g.fill({ color: bodyColor, alpha: 0.96 });

  g.ellipse(bodyL * 0.02, 0, bodyL * 0.22, bodyW * 0.38);
  g.fill({ color: wing, alpha: 0.16 });

  const stem = 0.82 + strength * 0.6;
  g.moveTo(rump * 0.72, 0);
  g.quadraticCurveTo(rump - stem * 0.35, bodyW * 0.22, rump - stem, 0);
  g.quadraticCurveTo(rump - stem * 0.35, -bodyW * 0.22, rump * 0.72, 0);
  g.closePath();
  g.fill({ color: bodyColor, alpha: 0.9 });

  g.ellipse(bodyL * 0.12, -bodyW * 0.08, bodyW * 0.32, bodyW * 0.24);
  g.fill({ color: wing, alpha: 0.92 });
}

function paintWing(
  g: Graphics,
  rootLead: number,
  rootTrail: number,
  tipX: number,
  tipY: number,
  bodyW: number,
  color: number,
  sentinel: boolean,
): void {
  const side = tipY < 0 ? -1 : 1;
  g.moveTo(rootLead, side * bodyW * 0.35);
  g.quadraticCurveTo(
    (rootLead + tipX) * 0.45,
    tipY * 0.72,
    tipX,
    tipY,
  );
  g.quadraticCurveTo(rootTrail, tipY * 0.48, rootTrail, side * bodyW * 0.72);
  g.closePath();
  g.fill({ color, alpha: sentinel ? 0.8 : 0.64 });
}
