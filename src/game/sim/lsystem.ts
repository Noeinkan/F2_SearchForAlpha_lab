import { mulberry32, range, type Rng } from './rng';
import type { TreeKind } from './types';

export interface TreeStroke {
  points: { x: number; y: number }[];
  widthStart: number;
  widthEnd: number;
  kind: 'wood' | 'root' | 'tuft' | 'twig' | 'grass';
  /** 0..1 maturity when this stroke begins to extend. */
  emerge?: number;
  /** 0..1 maturity span over which the stroke reaches full length. */
  span?: number;
}

export interface TreeFlower {
  x: number;
  y: number;
  angle: number;
  size: number;
  emerge?: number;
  span?: number;
}

export interface TreeTip {
  x: number;
  y: number;
  angle: number;
  emerge?: number;
}

export interface TreeBlob {
  x: number;
  y: number;
  r: number;
  alpha: number;
  emerge?: number;
  span?: number;
}

export interface TreeLeaf {
  x: number;
  y: number;
  angle: number;
  length: number;
  width: number;
  emerge?: number;
  span?: number;
}

export interface TreeCollar {
  x: number;
  y: number;
  rx: number;
  ry: number;
}

export interface TreeGeom {
  strokes: TreeStroke[];
  flowers: TreeFlower[];
  tips: TreeTip[];
  roots: TreeStroke[];
  blobs: TreeBlob[];
  leaves: TreeLeaf[];
  collar: TreeCollar;
}

type Pt = { x: number; y: number };

/**
 * One living plant: a slender spine, then an upward fan of
 * asymmetric side-shoots. Roots search the core separately.
 *
 * Topology is always the adult form. `maturity` only reveals it —
 * roots first, then the shoot, laterals, grass, then canopy.
 */
export function buildTree(
  seed: number,
  maturity: number,
  scale = 1,
  coreDepth = 70,
  surfaceY = 0,
  kind: TreeKind = 'dyson',
): TreeGeom {
  return growTree(
    buildAdultTree(seed, scale, coreDepth, surfaceY, kind),
    maturity,
  );
}

export function buildAdultTree(
  seed: number,
  scale = 1,
  coreDepth = 70,
  surfaceY = 0,
  kind: TreeKind = 'dyson',
): TreeGeom {
  const rng = mulberry32(seed >>> 0);
  const strokes: TreeStroke[] = [];
  const flowers: TreeFlower[] = [];
  const tips: TreeTip[] = [];
  const roots: TreeStroke[] = [];
  const blobs: TreeBlob[] = [];
  const leaves: TreeLeaf[] = [];

  const curl = range(rng, 0.1, 0.22);
  const droop = range(rng, 0.05, 0.2);
  const spread = range(rng, 0.55, 0.95);
  const lean = range(rng, -0.22, 0.22);
  const bend = range(rng, 0.05, 0.3);
  const height = scale * 148;
  const collarW = 8.4 * scale;
  const twigW = Math.max(0.7, 0.95 * scale);
  const woodDepth = 4;
  const coreY = coreDepth;
  const energyRich = kind === 'energy';

  const spine = growSpine(rng, surfaceY, height, lean, curl, bend);
  const surfIdx = spine.surfaceIndex;
  const woodPts = spine.points;

  const rootEmerge = 0;
  const rootSpan = 0.45;
  const woodEmerge = 0.07;
  const woodSpan = 0.58;

  const collarX = spine.points[surfIdx]?.x ?? 0;
  const collarPt: Pt = { x: collarX, y: surfaceY };

  growNervousRoots(
    rng,
    collarPt,
    { x: range(rng, -2.2, 2.2) * scale, y: coreY },
    collarW,
    scale,
    energyRich,
    rootEmerge,
    rootSpan,
    roots,
  );

  strokes.push({
    points: woodPts,
    widthStart: collarW,
    widthEnd: Math.max(twigW * 1.8, collarW * 0.38),
    kind: 'wood',
    emerge: woodEmerge,
    span: woodSpan,
  });

  const woodLaterals = 3 + Math.floor(rng() * 2);
  spawnLaterals(
    rng,
    spine.points,
    surfIdx,
    spine.points.length - 1,
    woodLaterals,
    spread,
    curl,
    droop,
    false,
    0,
    woodDepth,
    scale,
    woodEmerge,
    woodSpan,
    strokes,
    flowers,
    tips,
    roots,
    leaves,
  );

  growScarFlora(rng, surfaceY, scale, strokes);

  paintCanopy(tips, flowers, blobs, leaves, rng, scale);

  const collar: TreeCollar = {
    x: collarX,
    y: surfaceY,
    rx: collarW * 1.15,
    ry: collarW * 1.55,
  };

  return { strokes, flowers, tips, roots, blobs, leaves, collar };
}

