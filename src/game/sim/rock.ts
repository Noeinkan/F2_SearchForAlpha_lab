import { mulberry32, range, type Rng } from './rng';
import {
  HOME_RADIUS_SCALE,
  ROCK_RADIUS_MAX,
  ROCK_RADIUS_MIN,
  ROCK_SURFACE_INSET,
} from './types';

export interface RockBody {
  radius: number;
  seed: number;
}

interface Lump {
  freq: number;
  amp: number;
  phase: number;
}

/** Many small moons, fewer giants. Home worlds sit in the upper half, then scale up. */
export function pickRockRadius(rng: Rng, bias: 'any' | 'home' = 'any'): number {
  let u = rng();
  if (bias === 'home') u = 0.5 + u * 0.5;
  const skew = bias === 'home' ? 1.12 : 1.65;
  const t = Math.pow(u, skew);
  const radius = ROCK_RADIUS_MIN + t * (ROCK_RADIUS_MAX - ROCK_RADIUS_MIN);
  return bias === 'home' ? radius * HOME_RADIUS_SCALE : radius;
}

function lumpsFor(seed: number, radius: number): Lump[] {
  const rng = mulberry32((seed ^ 0xb10b5eed) >>> 0);
  const t = Math.min(
    1,
    Math.max(0, (radius - ROCK_RADIUS_MIN) / (ROCK_RADIUS_MAX - ROCK_RADIUS_MIN)),
  );
  const lumpiness = 0.125 - t * 0.05;
  const lumps: Lump[] = [
    {
      freq: 2,
      amp: range(rng, 0.03, 0.085) * (0.75 + lumpiness),
      phase: rng() * Math.PI * 2,
    },
  ];
  const extra = 2 + Math.floor(rng() * 2);
  for (let i = 0; i < extra; i++) {
    lumps.push({
      freq: 3 + i,
      amp: (lumpiness * range(rng, 0.3, 0.72)) / (i + 1.2),
      phase: rng() * Math.PI * 2,
    });
  }
  return lumps;
}

/** Mean radius times a gentle potato — small rocks lumpier than large ones. */
export function rockRadiusAt(rock: RockBody, angle: number): number {
  let scale = 1;
  for (const lump of lumpsFor(rock.seed, rock.radius)) {
    scale += lump.amp * Math.cos(lump.freq * angle + lump.phase);
  }
  return rock.radius * scale;
}

export function rockOutline(
  rock: RockBody,
  steps = 56,
): { x: number; y: number }[] {
  const pts: { x: number; y: number }[] = [];
  for (let i = 0; i < steps; i++) {
    const a = (i / steps) * Math.PI * 2;
    const r = rockRadiusAt(rock, a);
    pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r });
  }
  return pts;
}

export function slotAngle(
  slotIndex: number,
  treeSlots: number,
  seed: number,
): number {
  const base = -Math.PI / 2 + (slotIndex / Math.max(1, treeSlots)) * Math.PI * 2;
  const span = (Math.PI * 2) / Math.max(2, treeSlots);
  const rng = mulberry32((seed ^ Math.imul(slotIndex + 3, 0x9e3779b9)) >>> 0);
  return base + range(rng, -1, 1) * span * 0.16;
}

/** Collar pose on the crust at an arbitrary bearing. */
export function crustPolar(
  rock: RockBody,
  angle: number,
): { angle: number; rim: number; dist: number; surfaceY: number } {
  const rim = rockRadiusAt(rock, angle);
  const inset = rock.radius * ROCK_SURFACE_INSET;
  const dist = Math.max(rim * 0.55, rim - inset);
  return {
    angle,
    rim,
    dist,
    /** Tree-local Y of the lumpy rim. Collar at this Y sits on the crust. */
    surfaceY: dist - rim,
  };
}

export function slotPolar(
  rock: RockBody & { treeSlots: number },
  slotIndex: number,
): { angle: number; rim: number; dist: number; surfaceY: number } {
  return crustPolar(rock, slotAngle(slotIndex, rock.treeSlots, rock.seed));
}

/** Nearest rock whose lumpy rim sits within `pad` world units of (wx, wy). */
export function hitRockCrust(
  rocks: Iterable<RockBody & { id: number; x: number; y: number }>,
  wx: number,
  wy: number,
  pad: number,
): { id: number; angle: number } | null {
  let best: { id: number; angle: number } | null = null;
  let bestErr = pad;
  for (const rock of rocks) {
    const dx = wx - rock.x;
    const dy = wy - rock.y;
    const dist = Math.hypot(dx, dy);
    const angle = Math.atan2(dy, dx);
    const err = Math.abs(dist - rockRadiusAt(rock, angle));
    if (err <= bestErr) {
      bestErr = err;
      best = { id: rock.id, angle };
    }
  }
  return best;
}
