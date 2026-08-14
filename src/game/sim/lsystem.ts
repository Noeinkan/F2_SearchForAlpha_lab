import { mulberry32, range } from './rng';

export interface TreeStroke {
  points: { x: number; y: number }[];
  width: number;
  kind: 'wood' | 'root' | 'tuft';
  color?: number;
}

export interface TreeFlower {
  x: number;
  y: number;
  angle: number;
  size: number;
}

export interface TreeTip {
  x: number;
  y: number;
  angle: number;
}

export interface TreeGeom {
  strokes: TreeStroke[];
  flowers: TreeFlower[];
  tips: TreeTip[];
  roots: TreeStroke[];
}

type Rng = () => number;

/**
 * Hairline fractal plant: thin branching capillaries, buds at tips,
 * glowing roots aimed at the asteroid core (local +Y).
 */
export function buildTree(
  seed: number,
  maturity: number,
  scale = 1,
  coreDepth = 70,
): TreeGeom {
  const rng = mulberry32(seed >>> 0);
  const m = Math.min(1, Math.max(0.06, maturity));
  const strokes: TreeStroke[] = [];
  const flowers: TreeFlower[] = [];
  const tips: TreeTip[] = [];
  const roots: TreeStroke[] = [];

  const height = scale * (56 + m * 88);
  const maxDepth = 3 + Math.floor(m * 3);
  const lean = range(rng, -0.18, 0.18);

  branch(
    rng,
    { x: 0, y: 0 },
    -Math.PI / 2 + lean,
    height,
    Math.max(1.05, 1.7 * scale),
    0,
    maxDepth,
    m,
    strokes,
    flowers,
    tips,
  );

  // Grass tufts at the planting scar
  const tufts = 4 + Math.floor(rng() * 4);
  for (let i = 0; i < tufts; i++) {
    const a = -Math.PI / 2 + range(rng, -0.9, 0.9);
    const len = (4 + rng() * 7) * scale;
    strokes.push({
      points: [
        { x: range(rng, -3, 3) * scale, y: 1 },
        {
          x: Math.cos(a) * len * 0.5,
          y: Math.sin(a) * len * 0.5,
        },
        { x: Math.cos(a) * len, y: Math.sin(a) * len },
      ],
      width: 1.1 * scale,
      kind: 'tuft',
    });
  }

  // Roots: 2–3 wavy lines from the scar toward the core (local +Y)
  const rootN = 2 + (rng() > 0.45 ? 1 : 0);
  const depth = coreDepth * (0.72 + rng() * 0.12);
  for (let i = 0; i < rootN; i++) {
    const pts: { x: number; y: number }[] = [{ x: range(rng, -2, 2), y: 2 }];
    const segs = 7;
    const side = (i - (rootN - 1) / 2) * 0.35;
    for (let s = 1; s <= segs; s++) {
      const t = s / segs;
      const y = 2 + depth * t;
      const wave = Math.sin(t * Math.PI * (1.4 + rng()) + i) * (8 + i * 4) * scale;
      const pull = (1 - t) * side * 14 * scale;
      pts.push({
        x: wave * (1 - t * 0.7) + pull * (1 - t),
        y,
      });
    }
    // Converge on core
    pts.push({ x: range(rng, -3, 3), y: depth + 4 });
    roots.push({
      points: pts,
      width: Math.max(0.9, (1.8 - i * 0.35) * scale),
      kind: 'root',
    });
  }

  return { strokes, flowers, tips, roots };
}

function branch(
  rng: Rng,
  origin: { x: number; y: number },
  angle: number,
  length: number,
  width: number,
  depth: number,
  maxDepth: number,
  maturity: number,
  strokes: TreeStroke[],
  flowers: TreeFlower[],
  tips: TreeTip[],
): void {
  const n = 4 + (depth === 0 ? 3 : 0);
  const pts: { x: number; y: number }[] = [{ x: origin.x, y: origin.y }];
  let a = angle;
  let x = origin.x;
  let y = origin.y;
  const curl = range(rng, -0.28, 0.28);
  for (let i = 1; i <= n; i++) {
    a += curl / n + range(rng, -0.06, 0.06);
    const step = length / n;
    x += Math.cos(a) * step;
    y += Math.sin(a) * step;
    pts.push({ x, y });
  }
  strokes.push({ points: pts, width, kind: 'wood' });

  const end = pts[pts.length - 1]!;
  const endAngle = Math.atan2(
    end.y - pts[pts.length - 2]!.y,
    end.x - pts[pts.length - 2]!.x,
  );

  if (depth >= maxDepth || length < 8) {
    tips.push({ x: end.x, y: end.y, angle: endAngle });
    if (rng() < 0.45 + maturity * 0.4) {
      flowers.push({
        x: end.x,
        y: end.y,
        angle: endAngle,
        size: 2.2 + rng() * 2.4,
      });
    }
    return;
  }

  const splits = depth === 0 ? 2 + (rng() > 0.35 ? 1 : 0) : rng() < 0.18 ? 1 : 2;
  const spread = 0.38 + rng() * 0.34;
  for (let i = 0; i < splits; i++) {
    const side = splits === 1 ? range(rng, -0.2, 0.2) : i === 0 ? -spread : spread;
    const extra = splits === 3 && i === 2 ? range(rng, -0.15, 0.15) : 0;
    branch(
      rng,
      end,
      endAngle + side + extra,
      length * (0.55 + rng() * 0.22),
      Math.max(0.55, width * 0.62),
      depth + 1,
      maxDepth,
      maturity,
      strokes,
      flowers,
      tips,
    );
  }
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
): TreeTip[] {
  const geom = buildTree(seed, maturity, scale, coreDepth);
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
  for (const st of geom.strokes) {
    for (let i = 1; i < st.points.length; i++) {
      const a = st.points[i - 1]!;
      const b = st.points[i]!;
      segs.push({ x0: a.x, y0: a.y, x1: b.x, y1: b.y });
    }
  }
  return segs;
}