/**
 * How close adult roots came to the energy well (0..1).
 * Full feed inside the core glow radius; falloff outside.
 */
export function measureRootFeed(
  geom: TreeGeom,
  coreY: number,
  coreX = 0,
): number {
  let best = Infinity;
  for (const r of geom.roots) {
    if (r.points.length === 0) continue;
    const tip = r.points[r.points.length - 1]!;
    const d = Math.hypot(tip.x - coreX, tip.y - coreY);
    if (d < best) best = d;
  }
  if (!Number.isFinite(best)) return 0;
  const fullR = Math.max(12, Math.abs(coreY) * 0.18);
  const falloff = fullR * 2.6;
  if (best <= fullR) return 1;
  if (best >= falloff) return 0;
  return 1 - (best - fullR) / (falloff - fullR);
}

/** Maturity-gated feed strength used by spawn/regen multipliers. */
export function rootFeedActive(maturity: number, coreFeed: number): number {
  const m = Math.min(1, Math.max(0, maturity));
  const feed = Math.min(1, Math.max(0, coreFeed));
  return smoothstep(0.2, 0.55, m) * feed;
}

/**
 * How ready a tree is to drop seedlings (0 before side tips, 1 at adult).
 * Pass SPAWN_START_MATURITY from types as startMaturity.
 */
export function spawnReadiness(
  maturity: number,
  startMaturity: number,
): number {
  const m = Math.min(1, Math.max(0, maturity));
  if (m < startMaturity) return 0;
  return smoothstep(startMaturity, 1, m);
}

/** Reveal the adult plant from root-tip to canopy as maturity rises. */
export function growTree(adult: TreeGeom, maturity: number): TreeGeom {
  const m = Math.min(1, Math.max(0, maturity));
  if (m >= 0.999) return adult;

  const strokes: TreeStroke[] = [];
  for (const s of adult.strokes) {
    const grown = clipStroke(s, growthProgress(m, s.emerge ?? 0.12, s.span ?? 0.28));
    if (grown) strokes.push(grown);
  }
  const roots: TreeStroke[] = [];
  for (const s of adult.roots) {
    const grown = clipStroke(s, growthProgress(m, s.emerge ?? 0, s.span ?? 0.32));
    if (grown) roots.push(grown);
  }

  const tips: TreeTip[] = [];
  for (const s of strokes) {
    if (s.kind !== 'wood' && s.kind !== 'twig') continue;
    const end = s.points[s.points.length - 1];
    const pre = s.points[s.points.length - 2];
    if (!end || !pre) continue;
    tips.push({
      x: end.x,
      y: end.y,
      angle: Math.atan2(end.y - pre.y, end.x - pre.x),
    });
  }

  const flowers: TreeFlower[] = [];
  for (const f of adult.flowers) {
    const t = growthProgress(m, f.emerge ?? 0.72, f.span ?? 0.2);
    if (t <= 0.02) continue;
    flowers.push({
      x: f.x,
      y: f.y,
      angle: f.angle,
      size: f.size * (0.12 + 0.88 * t),
    });
  }

  const leaves: TreeLeaf[] = [];
  for (const leaf of adult.leaves) {
    const t = growthProgress(m, leaf.emerge ?? 0.58, leaf.span ?? 0.22);
    if (t <= 0.02) continue;
    leaves.push({
      x: leaf.x,
      y: leaf.y,
      angle: leaf.angle + (1 - t) * 0.55,
      length: leaf.length * (0.12 + 0.88 * t),
      width: leaf.width * (0.2 + 0.8 * t),
    });
  }

  const blobs: TreeBlob[] = [];
  for (const b of adult.blobs) {
    const t = growthProgress(m, b.emerge ?? 0.5, b.span ?? 0.32);
    if (t <= 0.02) continue;
    blobs.push({
      x: b.x,
      y: b.y,
      r: b.r * (0.2 + 0.8 * t),
      alpha: b.alpha * t,
    });
  }

  const ct = smoothstep(0.02, 0.26, m);
  const collar: TreeCollar = {
    x: adult.collar.x,
    y: adult.collar.y,
    rx: adult.collar.rx * (0.28 + 0.72 * ct),
    ry: adult.collar.ry * (0.22 + 0.78 * ct),
  };

  return { strokes, flowers, tips, roots, blobs, leaves, collar };
}

