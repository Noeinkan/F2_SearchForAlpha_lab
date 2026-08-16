import { Container, Graphics } from 'pixi.js';
import {
  buildAdultTree,
  growTree,
  rootFeedActive,
  type TreeGeom,
  type TreeStroke,
} from '../sim/lsystem';
import {
  ROCK_SURFACE_INSET,
  TREE_BURN_SECONDS,
  treeVisualScale,
  type Asteroid,
  type Tree,
  type TreeKind,
} from '../sim/types';
import { slotPolar } from '../sim/rock';
import { slotPosition } from '../sim/world';
import {
  floraEquals,
  floraPalette,
  mixHex,
  sapRiseU,
  sapStage,
  SAP_WINDOW,
  type FloraPalette,
  type ScenePalette,
} from './palette';

export class TreeView {
  /** Single plant container - roots, wood, then sap. Above rock. */
  readonly root = new Container();
  private wood = new Graphics();
  private wash = new Graphics();
  private rootGfx = new Graphics();
  private sap = new Graphics();
  private lastMaturity = -1;
  private treeId: number;
  private treeSeed: number;
  private kind: TreeKind;
  private pal: FloraPalette;
  private swayPhase: number;
  private baseRot = 0;
  private adult: TreeGeom | null = null;
  private adultKey = '';
  private grown: TreeGeom | null = null;
  private coreY = 0;

  constructor(tree: Tree, asteroid: Asteroid, scene: ScenePalette) {
    this.treeId = tree.id;
    this.treeSeed = tree.seed;
    this.kind = tree.kind;
    this.pal = floraPalette(asteroid.stats, asteroid.seed, scene);
    this.swayPhase = (tree.seed % 1000) * 0.017;
    this.sap.blendMode = 'add';
    this.root.addChild(this.rootGfx, this.wash, this.wood, this.sap);
    this.layout(tree, asteroid);
    this.redraw(tree, asteroid);
  }

  destroy(): void {
    this.root.destroy({ children: true });
  }

  private layout(tree: Tree, asteroid: Asteroid): void {
    const pos = slotPosition(asteroid, tree.slotIndex);
    this.baseRot = pos.angle + Math.PI / 2;
    this.root.position.set(pos.x, pos.y);
    this.root.rotation = this.baseRot;
  }

  update(tree: Tree, asteroid: Asteroid): void {
    if (tree.id !== this.treeId) return;
    this.layout(tree, asteroid);
    const t = performance.now() / 1000;
    const young = 1 - tree.maturity;
    const breeze =
      (Math.sin(t * 0.55 + this.swayPhase) * 0.055 +
        Math.sin(t * 1.08 + this.swayPhase * 1.37) * 0.022 +
        Math.sin(t * 1.84 + this.swayPhase * 0.71) * 0.01) *
      (1 + young * 1.35);
    this.root.rotation = this.baseRot + breeze;
    if (tree.maturity !== this.lastMaturity) {
      this.redraw(tree, asteroid);
    }
    this.paintSap(tree, t);

    const burn =
      asteroid.burnTimer > 0
        ? Math.min(1, asteroid.burnTimer / TREE_BURN_SECONDS)
        : 0;
    this.root.alpha = 1 - burn * 0.65;
  }

  retheme(tree: Tree, asteroid: Asteroid, scene: ScenePalette): void {
    const next = floraPalette(asteroid.stats, asteroid.seed, scene);
    if (floraEquals(this.pal, next) && this.lastMaturity === tree.maturity) {
      return;
    }
    this.pal = next;
    this.redraw(tree, asteroid);
  }

  private adultGeom(tree: Tree, asteroid: Asteroid): TreeGeom {
    const polar = slotPolar(asteroid, tree.slotIndex);
    const key = `${this.treeSeed}:${asteroid.radius}:${polar.dist.toFixed(2)}:${this.kind}`;
    if (this.adult && this.adultKey === key) return this.adult;
    const scale = treeVisualScale(asteroid.radius, asteroid.seed);
    const surfaceY = -asteroid.radius * ROCK_SURFACE_INSET;
    this.adult = buildAdultTree(
      this.treeSeed,
      scale,
      polar.dist,
      surfaceY,
      this.kind,
    );
    this.adultKey = key;
    return this.adult;
  }

