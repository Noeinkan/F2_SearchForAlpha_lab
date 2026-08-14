import { Container, Graphics } from 'pixi.js';
import type { Seedling } from '../sim/types';
import { seedlingColors, type ScenePalette } from './palette';

export class SeedlingLayer {
  readonly root = new Container();
  private sprites = new Map<number, Graphics>();
  private scene: ScenePalette;

  constructor(scene: ScenePalette) {
    this.scene = scene;
  }

  sync(seedlings: Map<number, Seedling>): void {
    const seen = new Set<number>();

    for (const s of seedlings.values()) {
      seen.add(s.id);
      let g = this.sprites.get(s.id);
      if (!g) {
        g = drawSeedling(s, this.scene);
        this.sprites.set(s.id, g);
        this.root.addChild(g);
      }
      g.position.set(s.x, s.y);
      g.rotation = s.facing;
      const sprout = s.state === 'sprout' ? Math.min(1, (s.sproutAge ?? 0) / 0.25) : 1;
      g.scale.set(0.55 + sprout * 0.45);
      g.alpha = s.state === 'plant' && (s.wait ?? 0) <= 0 ? 0.85 : 1;
    }

    for (const [id, g] of this.sprites) {
      if (!seen.has(id)) {
        this.root.removeChild(g);
        g.destroy();
        this.sprites.delete(id);
      }
    }
  }
}

/** Three petals around a body — hue comes from the seedling’s stats. */
function drawSeedling(s: Seedling, scene: ScenePalette): Graphics {
  const g = new Graphics();
  const { wing, body: bodyColor } = seedlingColors(s.stats, scene);
  const energy = s.stats.energy / 200;
  const petal = 4.2 + energy * 3.2;
  const body = 1.15 + energy * 0.9;

  g.circle(0, 0, petal * 1.15);
  g.fill({ color: wing, alpha: 0.12 });

  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2 - Math.PI / 2;
    const c = Math.cos(a);
    const sn = Math.sin(a);
    const tipX = c * petal;
    const tipY = sn * petal;
    const px = -sn;
    const py = c;
    g.moveTo(c * body * 0.4, sn * body * 0.4);
    g.quadraticCurveTo(
      c * petal * 0.55 + px * petal * 0.38,
      sn * petal * 0.55 + py * petal * 0.38,
      tipX,
      tipY,
    );
    g.quadraticCurveTo(
      c * petal * 0.55 - px * petal * 0.38,
      sn * petal * 0.55 - py * petal * 0.38,
      c * body * 0.4,
      sn * body * 0.4,
    );
    g.closePath();
    g.fill({ color: wing, alpha: 0.92 });
    g.stroke({ width: 0.4, color: bodyColor, alpha: 0.35 });
  }

  g.circle(0, 0, body);
  g.fill({ color: bodyColor, alpha: 0.95 });
  return g;
}