function growScarFlora(
  rng: Rng,
  surfaceY: number,
  scale: number,
  strokes: TreeStroke[],
): void {
  const tufts = 3 + Math.floor(rng() * 3);
  for (let i = 0; i < tufts; i++) {
    const a = -Math.PI / 2 + range(rng, -0.7, 0.7);
    const len = (2.2 + rng() * 4.2) * scale;
    const ox = range(rng, -3.2, 3.2) * scale;
    const base: Pt = { x: ox, y: surfaceY + 0.6 * scale };
    const pts = curveStroke(rng, base, a, len, 7, 0.48, 0.08, false);
    strokes.push({
      points: pts,
      widthStart: 1.25 * scale,
      widthEnd: 0.45 * scale,
      kind: 'tuft',
      emerge: 0.12 + rng() * 0.18,
      span: 0.16 + rng() * 0.1,
    });
  }

  const grasses = 8 + Math.floor(rng() * 6);
  for (let i = 0; i < grasses; i++) {
    const side = i % 2 === 0 ? -1 : 1;
    const a = -Math.PI / 2 + side * range(rng, 0.55, 1.42);
    const len = (3.4 + rng() * 6.8) * scale;
    const ox = side * range(rng, 1.1, 7.8) * scale;
    const base: Pt = { x: ox, y: surfaceY + 0.85 * scale };
    const pts = curveStroke(rng, base, a, len, 9, 0.62, 0.22, false);
    strokes.push({
      points: pts,
      widthStart: 1.08 * scale,
      widthEnd: 0.28 * scale,
      kind: 'grass',
      emerge: 0.16 + rng() * 0.38,
      span: 0.16 + rng() * 0.18,
    });
  }
}

/** Wood spine: collar stub, then a 5–30% height S-curve toward the canopy. */
function growSpine(
  rng: Rng,
  surfaceY: number,
  height: number,
  lean: number,
  curl: number,
  bend: number,
): { points: Pt[]; surfaceIndex: number } {
  const stub = 5.5;
  const total = height + stub;
  const steps = Math.max(28, Math.round(total / 3.2));
  const points: Pt[] = [];
  const x0 = range(rng, -2.2, 2.2);
  let wander = range(rng, -curl, curl) * 0.2;
  let surfaceIndex = 0;
  let bestSurf = Infinity;

  const tSurf = stub / total;
  const waves = range(rng, 0.45, 0.95);
  const phase = range(rng, 0, Math.PI * 2);
  const amp = bend * height;
  const leanAmp = lean * height * 0.2;

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    wander += range(rng, -curl, curl) * 0.18;
    wander *= 0.94;
    const above = t < tSurf ? 0 : (t - tSurf) / Math.max(1e-4, 1 - tSurf);
    const env = above * above * (3 - 2 * above);
    const x =
      x0 +
      wander * 3.5 +
      leanAmp * above +
      Math.sin(above * waves * Math.PI * 2 + phase) * amp * env;
    const y = surfaceY + stub - t * total;
    points.push({ x, y });
    const dist = Math.abs(y - surfaceY);
    if (dist < bestSurf) {
      bestSurf = dist;
      surfaceIndex = i;
    }
  }

  return { points, surfaceIndex };
}

/**
 * Dendritic roots that leave the collar and chemotax toward the core.
 * Dichotomous forks + terminal arbor near the well.
 */
function growNervousRoots(
  rng: Rng,
  collar: Pt,
  core: Pt,
  collarW: number,
  scale: number,
  energyRich: boolean,
  emerge: number,
  span: number,
  roots: TreeStroke[],
): void {
  const reach = Math.hypot(core.x - collar.x, core.y - collar.y);
  const baseAngle = Math.atan2(core.y - collar.y, core.x - collar.x);
  const axonCount = (energyRich ? 6 : 5) + Math.floor(rng() * 3);
  const maxDepth = energyRich ? 4 : 3;

  // Slightly thicker tap axon aimed at the well.
  growNeuronAxon(
    rng,
    collar,
    baseAngle + range(rng, -0.12, 0.12),
    reach * range(rng, 0.92, 1.08),
    collarW * 0.78,
    0,
    maxDepth,
    core,
    reach,
    scale,
    emerge,
    span * 0.92,
    true,
    energyRich,
    roots,
  );

  for (let i = 0; i < axonCount; i++) {
    const side = i % 2 === 0 ? -1 : 1;
    const cone = (0.28 + (i / Math.max(1, axonCount - 1)) * 0.95) * side;
    const wobble = range(rng, -0.18, 0.18);
    growNeuronAxon(
      rng,
      {
        x: collar.x + range(rng, -1.4, 1.4) * scale,
        y: collar.y + range(rng, 0.2, 1.6) * scale,
      },
      baseAngle + cone + wobble,
      reach * range(rng, 0.55, 0.98),
      collarW * range(rng, 0.32, 0.55),
      0,
      maxDepth,
      core,
      reach,
      scale,
      emerge + span * (0.04 + (i / axonCount) * 0.12),
      Math.max(0.16, span * (0.55 + rng() * 0.3)),
      false,
      energyRich,
      roots,
    );
  }
}