  private redraw(tree: Tree, asteroid: Asteroid): void {
    this.lastMaturity = tree.maturity;
    const polar = slotPolar(asteroid, tree.slotIndex);
    this.coreY = polar.dist;
    const geom = growTree(this.adultGeom(tree, asteroid), tree.maturity);
    this.grown = geom;
    const wood = this.wood;
    const wash = this.wash;
    const rootGfx = this.rootGfx;
    wood.clear();
    wash.clear();
    rootGfx.clear();

    const c = geom.collar;
    const join = mixHex(this.pal.wood, this.pal.root, 0.5);
    const joinSoft = mixHex(this.pal.wood, this.pal.rootSoft, 0.48);

    const wellR = Math.max(12, this.coreY * 0.18);
    for (const r of geom.roots) {
      // Dark understroke so filaments still read on the bright core.
      ribbon(
        rootGfx,
        r.points,
        r.widthStart * 1.2,
        r.widthEnd * 1.2,
        mixHex(this.pal.outline, join, 0.5),
        0.7,
        1,
        this.pal.outline,
        0.18,
        0.78,
      );
      // Soft bloom â€” hold join longer so the crown matches the trunk base.
      ribbon(
        rootGfx,
        r.points,
        r.widthStart * 2.4 + 2.8,
        r.widthEnd * 2.4 + 2.0,
        joinSoft,
        0.4,
        1,
        this.pal.rootSoft,
        0.2,
        0.82,
      );
      ribbon(
        rootGfx,
        r.points,
        r.widthStart,
        r.widthEnd,
        join,
        1,
        1,
        this.pal.root,
        0.22,
        0.84,
      );
      ribbon(
        rootGfx,
        r.points,
        Math.max(0.6, r.widthStart * 0.42),
        Math.max(0.45, r.widthEnd * 0.42),
        mixHex(join, this.pal.coreHot, 0.3),
        0.85,
        1,
        this.pal.coreHot,
        0.24,
        0.86,
      );
      const tip = r.points[r.points.length - 1];
      if (!tip) continue;
      const d = Math.hypot(tip.x, tip.y - this.coreY);
      const near = d < wellR * 1.6;
      const glow = near ? 1 - d / (wellR * 1.6) : 0.2;
      rootGfx.circle(
        tip.x,
        tip.y,
        (2.2 + glow * 3.2) * (0.75 + tree.maturity * 0.35),
      );
      rootGfx.fill({
        color: near ? this.pal.core : this.pal.rootSoft,
        alpha: 0.22 + glow * 0.4,
      });
      rootGfx.circle(tip.x, tip.y, 0.85 + glow * 1.1);
      rootGfx.fill({
        color: near ? this.pal.coreWhite : this.pal.root,
        alpha: 0.55 + glow * 0.35,
      });
    }

    for (const b of geom.blobs) {
      wash.circle(b.x, b.y, b.r);
      wash.fill({ color: this.pal.leaf, alpha: b.alpha * 0.85 });
      wash.circle(b.x + b.r * 0.18, b.y - b.r * 0.12, b.r * 0.55);
      wash.fill({ color: this.pal.tuft, alpha: b.alpha * 0.45 });
    }

    for (const s of geom.strokes) {
      if (s.kind !== 'tuft' && s.kind !== 'grass') continue;
      if (s.kind === 'tuft') {
        ribbon(wood, s.points, s.widthStart, s.widthEnd, this.pal.tuft, 0.72);
        continue;
      }
      ribbon(wood, s.points, s.widthStart, s.widthEnd, this.pal.grass, 0.78);
      ribbon(
        wood,
        s.points,
        s.widthStart * 0.45,
        s.widthEnd * 0.4,
        this.pal.leaf,
        0.55,
      );
    }

    for (const s of geom.strokes) {
      if (s.kind === 'tuft' || s.kind === 'grass') continue;
      const isTrunk = s.kind === 'wood';
      const color = s.kind === 'twig' ? this.pal.tuft : this.pal.wood;
      const startColor = isTrunk ? join : color;
      ribbon(
        wood,
        s.points,
        s.widthStart + 1.15,
        s.widthEnd + 0.6,
        startColor,
        0.2,
        2,
        color,
        isTrunk ? 0.18 : 0,
        isTrunk ? 0.72 : 1,
      );
      ribbon(
        wood,
        s.points,
        s.widthStart,
        s.widthEnd,
        startColor,
        0.96,
        2,
        color,
        isTrunk ? 0.2 : 0,
        isTrunk ? 0.74 : 1,
      );
      if (isTrunk) {
        ribbon(
          wood,
          s.points,
          s.widthStart * 0.42,
          s.widthEnd * 0.34,
          mixHex(join, this.pal.tuft, 0.35),
          0.26,
          2,
          this.pal.tuft,
          0.22,
          0.76,
        );
      }
    }

    for (const leaf of geom.leaves) {
      drawLeaf(
        wood,
        leaf.x,
        leaf.y,
        leaf.angle,
        leaf.length,
        leaf.width,
        this.pal.leaf,
        0.82,
      );
    }

    for (const f of geom.flowers) {
      const size =
        this.kind === 'energy'
          ? f.size * 1.35
          : this.kind === 'defense'
            ? f.size * 0.78
            : f.size;
      drawBloom(wood, f.x, f.y, f.angle, size, this.pal, this.kind);
    }

    const scale = treeVisualScale(asteroid.radius, asteroid.seed);
    if (this.kind === 'energy') {
      wash.ellipse(c.x, c.y - 14 * scale, 22 * scale, 16 * scale);
      wash.fill({ color: this.pal.core, alpha: 0.12 * Math.min(1, tree.maturity * 1.4) });
    }
    if (this.kind === 'defense') {
      wood.ellipse(c.x, c.y - 10 * scale, 18 * scale, 10 * scale);
      wood.stroke({
        width: 1.6,
        color: this.pal.ring,
        alpha: 0.4 * Math.min(1, tree.maturity * 1.4),
      });
    }

    this.paintSap(tree, performance.now() / 1000);
  }

