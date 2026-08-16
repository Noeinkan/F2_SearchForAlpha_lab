import { Container, Graphics } from 'pixi.js';
import { rockRadiusAt } from '../sim/rock';
import { allEdges } from '../sim/graph';
import type { World } from '../sim/types';
import { bucketHue, type ScenePalette } from './palette';

export class GraphView {
  readonly root = new Container();
  private links = new Graphics();
  private rings = new Graphics();
  private selectedRing = new Graphics();
  private scene: ScenePalette;
  private cachedWorld: World | null = null;
  private cachedSel: number | null | undefined = undefined;
  private lastHueBucket = -1;
  private lastTheme: ScenePalette['theme'] | undefined;

  constructor(scene: ScenePalette) {
    this.scene = scene;
    this.root.eventMode = 'none';
    this.root.addChild(this.links, this.rings, this.selectedRing);
  }

  retheme(scene: ScenePalette): void {
    const bucket = bucketHue(scene.hue);
    const themeChanged = scene.theme !== undefined && scene.theme !== this.lastTheme;
    this.scene = scene;
    if (bucket === this.lastHueBucket && !themeChanged) return;
    this.lastHueBucket = bucket;
    this.lastTheme = scene.theme;
    this.cachedWorld = null;
  }

  sync(world: World, selectedId: number | null): void {
    if (this.cachedWorld === world && this.cachedSel === selectedId) return;
    this.cachedWorld = world;
    this.cachedSel = selectedId;

    this.links.clear();
    this.rings.clear();
    this.selectedRing.clear();

    for (const [aId, bId] of allEdges(world)) {
      const a = world.asteroids.get(aId);
      const b = world.asteroids.get(bId);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len = Math.hypot(dx, dy) || 1;
      const ux = dx / len;
      const uy = dy / len;
      const aAng = Math.atan2(dy, dx);
      const r0 = rockRadiusAt(a, aAng);
      const r1 = rockRadiusAt(b, aAng + Math.PI);
      const x0 = a.x + ux * r0;
      const y0 = a.y + uy * r0;
      const x1 = b.x - ux * r1;
      const y1 = b.y - uy * r1;
      const mx = (x0 + x1) / 2;
      const my = (y0 + y1) / 2;
      const sag = 16;
      const cx = mx - uy * sag;
      const cy = my + ux * sag;
      const hot = a.id === selectedId || b.id === selectedId;
      this.links.moveTo(x0, y0);
      this.links.quadraticCurveTo(cx, cy, x1, y1);
      this.links.stroke({
        width: hot ? 1.6 : 1.05,
        color: hot ? this.scene.mist : this.scene.dust,
        alpha: this.scene.dark
          ? hot
            ? 0.28
            : 0.12
          : hot
            ? 0.22
            : 0.1,
        cap: 'round',
      });
    }

    for (const a of world.asteroids.values()) {
      const isSel = a.id === selectedId;
      if (isSel) {
        this.rings.circle(a.x, a.y, a.travelRadius);
        this.rings.fill({
          color: this.scene.mist,
          alpha: this.scene.dark ? 0.035 : 0.04,
        });
      }
      dashCircle(
        this.rings,
        a.x,
        a.y,
        a.travelRadius,
        isSel ? this.scene.ink : this.scene.inkSoft,
        isSel ? 0.2 : 0.06,
        isSel ? 8 : 6,
      );
    }

    if (selectedId !== null) {
      const a = world.asteroids.get(selectedId);
      if (a) {
        this.selectedRing.circle(a.x, a.y, a.radius + 14);
        this.selectedRing.stroke({
          width: 1.15,
          color: this.scene.ink,
          alpha: 0.22,
        });
      }
    }
  }
}

function dashCircle(
  g: Graphics,
  x: number,
  y: number,
  radius: number,
  color: number,
  alpha: number,
  dash: number,
): void {
  const circ = Math.PI * 2 * radius;
  const n = Math.max(28, Math.floor(circ / (dash * 3.4)));
  for (let i = 0; i < n; i++) {
    const a0 = (i / n) * Math.PI * 2;
    const a1 = a0 + ((Math.PI * 2) / n) * 0.32;
    g.moveTo(x + Math.cos(a0) * radius, y + Math.sin(a0) * radius);
    g.lineTo(x + Math.cos(a1) * radius, y + Math.sin(a1) * radius);
    g.stroke({ width: 1.05, color, alpha, cap: 'round' });
  }
}