function growNeuronAxon(
  rng: Rng,
  origin: Pt,
  angle: number,
  length: number,
  widthStart: number,
  depth: number,
  maxDepth: number,
  core: Pt,
  reach: number,
  scale: number,
  emerge: number,
  span: number,
  isTap: boolean,
  energyRich: boolean,
  roots: TreeStroke[],
): void {
  if (length < 4 * scale || widthStart < 0.28 * scale) return;

  const stepLen = Math.max(2.4, (isTap ? 3.6 : 3.1) * scale);
  const maxSteps = Math.max(6, Math.round(length / stepLen));
  const pts: Pt[] = [{ x: origin.x, y: origin.y }];
  let x = origin.x;
  let y = origin.y;
  let a = angle;
  let wander = range(rng, -0.2, 0.2);
  let stoppedNearCore = false;

  for (let i = 1; i <= maxSteps; i++) {
    const dist = Math.hypot(core.x - x, core.y - y);
    const proximity = 1 - Math.min(1, dist / Math.max(1e-3, reach));
    const tropismK = 0.06 + 0.42 * proximity * proximity;
    const toCore = Math.atan2(core.y - y, core.x - x);

    wander += range(rng, -0.38, 0.38) * (1.05 - proximity * 0.7);
    wander *= 0.82;
    a += wander;
    a += shortestAngle(a, toCore) * tropismK;

    const step = Math.min(stepLen, dist * 0.55 + 1.2);
    const nx = x + Math.cos(a) * step;
    const ny = y + Math.sin(a) * step;
    const nextDist = Math.hypot(core.x - nx, core.y - ny);

    // Stop before overshooting the well.
    if (nextDist > dist && proximity > 0.72) {
      stoppedNearCore = true;
      break;
    }
    if (nextDist < Math.max(3.5, 5 * scale)) {
      pts.push({ x: nx, y: ny });
      x = nx;
      y = ny;
      stoppedNearCore = true;
      break;
    }

    pts.push({ x: nx, y: ny });
    x = nx;
    y = ny;
  }

  if (pts.length < 2) return;

  const tipW = Math.max(
    0.32 * scale,
    widthStart * (stoppedNearCore ? 0.2 : 0.12),
  );
  roots.push({
    points: pts,
    widthStart,
    widthEnd: tipW,
    kind: 'root',
    emerge,
    span,
  });

  const end = pts[pts.length - 1]!;
  const pre = pts[pts.length - 2] ?? origin;
  const endAngle = Math.atan2(end.y - pre.y, end.x - pre.x);
  const tipDist = Math.hypot(core.x - end.x, core.y - end.y);
  const nearCore = tipDist < reach * 0.28;

  if (nearCore || stoppedNearCore) {
    const arborN = (energyRich ? 3 : 2) + Math.floor(rng() * (energyRich ? 3 : 2));
    for (let k = 0; k < arborN; k++) {
      const side = k % 2 === 0 ? -1 : 1;
      const filamentLen = (6 + rng() * 10) * scale * (energyRich ? 1.15 : 1);
      growNeuronAxon(
        rng,
        end,
        endAngle + side * (0.55 + rng() * 1.1) + range(rng, -0.2, 0.2),
        filamentLen,
        Math.max(0.28 * scale, tipW * 0.7),
        maxDepth,
        maxDepth,
        core,
        reach,
        scale,
        emerge + span * 0.72,
        Math.max(0.1, span * 0.35),
        false,
        energyRich,
        roots,
      );
    }
    return;
  }

  if (depth >= maxDepth) return;

  // Dichotomous fork.
  const forkCount = depth === 0 && rng() > 0.35 ? 2 : rng() > 0.22 ? 2 : 1;
  for (let k = 0; k < forkCount; k++) {
    const side = k === 0 ? -1 : 1;
    const forkAngle =
      endAngle +
      side * (0.35 + rng() * 0.75) * (forkCount === 1 ? (rng() > 0.5 ? 1 : -1) : 1);
    const childLen = length * (0.42 + rng() * 0.32) * (isTap ? 0.9 : 1);
    growNeuronAxon(
      rng,
      end,
      forkAngle,
      childLen,
      Math.max(0.3 * scale, widthStart * (0.42 + rng() * 0.18)),
      depth + 1,
      maxDepth,
      core,
      reach,
      scale,
      emerge + span * (0.45 + rng() * 0.2),
      Math.max(0.12, span * (0.4 + rng() * 0.2)),
      false,
      energyRich,
      roots,
    );
  }
}

