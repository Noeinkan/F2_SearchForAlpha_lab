import { Container, Graphics } from 'pixi.js';
import { buildTree, maturityStep } from '../sim/lsystem';
import type { Asteroid, Tree } from '../sim/types';
import { slotPosition } from '../sim/world';
import {
  floraPalette,
  type FloraPalette,
  type ScenePalette,
} from './palette';

const SURFACE_INSET = 0.18;

export class TreeView {
  readonly canopy = new Container();
  readonly roots = new Container();
  private wood = new Graphics();
  private wash = new Graphics();
  private rootGfx = new Graphics();
  private lastStep = -1;
  private treeId: number;
  private treeSeed: number;
  private pal: FloraPalette;

  constructor(tree: Tree, asteroid: Asteroid, scene: ScenePalette) {
    this.treeId = tree.id;
    this.treeSeed = tree.seed;
    this.pal = floraPalette(asteroid.stats, asteroid.seed, scene);
    this.canopy.addChild(this.wash, this.wood);
    this.roots.addChild(this.rootGfx);
    this.layout(tree, asteroid);
    this.redraw(tree.maturity, asteroid.radius);
  }

  private layout(tree: Tree, asteroid: Asteroid): void {
    const pos = slotPosition(asteroid, tree.slotIndex);
    const rot = pos.angle + Math.PI / 2;
    this.canopy.position.set(pos.x, pos.y);
    this.canopy.rotation = rot;
    this.roots.position.set(pos.x, pos.y);
    this.roots.rotation = rot;
  }

  update(tree: Tree, asteroid: Asteroid): void {
    if (tree.id !== this.treeId) return;
    this.layout(tree, asteroid);
    const step = maturityStep(tree.maturity);
    if (step !== this.lastStep) {
      this.redraw(tree.maturity, asteroid.radius);
    }
  }

  private redraw(maturity: number, asteroidRadius: number): void {
    this.lastStep = maturityStep(maturity);
    const scale = asteroidRadius / 82;
    const surfaceY = -asteroidRadius * SURFACE_INSET;
    const geom = buildTree(
      this.treeSeed,
      maturity,
      scale,
      asteroidRadius * (1 - SURFACE_INSET),
      surfaceY,
    );
    const wood = this.wood;
    const wash = this.wash;
    const rootGfx = this.rootGfx;
    wood.clear();
    wash.clear();
    rootGfx.clear();

    const c = geom.collar;
    rootGfx.ellipse(c.x, c.y + c.ry * 0.35, c.rx * 1.15, c.ry * 1.2);
    rootGfx.fill({ color: this.pal.rootSoft, alpha: 0.35 });
    rootGfx.ellipse(c.x, c.y + c.ry * 0.2, c.rx, c.ry);
    rootGfx.fill({ color: this.pal.root, alpha: 0.7 });

    for (const r of geom.roots) {
      ribbon(
        rootGfx,
        r.points,
        r.widthStart + 3.4,
        r.widthEnd + 2.2,
        this.pal.rootSoft,
        0.28,
      );
      ribbon(rootGfx, r.points, r.widthStart, r.widthEnd, this.pal.root, 0.92);
    }

    for (const b of geom.blobs) {
      wash.circle(b.x, b.y, b.r);
      wash.fill({ color: this.pal.tuft, alpha: b.alpha });
    }

    wood.ellipse(c.x, c.y - c.ry * 0.25, c.rx * 0.95, c.ry * 0.9);
    wood.fill({ color: this.pal.wood, alpha: 0.88 });

    for (const s of geom.strokes) {
      if (s.kind === 'tuft') {
        ribbon(wood, s.points, s.widthStart, s.widthEnd, this.pal.tuft, 0.9);
        continue;
      }
      const color = s.kind === 'twig' ? this.pal.tuft : this.pal.wood;
      ribbon(
        wood,
        s.points,
        s.widthStart + 1.1,
        s.widthEnd + 0.55,
        color,
        0.28,
      );
      ribbon(wood, s.points, s.widthStart, s.widthEnd, color, 0.96);
    }

    for (const f of geom.flowers) {
      drawStarburst(wood, f.x, f.y, f.angle, f.size, this.pal);
    }
  }
}

function chaikin(
  points: { x: number; y: number }[],
  iterations = 2,
): { x: number; y: number }[] {
  let pts = points;
  for (let k = 0; k < iterations; k++) {
    if (pts.length < 2) break;
    const next: { x: number; y: number }[] = [{ x: pts[0]!.x, y: pts[0]!.y }];
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i]!;
      const b = pts[i + 1]!;
      next.push({
        x: a.x * 0.75 + b.x * 0.25,
        y: a.y * 0.75 + b.y * 0.25,
      });
      next.push({
        x: a.x * 0.25 + b.x * 0.75,
        y: a.y * 0.25 + b.y * 0.75,
      });
    }
    next.push({
      x: pts[pts.length - 1]!.x,
      y: pts[pts.length - 1]!.y,
    });
    pts = next;
  }
  return pts;
}

function ribbon(
  g: Graphics,
  points: { x: number; y: number }[],
  widthStart: number,
  widthEnd: number,
  color: number,
  alpha: number,
): void {
  const pts = chaikin(points, 2);
  if (pts.length < 2) return;

  const left: { x: number; y: number }[] = [];
  const right: { x: number; y: number }[] = [];
  for (let i = 0; i < pts.length; i++) {
    const t = i / (pts.length - 1);
    const w = (widthStart + (widthEnd - widthStart) * t) * 0.5;
    let dx: number;
    let dy: number;
    if (i === 0) {
      dx = pts[1]!.x - pts[0]!.x;
      dy = pts[1]!.y - pts[0]!.y;
    } else if (i === pts.length - 1) {
      dx = pts[i]!.x - pts[i - 1]!.x;
      dy = pts[i]!.y - pts[i - 1]!.y;
    } else {
      dx = pts[i + 1]!.x - pts[i - 1]!.x;
      dy = pts[i + 1]!.y - pts[i - 1]!.y;
    }
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    const p = pts[i]!;
    left.push({ x: p.x + nx * w, y: p.y + ny * w });
    right.push({ x: p.x - nx * w, y: p.y - ny * w });
  }

  g.moveTo(left[0]!.x, left[0]!.y);
  for (let i = 1; i < left.length; i++) g.lineTo(left[i]!.x, left[i]!.y);
  for (let i = right.length - 1; i >= 0; i--) g.lineTo(right[i]!.x, right[i]!.y);
  g.closePath();
  g.fill({ color, alpha });

  g.circle(pts[0]!.x, pts[0]!.y, widthStart * 0.5);
  g.fill({ color, alpha });
  g.circle(pts[pts.length - 1]!.x, pts[pts.length - 1]!.y, widthEnd * 0.5);
  g.fill({ color, alpha });
}

function drawStarburst(
  g: Graphics,
  x: number,
  y: number,
  angle: number,
  size: number,
  pal: FloraPalette,
): void {
  const n = 7;
  for (let i = 0; i < n; i++) {
    const a = angle + (i / n) * Math.PI * 2;
    const len = i % 2 === 0 ? size : size * 0.55;
    g.moveTo(x, y);
    g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    g.stroke({ width: 0.65, color: pal.flower, alpha: 0.88, cap: 'round' });
  }
  g.circle(x, y, 1.05);
  g.fill({ color: pal.seedBody, alpha: 0.9 });
}