  private paintSap(tree: Tree, time: number): void {
    const sap = this.sap;
    sap.clear();
    const geom = this.grown;
    if (!geom) return;

    let feed = rootFeedActive(tree.maturity, tree.coreFeed);
    if (this.kind === 'energy') feed = Math.min(1, feed * 1.25);
    if (this.kind === 'defense') feed = feed * 0.85;
    if (feed <= 0.02) return;

    const u = sapRiseU(time, tree.seed);
    const breathe = 0.88 + 0.12 * Math.sin(time * 1.41 + this.swayPhase);
    const strength = feed * breathe * 0.56;
    const core = sapStage(u, SAP_WINDOW.core[0], SAP_WINDOW.core[1], 0.28);
    const roots = sapStage(u, SAP_WINDOW.roots[0], SAP_WINDOW.roots[1]);
    const trunk = sapStage(u, SAP_WINDOW.trunk[0], SAP_WINDOW.trunk[1]);
    const twig = sapStage(u, SAP_WINDOW.twig[0], SAP_WINDOW.twig[1]);
    const grass = sapStage(u, SAP_WINDOW.grass[0], SAP_WINDOW.grass[1], 0.2);

    // Nucleus â€” sap launches from here.
    const wellR = Math.max(14, this.coreY * 0.2);
    const launch = Math.max(core.glow, roots.glow * 0.45) * strength;
    if (launch > 0.02) {
      const throb = 1 + core.progress * 0.22;
      sap.circle(0, this.coreY, wellR * (1.85 + 0.7 * throb) * (0.75 + launch));
      sap.fill({ color: this.pal.core, alpha: 0.16 * launch });
      sap.circle(0, this.coreY, wellR * 1.05 * throb);
      sap.fill({ color: this.pal.coreHot, alpha: 0.22 * launch });
      sap.circle(0, this.coreY, wellR * 0.48 * throb);
      sap.fill({ color: this.pal.coreWhite, alpha: 0.18 * launch });
    }

    // Roots: stored collar â†’ core; reverse so sap rises toward the surface.
    if (roots.glow > 0.02) {
      for (const r of geom.roots) {
        paintSapStroke(sap, r, roots, strength, this.pal, true);
      }
    }

    // Soft collar pulse as sap crosses into the trunk.
    const seam = Math.max(trunk.glow * 0.85, roots.rising ? 0 : roots.glow);
    if (seam > 0.04) {
      const c = geom.collar;
      const k = seam * strength;
      sap.circle(c.x, c.y, c.rx * (1.8 + 0.8 * k));
      sap.fill({ color: this.pal.core, alpha: 0.12 * k });
    }

    for (const s of geom.strokes) {
      if (s.kind === 'wood' && trunk.glow > 0.02) {
        paintSapStroke(sap, s, trunk, strength, this.pal, false);
        continue;
      }
      // Branches fade as sap leaves the trunk â€” only a short haze at the join.
      if (s.kind === 'twig' && twig.glow > 0.02) {
        paintSapStroke(sap, s, twig, strength * 0.22, this.pal, false, 0.28);
        continue;
      }
      if ((s.kind === 'grass' || s.kind === 'tuft') && grass.glow > 0.02) {
        paintSapStroke(sap, s, grass, strength * 0.8, this.pal, false);
      }
    }

    // Small leftover glow in the blooms once sap would have reached the canopy.
    if (twig.glow > 0.03) {
      for (const f of geom.flowers) {
        const k = twig.glow * strength * 0.45;
        const r = f.size * (1.15 + twig.progress * 0.35);
        sap.circle(f.x, f.y, r * 2.1);
        sap.fill({ color: this.pal.core, alpha: 0.12 * k });
        sap.circle(f.x, f.y, r * 0.85);
        sap.fill({ color: this.pal.coreHot, alpha: 0.16 * k });
      }
    }
  }
}