function spawnLaterals(
  rng: Rng,
  spine: Pt[],
  fromIdx: number,
  toIdx: number,
  count: number,
  spread: number,
  curl: number,
  droop: number,
  isRoot: boolean,
  depth: number,
  maxDepth: number,
  scale: number,
  parentEmerge: number,
  parentSpan: number,
  strokes: TreeStroke[],
  flowers: TreeFlower[],
  tips: TreeTip[],
  roots: TreeStroke[],
  leaves: TreeLeaf[],
): void {
  const idxSpan = Math.max(1, toIdx - fromIdx);
  for (let k = 0; k < count; k++) {
    const t = 0.34 + ((k + 0.2 + rng() * 0.32) / count) * 0.56;
    const idx = Math.max(
      fromIdx + 1,
      Math.min(toIdx - 1, fromIdx + Math.round(t * idxSpan)),
    );
    const p = spine[idx]!;
    const prev = spine[Math.max(0, idx - 1)]!;
    const stemA = Math.atan2(p.y - prev.y, p.x - prev.x);
    const side = k % 2 === 0 ? -1 : 1;
    const fork = side * (0.34 + t * 0.18 + rng() * spread * 0.28);
    const len = (isRoot ? 20 : 30 + t * 18) * scale * (0.72 + rng() * 0.32);
    const w = (isRoot ? 2.1 : 3.15) * scale * (1 - t * 0.38);
    const emerge = parentEmerge + parentSpan * t * 0.82 + rng() * 0.03;
    const span = Math.max(0.14, parentSpan * (0.48 + rng() * 0.22));
    growBranch(
      rng,
      p,
      stemA + fork,
      len,
      Math.max(0.7, w),
      curl * (1.02 + rng() * 0.22),
      droop,
      isRoot,
      depth,
      maxDepth,
      scale,
      emerge,
      span,
      strokes,
      flowers,
      tips,
      roots,
      leaves,
    );
  }
}

