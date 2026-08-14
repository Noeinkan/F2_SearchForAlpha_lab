import { Container, Graphics } from 'pixi.js';
import type { World } from '../sim/types';
import { PAL } from './palette';

export class GraphView {
  readonly root = new Container();
  private rings = new Graphics();
  private selectedRing = new Graphics();

  constructor() {
    this.root.eventMode = 'none';
    this.root.addChild(this.rings, this.selectedRing);
  }

  sync(world: World, selectedId: number | null): void {
    this.rings.clear();
    this.selectedRing.clear();

    for (const a of world.asteroids.values()) {
      const isSel = a.id === selectedId;
      dashCircle(
        this.rings,
        a.x,
        a.y,
        a.travelRadius,
        isSel ? PAL.magenta : 0x8a7080,
        isSel ? 0.28 : 0.1,
        isSel ? 7 : 5,
      );
    }

    if (selectedId !== null) {
      const a = world.asteroids.get(selectedId);
      if (a) {
        this.selectedRing.circle(a.x, a.y, a.radius + 12);
        this.selectedRing.stroke({ width: 1, color: PAL.magenta, alpha: 0.28 });
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
  const n = Math.max(24, Math.floor(circ / (dash * 3)));
  for (let i = 0; i < n; i++) {
    const a0 = (i / n) * Math.PI * 2;
    const a1 = a0 + (Math.PI * 2) / n * 0.38;
    g.moveTo(x + Math.cos(a0) * radius, y + Math.sin(a0) * radius);
    g.lineTo(x + Math.cos(a1) * radius, y + Math.sin(a1) * radius);
    g.stroke({ width: 1, color, alpha, cap: 'round' });
  }
}