function paintSapStroke(
  g: Graphics,
  stroke: TreeStroke,
  stage: { progress: number; glow: number; rising: boolean },
  strength: number,
  pal: FloraPalette,
  fromTip: boolean,
  taper = 1,
): void {
  const src = stroke.points;
  if (src.length < 2 || stage.glow <= 0.02 || strength <= 0.02) return;

  const pts = fromTip ? reversePts(src) : src;
  const w0 = fromTip ? stroke.widthEnd : stroke.widthStart;
  const w1 = fromTip ? stroke.widthStart : stroke.widthEnd;

  const lens: number[] = [0];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]!;
    const b = pts[i]!;
    total += Math.hypot(b.x - a.x, b.y - a.y);
    lens.push(total);
  }
  if (total < 1.2) return;

  const headT = Math.max(0.02, stage.progress * taper);
  const trail = sliceStroke(pts, lens, total, 0, headT);
  if (trail.length >= 2) {
    sapVein(
      g,
      trail,
      Math.max(0.7, w0 * 0.55),
      Math.max(0.55, widthAt(w0, w1, headT)),
      stage.glow * strength * (stage.rising ? 0.62 : 0.4),
      pal,
      false,
    );
  }

  if (!stage.rising && stage.glow < 0.12) return;

  const pulseLo = Math.max(0, headT - (stage.rising ? 0.4 : 0.18) * taper);
  const pulseHi = Math.min(taper, headT + 0.06);
  const pulse = sliceStroke(pts, lens, total, pulseLo, pulseHi);
  const head = pointAlong(pts, lens, total, headT * total);
  if (pulse.length >= 2) {
    sapVein(
      g,
      pulse,
      Math.max(0.85, widthAt(w0, w1, pulseLo) * 0.7),
      Math.max(0.7, widthAt(w0, w1, pulseHi) * 0.7),
      stage.glow * strength * (taper < 1 ? 0.55 : 1),
      pal,
      taper >= 1,
    );
  }
  if (taper >= 0.85) {
    sapHead(g, head.x, head.y, Math.max(w0, w1), stage.glow * strength, pal);
  }
}

function reversePts(pts: { x: number; y: number }[]): { x: number; y: number }[] {
  const out: { x: number; y: number }[] = [];
  for (let i = pts.length - 1; i >= 0; i--) out.push(pts[i]!);
  return out;
}

function widthAt(w0: number, w1: number, t: number): number {
  return w0 + (w1 - w0) * t;
}

function pointAlong(
  pts: { x: number; y: number }[],
  lens: number[],
  total: number,
  dist: number,
): { x: number; y: number } {
  const d = Math.min(total, Math.max(0, dist));
  for (let i = 1; i < pts.length; i++) {
    if (lens[i]! >= d) {
      const span = lens[i]! - lens[i - 1]! || 1;
      const t = (d - lens[i - 1]!) / span;
      const a = pts[i - 1]!;
      const b = pts[i]!;
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    }
  }
  return pts[pts.length - 1]!;
}

function sliceStroke(
  pts: { x: number; y: number }[],
  lens: number[],
  total: number,
  t0: number,
  t1: number,
): { x: number; y: number }[] {
  const lo = Math.max(0, Math.min(t0, t1) * total);
  const hi = Math.min(total, Math.max(t0, t1) * total);
  if (hi - lo < 0.45) return [];
  const out: { x: number; y: number }[] = [pointAlong(pts, lens, total, lo)];
  for (let i = 0; i < pts.length; i++) {
    const d = lens[i]!;
    if (d > lo + 0.15 && d < hi - 0.15) out.push(pts[i]!);
  }
  out.push(pointAlong(pts, lens, total, hi));
  return out;
}

function sapVein(
  g: Graphics,
  pts: { x: number; y: number }[],
  w0: number,
  w1: number,
  strength: number,
  pal: FloraPalette,
  hot: boolean,
): void {
  if (pts.length < 2 || strength <= 0.02) return;
  const k = hot ? 1 : 0.7;
  ribbon(g, pts, w0 * 4.4 + 7.2, w1 * 4.4 + 6.2, pal.core, 0.14 * strength * k, 1);
  ribbon(g, pts, w0 * 2.2 + 3.2, w1 * 2.2 + 2.6, pal.coreHot, 0.2 * strength * k, 1);
  ribbon(
    g,
    pts,
    Math.max(0.7, w0 * 0.85),
    Math.max(0.55, w1 * 0.75),
    pal.coreWhite,
    (hot ? 0.22 : 0.14) * strength,
    1,
  );
}