function growBranch(
  rng: Rng,
  origin: Pt,
  angle: number,
  length: number,
  widthStart: number,
  curl: number,
  droop: number,
  isRoot: boolean,
  depth: number,
  maxDepth: number,
  scale: number,
  emerge: number,
  span: number,
  strokes: TreeStroke[],
  flowers: TreeFlower[],
  tips: TreeTip[],
  roots: TreeStroke[],
  leaves: TreeLeaf[],
): void {
  if (length < 5 * scale) return;

  const steps = Math.max(8, Math.round(length / (isRoot ? 4.4 : 3.2)));
  const pts = curveStroke(
    rng,
    origin,
    angle,
    length,
    steps,
    curl * (1 + depth * 0.05),
    droop,
    isRoot,
  );
  const widthEnd = Math.max(0.55, widthStart * (depth >= maxDepth ? 0.28 : 0.46));
  const kind: TreeStroke['kind'] = isRoot
    ? 'root'
    : depth >= maxDepth - 1 || widthStart < 1.15 * scale
      ? 'twig'
      : 'wood';
  const stroke: TreeStroke = {
    points: pts,
    widthStart,
    widthEnd,
    kind,
    emerge,
    span,
  };
  if (isRoot) roots.push(stroke);
  else strokes.push(stroke);

  if (!isRoot && depth <= 1 && rng() < 0.42) {
    sprinkleLeaves(rng, pts, scale, emerge, span, leaves);
  }

  const end = pts[pts.length - 1]!;
  const pre = pts[pts.length - 2] ?? origin;
  const endAngle = Math.atan2(end.y - pre.y, end.x - pre.x);
  const tipEmerge = emerge + span * 0.9;

  if (!isRoot && (depth >= maxDepth || length < 14 * scale)) {
    tips.push({ x: end.x, y: end.y, angle: endAngle, emerge: tipEmerge });
    if (rng() < 0.85) {
      flowers.push({
        x: end.x,
        y: end.y,
        angle: endAngle,
        size: (6.5 + rng() * 3.5) * scale,
        emerge: Math.min(0.4, emerge + span * 0.5),
        span: 0.16,
      });
    }
    if (rng() < 0.55 && length > 8 * scale) {
      const twigLen = length * (0.28 + rng() * 0.22);
      growBranch(
        rng,
        end,
        endAngle + range(rng, -0.42, 0.42),
        twigLen,
        Math.max(0.5, widthEnd),
        curl * 1.1,
        droop * 1.12,
        false,
        depth + 1,
        maxDepth,
        scale,
        emerge + span * 0.86,
        Math.max(0.12, span * 0.55),
        strokes,
        flowers,
        tips,
        roots,
        leaves,
      );
    }
    return;
  }

  if (depth >= maxDepth) {
    if (isRoot) return;
    tips.push({ x: end.x, y: end.y, angle: endAngle, emerge: tipEmerge });
    return;
  }

  const nLat = depth === 0 ? 2 : rng() < 0.62 ? 1 : rng() < 0.45 ? 2 : 0;
  for (let k = 0; k < nLat; k++) {
    const t = 0.48 + rng() * 0.4;
    const idx = Math.max(1, Math.min(pts.length - 2, Math.round(t * (pts.length - 1))));
    const p = pts[idx]!;
    const p0 = pts[idx - 1]!;
    const a = Math.atan2(p.y - p0.y, p.x - p0.x);
    const side = nLat === 1 ? (rng() > 0.5 ? 1 : -1) : k === 0 ? -1 : 1;
    growBranch(
      rng,
      p,
      a + side * (0.32 + rng() * 0.38),
      length * (0.5 + rng() * 0.22),
      Math.max(0.55, widthStart * (1 - t * 0.55) * 0.7),
      curl * 1.08,
      droop,
      isRoot,
      depth + 1,
      maxDepth,
      scale,
      emerge + span * t * 0.8,
      Math.max(0.12, span * (0.45 + rng() * 0.2)),
      strokes,
      flowers,
      tips,
      roots,
      leaves,
    );
  }

  if (!isRoot && rng() < 0.7) {
    growBranch(
      rng,
      end,
      endAngle + range(rng, -0.28, 0.28),
      length * (0.38 + rng() * 0.18),
      widthEnd,
      curl * 1.15,
      droop * 1.08,
      false,
      depth + 1,
      maxDepth,
      scale,
      emerge + span * 0.88,
      Math.max(0.12, span * 0.5),
      strokes,
      flowers,
      tips,
      roots,
      leaves,
    );
  } else if (!isRoot) {
    tips.push({ x: end.x, y: end.y, angle: endAngle, emerge: tipEmerge });
    if (rng() < 0.8) {
      flowers.push({
        x: end.x,
        y: end.y,
        angle: endAngle,
        size: (6.5 + rng() * 3.5) * scale,
        emerge: Math.min(0.4, emerge + span * 0.5),
        span: 0.18,
      });
    }
  }
}

function curveStroke(
  rng: Rng,
  origin: Pt,
  angle: number,
  length: number,
  steps: number,
  curl: number,
  droop: number,
  isRoot: boolean,
): Pt[] {
  const pts: Pt[] = [{ x: origin.x, y: origin.y }];
  let x = origin.x;
  let y = origin.y;
  let wander = range(rng, -curl, curl) * 0.28;
  const tropism = isRoot ? Math.PI / 2 : -Math.PI / 2;
  const tropismK = isRoot ? 0.13 : 0.04;
  const waves = range(rng, isRoot ? 0.9 : 0.35, isRoot ? 1.7 : 0.9);
  const phase = range(rng, 0, Math.PI * 2);
  const waveAmp = curl * range(rng, 1.05, 1.85);
  const arc = range(rng, -1, 1) * curl * 1.55;
  const tipCurl = isRoot ? range(rng, -curl, curl) * 0.7 : range(rng, -1, 1) * curl * 1.05;
  const n = Math.max(steps, 4);
  for (let i = 1; i <= n; i++) {
    const t = i / n;
    wander += range(rng, -curl, curl) * (isRoot ? 0.72 : 0.18);
    wander *= isRoot ? 0.86 : 0.94;
    const env = isRoot ? 0.5 + 0.5 * t : 0.28 + 0.72 * t;
    const wave = Math.sin(t * waves * Math.PI * 2 + phase) * waveAmp * env;
    const droopBend = droop * t * t * (isRoot ? 0.35 : 1.35);
    const tendril = tipCurl * Math.max(0, (t - 0.78) / 0.22);
    let a = angle + arc * t + wave + wander + droopBend + tendril;
    a += shortestAngle(a, tropism) * tropismK;
    const step = length / n;
    x += Math.cos(a) * step;
    y += Math.sin(a) * step;
    pts.push({ x, y });
  }
  return pts;
}

