import { Container, Graphics } from 'pixi.js';
import { PAL } from './palette';
import { buildTree, maturityStep } from '../sim/lsystem';
import { slotPosition } from '../sim/world';
import type { Asteroid, Tree } from '../sim/types';

export class TreeView {
  readonly canopy = new Container();
  readonly roots = new Container();
  private wood = new Graphics();
  private rootGfx = new Graphics();
  private lastStep = -1;
  private treeId: number;
  private treeSeed: number;

  constructor(tree: Tree, asteroid: Asteroid) {
    this.treeId = tree.id;
    this.treeSeed = tree.seed;
    this.canopy.addChild(this.wood);
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
    const geom = buildTree(this.treeSeed, maturity, scale, asteroidRadius * 0.78);
    const wood = this.wood;
    const rootGfx = this.rootGfx;
    wood.clear();
    rootGfx.clear();

    for (const r of geom.roots) {
      strokeChain(rootGfx, r.points, r.width + 2.2, PAL.rootSoft, 0.28);
      strokeChain(rootGfx, r.points, r.width, PAL.root, 0.95);
    }

    for (const s of geom.strokes) {
      const color = s.kind === 'tuft' ? PAL.magenta : PAL.branch;
      strokeChain(wood, s.points, s.width, color, 0.95);
    }

    for (const f of geom.flowers) {
      drawStarburst(wood, f.x, f.y, f.angle, f.size);
    }
  }
}

function strokeChain(
  g: Graphics,
  points: { x: number; y: number }[],
  width: number,
  color: number,
  alpha: number,
): void {
  if (points.length < 2) return;
  g.moveTo(points[0]!.x, points[0]!.y);
  for (let i = 1; i < points.length; i++) {
    g.lineTo(points[i]!.x, points[i]!.y);
  }
  g.stroke({ width, color, alpha, cap: 'round', join: 'round' });
}

function drawStarburst(
  g: Graphics,
  x: number,
  y: number,
  angle: number,
  size: number,
): void {
  const n = 6;
  for (let i = 0; i < n; i++) {
    const a = angle + (i / n) * Math.PI * 2;
    g.moveTo(x, y);
    g.lineTo(x + Math.cos(a) * size, y + Math.sin(a) * size);
    g.stroke({ width: 0.7, color: PAL.flower, alpha: 0.85, cap: 'round' });
  }
  g.circle(x, y, 1.1);
  g.fill({ color: PAL.seedBody, alpha: 0.9 });
}