function sapHead(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  strength: number,
  pal: FloraPalette,
): void {
  if (strength <= 0.04) return;
  const r = Math.max(3.8, width * 1.35);
  g.circle(x, y, r * 3.2);
  g.fill({ color: pal.core, alpha: 0.16 * strength });
  g.circle(x, y, r * 1.85);
  g.fill({ color: pal.coreHot, alpha: 0.2 * strength });
  g.circle(x, y, r * 0.85);
  g.fill({ color: pal.coreWhite, alpha: 0.18 * strength });
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
  chaikinIters = 2,
  colorEnd?: number,
  /** Hold start color until this t, then ramp (smoothstep). */
  blendFrom = 0,
  /** Reach end color by this t. */
  blendTo = 1,
): void {
  const pts = chaikin(points, chaikinIters);
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

  const end = colorEnd ?? color;
  const blendT = (t: number) => {
    if (end === color) return 0;
    const lo = blendFrom;
    const hi = Math.max(lo + 1e-4, blendTo);
    const u = Math.min(1, Math.max(0, (t - lo) / (hi - lo)));
    return u * u * (3 - 2 * u);
  };

  if (end === color) {
    g.moveTo(left[0]!.x, left[0]!.y);
    for (let i = 1; i < left.length; i++) g.lineTo(left[i]!.x, left[i]!.y);
    for (let i = right.length - 1; i >= 0; i--) g.lineTo(right[i]!.x, right[i]!.y);
    g.closePath();
    g.fill({ color, alpha });
  } else {
    for (let i = 0; i < pts.length - 1; i++) {
      const t0 = i / (pts.length - 1);
      const t1 = (i + 1) / (pts.length - 1);
      const col = mixHex(color, end, blendT((t0 + t1) * 0.5));
      g.moveTo(left[i]!.x, left[i]!.y);
      g.lineTo(left[i + 1]!.x, left[i + 1]!.y);
      g.lineTo(right[i + 1]!.x, right[i + 1]!.y);
      g.lineTo(right[i]!.x, right[i]!.y);
      g.closePath();
      g.fill({ color: col, alpha });
    }
  }

  g.circle(pts[0]!.x, pts[0]!.y, widthStart * 0.5);
  g.fill({ color, alpha });
  g.circle(pts[pts.length - 1]!.x, pts[pts.length - 1]!.y, widthEnd * 0.5);
  g.fill({ color: end, alpha });
}

function drawLeaf(
  g: Graphics,
  x: number,
  y: number,
  angle: number,
  length: number,
  width: number,
  color: number,
  alpha: number,
): void {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const px = -s;
  const py = c;
  const tipX = x + c * length + px * width * 0.22;
  const tipY = y + s * length + py * width * 0.22;
  g.moveTo(x, y);
  g.quadraticCurveTo(
    x + c * length * 0.4 + px * width * 1.15,
    y + s * length * 0.4 + py * width * 1.15,
    tipX,
    tipY,
  );
  g.quadraticCurveTo(
    x + c * length * 0.58 - px * width * 0.72,
    y + s * length * 0.58 - py * width * 0.72,
    x,
    y,
  );
  g.closePath();
  g.fill({ color, alpha });
}

function drawBloom(
  g: Graphics,
  x: number,
  y: number,
  angle: number,
  size: number,
  pal: FloraPalette,
  kind: TreeKind = 'dyson',
): void {
  const n = kind === 'energy' ? 7 : kind === 'defense' ? 5 : 6;
  const petalColor = kind === 'energy' ? pal.core : pal.flower;
  g.circle(x, y, size * 1.85);
  g.fill({ color: petalColor, alpha: 0.2 });
  for (let i = 0; i < n; i++) {
    const a = angle + (i / n) * Math.PI * 2;
    drawLeaf(
      g,
      x,
      y,
      a,
      kind === 'defense' ? size * 0.95 : size * 1.15,
      size * (kind === 'defense' ? 0.38 : 0.48),
      petalColor,
      0.82,
    );
  }
  g.circle(x, y, kind === 'energy' ? size * 0.38 : size * 0.28);
  g.fill({ color: pal.seedBody, alpha: 0.88 });
  if (kind === 'energy') {
    g.circle(x, y, size * 0.16);
    g.fill({ color: pal.coreWhite, alpha: 0.9 });
  }
}