function sprinkleLeaves(
  rng: Rng,
  pts: Pt[],
  scale: number,
  emerge: number,
  span: number,
  leaves: TreeLeaf[],
): void {
  if (pts.length < 3) return;
  const n = rng() > 0.55 ? 2 : 1;
  for (let i = 0; i < n; i++) {
    const t = 0.4 + rng() * 0.55;
    const idx = Math.max(1, Math.min(pts.length - 1, Math.round(t * (pts.length - 1))));
    const p = pts[idx]!;
    const p0 = pts[idx - 1]!;
    const a = Math.atan2(p.y - p0.y, p.x - p0.x);
    leaves.push({
      x: p.x + range(rng, -1.15, 1.15) * scale,
      y: p.y + range(rng, -1.15, 1.15) * scale,
      angle: a + range(rng, -0.95, 0.95) + 0.32,
      length: (4.6 + rng() * 7.2) * scale,
      width: (1.12 + rng() * 1.28) * scale,
      emerge: emerge + span * t * 0.65,
      span: 0.16 + rng() * 0.08,
    });
  }
}

function paintCanopy(
  tips: TreeTip[],
  flowers: TreeFlower[],
  blobs: TreeBlob[],
  leaves: TreeLeaf[],
  rng: Rng,
  scale: number,
): void {
  if (tips.length === 0) return;
  let cx = 0;
  let cy = 0;
  for (const t of tips) {
    cx += t.x;
    cy += t.y;
  }
  cx /= tips.length;
  cy /= tips.length;
  let spanR = 0;
  for (const t of tips) {
    spanR = Math.max(spanR, Math.hypot(t.x - cx, t.y - cy));
  }

  blobs.push({
    x: cx,
    y: cy,
    r: Math.max(36 * scale, spanR * 1.08 + 10 * scale),
    alpha: 0.16,
    emerge: 0.48,
    span: 0.38,
  });
  for (const t of tips) {
    const tipEmerge = t.emerge ?? 0.62;
    blobs.push({
      x: t.x + range(rng, -4, 4) * scale,
      y: t.y + range(rng, -4, 4) * scale,
      r: (5 + rng() * 9) * scale,
      alpha: 0.07 + rng() * 0.09,
      emerge: tipEmerge - 0.06,
      span: 0.28,
    });
    const n = 2 + (rng() > 0.4 ? 1 : 0);
    for (let i = 0; i < n; i++) {
      leaves.push({
        x: t.x + range(rng, -2.2, 2.2) * scale,
        y: t.y + range(rng, -2.2, 2.2) * scale,
        angle: t.angle + range(rng, -0.65, 0.65) + 0.32,
        length: (5.2 + rng() * 7.4) * scale,
        width: (1.22 + rng() * 1.28) * scale,
        emerge: tipEmerge + rng() * 0.08,
        span: 0.18 + rng() * 0.08,
      });
    }
  }
  for (const f of flowers) {
    blobs.push({
      x: f.x,
      y: f.y,
      r: f.size * 2.2,
      alpha: 0.16,
      emerge: (f.emerge ?? 0.72) - 0.04,
      span: 0.22,
    });
  }
}

function growthProgress(maturity: number, emerge: number, span: number): number {
  if (span <= 1e-6) return maturity >= emerge ? 1 : 0;
  return smoothstep(emerge, emerge + span, maturity);
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function clipStroke(stroke: TreeStroke, t: number): TreeStroke | null {
  if (t <= 0.012) return null;
  if (t >= 0.999) return stroke;

  const pts = stroke.points;
  if (pts.length < 2) return null;

  const lens: number[] = [0];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1]!;
    const b = pts[i]!;
    total += Math.hypot(b.x - a.x, b.y - a.y);
    lens.push(total);
  }
  if (total < 1e-4) return null;

  const eased = t;
  const target = Math.max(total * eased, Math.min(1.4, total * 0.04));
  const clipped: Pt[] = [{ x: pts[0]!.x, y: pts[0]!.y }];
  for (let i = 1; i < pts.length; i++) {
    if (lens[i]! <= target) {
      clipped.push(pts[i]!);
      continue;
    }
    const prev = pts[i - 1]!;
    const next = pts[i]!;
    const seg = lens[i]! - lens[i - 1]!;
    const u = seg > 1e-6 ? (target - lens[i - 1]!) / seg : 1;
    clipped.push({
      x: prev.x + (next.x - prev.x) * u,
      y: prev.y + (next.y - prev.y) * u,
    });
    break;
  }

  if (clipped.length < 2) {
    const d = pts[1]!;
    const len = Math.hypot(d.x - pts[0]!.x, d.y - pts[0]!.y) || 1;
    clipped.push({
      x: pts[0]!.x + ((d.x - pts[0]!.x) / len) * target,
      y: pts[0]!.y + ((d.y - pts[0]!.y) / len) * target,
    });
  }

  const widthStart = stroke.widthStart * (0.38 + 0.62 * t);
  const widthEnd = widthStart * (0.18 + 0.82 * t) * (stroke.widthEnd / Math.max(stroke.widthStart, 0.01));
  return {
    points: clipped,
    widthStart,
    widthEnd: Math.max(0.35, widthEnd),
    kind: stroke.kind,
  };
}

function shortestAngle(from: number, to: number): number {
  let d = to - from;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
}

/** Min bloom growth (0..1) before a flower sheds pollen. */
export const FLOWER_POLLEN_OPEN = 0.22;
/** Min bloom growth (0..1) before a flower may drop a seedling. */
export const FLOWER_SPAWN_READY = 0.45;

/**
 * World-space flowers open enough for pollen or seedling spawn.
 * Uses adult bloom positions so effects leave the blooms, not clipped tips.
 */
export function treeFlowersWorld(
  seed: number,
  maturity: number,
  scale: number,
  originX: number,
  originY: number,
  rotation: number,
  coreDepth: number,
  surfaceY = 0,
  kind: TreeKind = 'dyson',
  minOpen = FLOWER_POLLEN_OPEN,
): TreeFlower[] {
  const adult = buildAdultTree(seed, scale, coreDepth, surfaceY, kind);
  const c = Math.cos(rotation);
  const s = Math.sin(rotation);
  const out: TreeFlower[] = [];
  for (const f of adult.flowers) {
    const t = growthProgress(maturity, f.emerge ?? 0.72, f.span ?? 0.2);
    if (t < minOpen) continue;
    out.push({
      x: originX + f.x * c - f.y * s,
      y: originY + f.x * s + f.y * c,
      angle: f.angle + rotation,
      size: f.size * (0.12 + 0.88 * t),
      emerge: f.emerge,
      span: f.span,
    });
  }
  return out;
}

/** World-space branch tips for budding seedlings. */
export function treeTipsWorld(
  seed: number,
  maturity: number,
  scale: number,
  originX: number,
  originY: number,
  rotation: number,
  coreDepth: number,
  surfaceY = 0,
): TreeTip[] {
  const geom = buildTree(seed, maturity, scale, coreDepth, surfaceY);
  const c = Math.cos(rotation);
  const s = Math.sin(rotation);
  return geom.tips.map((t) => ({
    x: originX + t.x * c - t.y * s,
    y: originY + t.x * s + t.y * c,
    angle: t.angle + rotation,
  }));
}

export function maturityStep(maturity: number): number {
  return Math.floor(Math.min(1, Math.max(0, maturity)) / 0.05);
}

export function buildLSystemSegments(
  seed: number,
  maturity: number,
  scale = 1,
): { x0: number; y0: number; x1: number; y1: number }[] {
  const geom = buildTree(seed, maturity, scale);
  const segs: { x0: number; y0: number; x1: number; y1: number }[] = [];
  for (const st of [...geom.strokes, ...geom.roots]) {
    for (let i = 1; i < st.points.length; i++) {
      const a = st.points[i - 1]!;
      const b = st.points[i]!;
      segs.push({ x0: a.x, y0: a.y, x1: b.x, y1: b.y });
    }
  }
  return segs;
}
