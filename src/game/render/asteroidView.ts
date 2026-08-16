import { Container, Graphics, Text } from 'pixi.js';
import {
  groveSpread,
  lifeDensity,
  lifeLushScale,
  lifeProximity,
  lifeReach,
  lifeSpread,
  shortestAngle,
} from '../sim/life';
import { rootFeedActive } from '../sim/lsystem';
import { mulberry32, range } from '../sim/rng';
import { rockOutline, rockRadiusAt, slotPolar } from '../sim/rock';
import {
  canPlantKind,
  type Asteroid,
  type FactionId,
  type Tree,
  type TreeKind,
  type World,
} from '../sim/types';
import {
  getOccupiedSlots,
  hasHostileOrbiters,
  hasHostileTrees,
  slotPosition,
} from '../sim/world';
import {
  floraEquals,
  factionCoreHue,
  floraPalette,
  hslToHex,
  mixHex,
  sapRiseU,
  sapStage,
  SAP_WINDOW,
  type FloraPalette,
  type ScenePalette,
} from './palette';

const NO_TREES: Tree[] = [];
const SUBSTRATE_BINS = 120;

export class AsteroidView {
  readonly root = new Container();
  readonly asteroidId: number;
  private core: Graphics;
  private slotsGfx: Graphics;
  private selectionRing: Graphics;
  private label: Text;
  private pal: FloraPalette;
  private rock: Graphics;
  private film: Graphics;
  private grass: Graphics;
  private grassSap: Graphics;
  private pollenGfx: Graphics;
  private halo: Graphics;
  private lastSelected = false;
  private lastPlantKey = '';
  private lastOwner: FactionId;
  private lastShieldKey = '';
  private lastShield = -1;
  private lastLifeKey = '';
  private lastFeedKey = '';
  private hitPulseUntil = 0;
  private pulsePhase: number;
  private bits: GrassBit[] = [];
  private fieldKey = '';
  private localTrees: Tree[] = NO_TREES;
  private pollen: PollenGrain[] = [];
  private pollenAcc = 0;
  private pollenTime = 0;
  private pollenRng: () => number;
  private substrate: Float32Array = new Float32Array(SUBSTRATE_BINS);
  private filmJitter: Float32Array = new Float32Array(SUBSTRATE_BINS);
  private seededTrees = new Set<number>();

  constructor(asteroid: Asteroid, scene: ScenePalette) {
    this.asteroidId = asteroid.id;
    this.pal = floraPalette(asteroid.stats, asteroid.seed, scene);
    this.lastOwner = asteroid.owner;
    this.lastShield = asteroid.shield;
    this.pulsePhase = (asteroid.seed % 1000) * 0.013;
    this.pollenRng = mulberry32((asteroid.seed ^ 0x51ed) >>> 0);
    const jitterRng = mulberry32((asteroid.seed ^ 0x51edc0de) >>> 0);
    for (let i = 0; i < SUBSTRATE_BINS; i++) this.filmJitter[i] = jitterRng();
    this.root.position.set(asteroid.x, asteroid.y);

    this.halo = new Graphics();
    this.root.addChild(this.halo);

    this.rock = new Graphics();
    this.root.addChild(this.rock);
    paintRock(this.rock, asteroid, this.pal);

    this.film = new Graphics();
    this.film.eventMode = 'none';
    this.root.addChild(this.film);

    this.grass = new Graphics();
    this.grass.eventMode = 'none';
    this.root.addChild(this.grass);

    this.grassSap = new Graphics();
    this.grassSap.eventMode = 'none';
    this.grassSap.blendMode = 'add';
    this.root.addChild(this.grassSap);

    this.pollenGfx = new Graphics();
    this.pollenGfx.eventMode = 'none';
    this.pollenGfx.blendMode = 'add';
    this.root.addChild(this.pollenGfx);

    this.core = new Graphics();
    this.root.addChild(this.core);

    this.selectionRing = new Graphics();
    this.root.addChild(this.selectionRing);

    this.slotsGfx = new Graphics();
    this.root.addChild(this.slotsGfx);

    this.label = new Text({
      text: asteroid.name,
      style: {
        fontFamily: 'Comfortaa, Nunito, "Segoe UI", system-ui, sans-serif',
        fontSize: 13,
        fontWeight: '600',
        fill: scene.inkSoft,
        align: 'center',
      },
    });
    this.label.anchor.set(0.5, 0);
    this.label.position.set(0, asteroid.radius + 18);
    this.label.alpha = 0.7;
    this.root.addChild(this.label);

    this.redrawCore(asteroid, false);
    this.redrawSlots(asteroid, new Set(), false);
    this.redrawHalo(asteroid, false);
  }

  update(
    asteroid: Asteroid,
    selected: boolean,
    plantableSlots: Set<number>,
    trees: Tree[] = NO_TREES,
  ): void {
    this.root.position.set(asteroid.x, asteroid.y);
    let plantKey = `${plantableSlots.size}`;
    for (const i of plantableSlots) plantKey += `,${i}`;
    const shieldKey = `${Math.round(asteroid.shield)}/${Math.round(asteroid.maxShield)}`;
    const selChanged = selected !== this.lastSelected;
    const ownerChanged = asteroid.owner !== this.lastOwner;
    const shieldChanged = shieldKey !== this.lastShieldKey;
    const now = performance.now();
    if (this.lastShield >= 0 && asteroid.shield < this.lastShield - 0.05) {
      this.hitPulseUntil = now + 280;
    }
    this.lastShield = asteroid.shield;
    this.localTrees = trees;
    const feedKey = feedKeyFor(trees);
    const feedChanged = feedKey !== this.lastFeedKey;
    if (selChanged || ownerChanged || shieldChanged || feedChanged) {
      this.redrawCore(asteroid, selected, trees);
      this.redrawHalo(asteroid, selected);
      this.lastSelected = selected;
      this.lastOwner = asteroid.owner;
      this.lastShieldKey = shieldKey;
      this.lastFeedKey = feedKey;
    }
    if (ownerChanged) {
      paintRock(this.rock, asteroid, this.pal);
    }
    if (plantKey !== this.lastPlantKey || selChanged) {
      this.redrawSlots(asteroid, plantableSlots, selected);
      this.lastPlantKey = plantKey;
    }
    this.syncGrass(asteroid, trees, now / 1000);
    this.tickPollen(asteroid, trees, now / 1000);
    if (this.label.text !== asteroid.name) this.label.text = asteroid.name;

    const t = now / 1000;
    const feed = maxFeed(trees);
    let launch = 0;
    for (const tree of trees) {
      const live = rootFeedActive(tree.maturity, tree.coreFeed);
      if (live < 0.02) continue;
      const u = sapRiseU(t, tree.seed);
      if (u < 0.16) launch = Math.max(launch, (1 - u / 0.16) * live);
    }
    const pulse =
      0.88 +
      Math.sin(t * 1.35 + this.pulsePhase) * 0.12 +
      feed * (0.06 + Math.sin(t * 2.1 + this.pulsePhase) * 0.08);
    this.core.alpha = Math.min(1.28, pulse + launch * 0.28);
    this.core.scale.set(1 + launch * 0.056);
    this.halo.alpha = 0.85 + Math.sin(t * 0.7 + this.pulsePhase) * 0.15 + launch * 0.11;
    this.halo.scale.set(1 + Math.sin(t * 0.55 + this.pulsePhase) * 0.018 + launch * 0.022);

    // Animate shield shimmer every frame when a shield is present.
    if (asteroid.maxShield > 0 && asteroid.shield > 0) {
      this.redrawShieldRing(asteroid, selected, now);
    }
  }

  private redrawShieldRing(
    asteroid: Asteroid,
    selected: boolean,
    now: number,
  ): void {
    const t = asteroid.shield / asteroid.maxShield;
    const shimmer = 0.5 + 0.5 * Math.sin(now / 1000 * 3.2 + this.pulsePhase);
    const hit = now < this.hitPulseUntil;
    const radius =
      asteroid.radius + 6 + shimmer * 1.6 + (hit ? 2.4 : 0);
    const alpha = 0.18 + t * 0.4 + shimmer * 0.12 + (hit ? 0.28 : 0);

    this.selectionRing.clear();
    this.selectionRing.circle(0, 0, radius);
    this.selectionRing.stroke({
      width: hit ? 2.8 : 2.2,
      color: this.pal.core,
      alpha: Math.min(0.95, alpha),
    });
    if (selected) {
      this.selectionRing.circle(0, 0, asteroid.radius + 10);
      this.selectionRing.stroke({
        width: 1.4,
        color: this.pal.ring,
        alpha: 0.32,
      });
    }
  }

  retheme(
    asteroid: Asteroid,
    scene: ScenePalette,
    selected: boolean,
    plantableSlots: Set<number>,
    trees: Tree[] = NO_TREES,
  ): void {
    const next = floraPalette(asteroid.stats, asteroid.seed, scene);
    if (!floraEquals(this.pal, next)) {
      this.pal = next;
      paintRock(this.rock, asteroid, this.pal);
      this.redrawCore(asteroid, selected, trees);
      this.redrawHalo(asteroid, selected);
      this.redrawSlots(asteroid, plantableSlots, selected);
      this.lastLifeKey = '';
      this.syncGrass(asteroid, trees, performance.now() / 1000);
    }
    this.label.style.fill = scene.inkSoft;
  }

  private syncGrass(asteroid: Asteroid, trees: Tree[], time: number): void {
    this.ensureField(asteroid);
    let growing = false;
    let key = `${trees.length}`;
    for (const tree of trees) {
      key += `|${tree.slotIndex}:${tree.id}:${maturityBucket(tree.maturity)}`;
      if (tree.maturity < 0.999) growing = true;
    }
    const feed = maxFeed(trees);
    // Redraw while colonizing, or every frame when sap sheen is active.
    if (!growing && feed <= 0.02 && key === this.lastLifeKey) return;
    this.lastLifeKey = key;
    paintLife(
      this.grass,
      this.grassSap,
      asteroid,
      this.pal,
      this.bits,
      trees,
      time,
      this.substrate,
    );
  }

  private ensureField(asteroid: Asteroid): void {
    const key = `${asteroid.seed}:${asteroid.radius}:${asteroid.treeSlots}`;
    if (key === this.fieldKey) return;
    this.fieldKey = key;
    this.bits = buildGrassField(asteroid);
  }

  private tickPollen(asteroid: Asteroid, trees: Tree[], time: number): void {
    const g = this.pollenGfx;
    g.clear();
    const dt = Math.min(0.05, Math.max(0, time - this.pollenTime));
    this.pollenTime = time;
    const rng = this.pollenRng;

    const live = new Set(trees.map((t) => t.id));
    for (const id of [...this.seededTrees]) {
      if (!live.has(id)) this.seededTrees.delete(id);
    }
    if (trees.length === 0) {
      this.pollen.length = 0;
      this.pollenAcc = 0;
      for (let i = 0; i < SUBSTRATE_BINS; i++) {
        this.substrate[i] *= Math.max(0, 1 - dt * 1.8);
      }
      this.paintSubstrate(asteroid);
      return;
    }

    for (const tree of trees) {
      if (this.seededTrees.has(tree.id) || tree.maturity < 0.06) continue;
      const polar = slotPolar(asteroid, tree.slotIndex);
      const span = tree.maturity > 0.3 ? lifeReach(tree.maturity) * 0.92 : 0.14;
      this.stainArc(polar.angle, span, tree.maturity > 0.3 ? 0.62 : 0.48);
      this.seededTrees.add(tree.id);
    }

    for (const tree of trees) {
      if (tree.maturity < 0.08) continue;
      const flowers = tree.maturity > 0.42 ? 1.25 : 0.85;
      this.pollenAcc += dt * (1.15 + tree.maturity * 1.6) * flowers;
    }
    while (this.pollenAcc >= 1 && this.pollen.length < 40) {
      this.pollenAcc -= 1;
      const tree = trees[Math.floor(rng() * trees.length)]!;
      if (tree.maturity < 0.08) continue;
      this.pollen.push(spawnPollen(asteroid, tree, rng));
    }
    this.pollenAcc = Math.min(this.pollenAcc, 3);

    const next: PollenGrain[] = [];
    for (const grain of this.pollen) {
      grain.age += dt;
      const flying = grain.age < grain.life;
      const settle = flying ? 0 : grain.age - grain.life;
      if (settle > 0.85) continue;

      const u = Math.min(1, grain.age / grain.life);
      const e = u * u * (3 - 2 * u);
      const arc = shortestAngle(grain.fromTheta, grain.toTheta);
      const theta =
        grain.fromTheta +
        arc * e +
        Math.sin(time * 2.1 + grain.wobble) * 0.018 * (1 - e);
      const hover = Math.max(
        1.4,
        grain.hover + Math.sin(time * 2.4 + grain.wobble * 1.3) * 1.15 * (1 - e),
      );
      const p = crustPoint(asteroid, theta, -hover);
      if (flying) this.stain(theta, dt * 1.65);
      else if (settle < 0.08) this.stain(grain.toTheta, 0.22);

      const fade = flying
        ? 0.28 + 0.4 * (1 - u)
        : Math.max(0, 0.45 * (1 - settle / 0.85));
      const size = flying
        ? grain.size * (0.75 + 0.4 * (1 - u))
        : grain.size * (1.05 + settle * 1.4);
      g.circle(p.x, p.y, size);
      g.fill({
        color: mixHex(this.pal.flower, this.pal.film, 0.35 + grain.size * 0.2),
        alpha: fade,
      });
      g.circle(p.x, p.y, size * 0.38);
      g.fill({ color: this.pal.coreWhite, alpha: fade * 0.55 });
      next.push(grain);
    }
    this.pollen = next;
    this.paintSubstrate(asteroid);
  }

  private stain(theta: number, amount: number): void {
    if (amount <= 0) return;
    const n = SUBSTRATE_BINS;
    const u = ((theta / (Math.PI * 2)) % 1 + 1) % 1;
    const mid = u * n;
    const i0 = Math.floor(mid);
    for (let k = -2; k <= 2; k++) {
      const i = ((i0 + k) % n + n) % n;
      const dist = Math.abs(mid - i0 - k);
      const w = k === 0 ? 1 : Math.max(0, 1 - dist * 0.55);
      this.substrate[i] = Math.min(1, this.substrate[i]! + amount * w);
    }
  }

  private stainArc(center: number, span: number, amount: number): void {
    const steps = Math.max(3, Math.ceil(span * SUBSTRATE_BINS));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps - 0.5;
      this.stain(center + t * span * 2, amount * (1 - Math.abs(t) * 0.65));
    }
  }

  private paintSubstrate(asteroid: Asteroid): void {
    const g = this.film;
    g.clear();
    const r = asteroid.radius;
    const n = SUBSTRATE_BINS;
    const runs: { start: number; len: number }[] = [];
    let i = 0;
    while (i < n) {
      if (this.substrate[i]! < 0.04) {
        i += 1;
        continue;
      }
      const start = i;
      while (i < n && this.substrate[i]! >= 0.04) i += 1;
      runs.push({ start, len: i - start });
    }
    if (
      runs.length >= 2 &&
      runs[0]!.start === 0 &&
      runs[runs.length - 1]!.start + runs[runs.length - 1]!.len === n
    ) {
      const last = runs.pop()!;
      runs[0] = { start: last.start, len: last.len + runs[0]!.len };
    }

    for (const run of runs) {
      const outer: Pt[] = [];
      const inner: Pt[] = [];
      const aura: Pt[] = [];
      for (let k = 0; k <= run.len; k++) {
        const idx = (run.start + k) % n;
        const c = this.substrate[idx]!;
        const jitter = this.filmJitter[idx]!;
        const theta = (idx / n) * Math.PI * 2;
        const depth = r * (0.028 + 0.07 * c) * (0.78 + jitter * 0.4);
        outer.push(crustPoint(asteroid, theta, r * 0.004));
        inner.push(crustPoint(asteroid, theta, depth));
        aura.push(crustPoint(asteroid, theta, -0.6));
      }
      const soil = outer.concat(inner.reverse());
      if (soil.length < 6) continue;
      const mid = this.substrate[run.start]!;
      const tone = this.filmJitter[run.start]!;
      g.poly(soil);
      g.fill({
        color: mixHex(this.pal.film, this.pal.rock, 0.18),
        alpha: 0.42 + mid * 0.28,
      });
      g.poly(soil);
      g.fill({
        color: mixHex(this.pal.film, tone > 0.5 ? this.pal.leaf : this.pal.flower, 0.28),
        alpha: 0.2 + mid * 0.18,
      });
      if (aura.length >= 2) {
        g.moveTo(aura[0]!.x, aura[0]!.y);
        for (let a = 1; a < aura.length; a++) g.lineTo(aura[a]!.x, aura[a]!.y);
        g.stroke({
          width: 1.6,
          color: mixHex(this.pal.film, this.pal.flower, 0.35),
          alpha: 0.22 + mid * 0.18,
        });
      }
    }

    // Speckles in the soil — grit, not bowls. Stay inside the crust.
    for (let i = 0; i < n; i++) {
      const c = this.substrate[i]!;
      if (c < 0.12) continue;
      const jitter = this.filmJitter[i]!;
      if (jitter < 0.38) continue;
      const theta = ((i + 0.5) / n) * Math.PI * 2;
      const p = crustPoint(asteroid, theta, r * (0.018 + jitter * 0.04));
      g.circle(p.x, p.y, 0.7 + jitter * 1.4);
      g.fill({
        color: mixHex(this.pal.film, this.pal.grass, jitter),
        alpha: 0.14 * c,
      });
    }
  }

  private redrawHalo(asteroid: Asteroid, selected: boolean): void {
    const g = this.halo;
    g.clear();
    const r = asteroid.radius;
    const owned = asteroid.owner === 'player' || asteroid.owner === 'enemy';
    g.circle(0, 0, r * 1.38);
    g.fill({
      color: this.pal.core,
      alpha: owned ? 0.08 : selected ? 0.05 : 0.025,
    });
    g.circle(0, 0, r * 1.16);
    g.fill({ color: this.pal.rockLit, alpha: 0.1 });
  }

  private redrawCore(
    asteroid: Asteroid,
    selected: boolean,
    trees: Tree[] = this.localTrees,
  ): void {
    const g = this.core;
    g.clear();
    const hue = factionCoreHue(asteroid.owner, 48);
    const owned = asteroid.owner === 'player';
    const enemy = asteroid.owner === 'enemy';
    const grey = asteroid.owner === 'grey';
    const feed = maxFeed(trees);
    const glow = owned
      ? this.pal.core
      : enemy
        ? hslToHex(hue, 0.48, 0.58)
        : grey
          ? this.pal.rockShadow
          : this.pal.rockLit;
    const hot = owned
      ? this.pal.coreHot
      : enemy
        ? hslToHex(hue, 0.5, 0.42)
        : this.pal.rockShadow;
    g.circle(0, 0, asteroid.radius * (0.58 + feed * 0.08));
    g.fill({ color: glow, alpha: (selected ? 0.1 : 0.05) + feed * 0.12 });
    g.circle(0, 0, asteroid.radius * (0.42 + feed * 0.04));
    g.fill({ color: glow, alpha: (selected ? 0.16 : 0.08) + feed * 0.08 });
    g.circle(0, 0, asteroid.radius * 0.28);
    g.fill({ color: hot, alpha: (selected ? 0.28 : 0.16) + feed * 0.1 });
    g.circle(0, 0, asteroid.radius * 0.14);
    g.fill({ color: glow, alpha: (selected ? 0.82 : 0.62) + feed * 0.12 });
    g.circle(0, 0, asteroid.radius * 0.05);
    g.fill({ color: this.pal.coreWhite, alpha: 0.95 });

    this.selectionRing.clear();
    if (asteroid.maxShield > 0 && asteroid.shield > 0) {
      const t = asteroid.shield / asteroid.maxShield;
      this.selectionRing.circle(0, 0, asteroid.radius + 6);
      this.selectionRing.stroke({
        width: 2.2,
        color: this.pal.core,
        alpha: 0.18 + t * 0.4,
      });
    }
    if (selected) {
      this.selectionRing.circle(0, 0, asteroid.radius + 10);
      this.selectionRing.stroke({
        width: 1.4,
        color: this.pal.ring,
        alpha: 0.32,
      });
    }
  }

  private redrawSlots(
    asteroid: Asteroid,
    plantableSlots: Set<number>,
    selected: boolean,
  ): void {
    const g = this.slotsGfx;
    g.clear();
    for (let i = 0; i < asteroid.treeSlots; i++) {
      const pos = slotPosition(asteroid, i);
      const lx = pos.x - asteroid.x;
      const ly = pos.y - asteroid.y;
      const plantable = plantableSlots.has(i);
      g.circle(lx, ly, plantable ? 6.5 : 3.2);
      g.fill({
        color: plantable ? this.pal.flower : this.pal.tuft,
        alpha: plantable ? 0.22 : selected ? 0.1 : 0.05,
      });
      g.circle(lx, ly, plantable ? 2.4 : 1.2);
      g.fill({
        color: plantable ? this.pal.flower : this.pal.leaf,
        alpha: plantable ? 0.8 : selected ? 0.35 : 0.16,
      });
    }
  }
}

const EMPTY_PLANTABLE = new Set<number>();

export function plantableEmptySlots(
  world: World,
  asteroidId: number,
  localOrbitCount: number,
  kind: TreeKind = 'dyson',
  faction: FactionId = 'player',
): Set<number> {
  if (localOrbitCount < 10) return EMPTY_PLANTABLE;
  const asteroid = world.asteroids.get(asteroidId);
  if (!asteroid) return EMPTY_PLANTABLE;
  if (!canPlantKind(asteroid.stats.energy, kind)) return EMPTY_PLANTABLE;
  if (hasHostileOrbiters(world, asteroidId, faction)) return EMPTY_PLANTABLE;
  if (hasHostileTrees(world, asteroidId, faction)) return EMPTY_PLANTABLE;
  const occupied = getOccupiedSlots(world, asteroidId);
  const empty = new Set<number>();
  for (let i = 0; i < asteroid.treeSlots; i++) {
    if (!occupied.has(i)) empty.add(i);
  }
  return empty.size === 0 ? EMPTY_PLANTABLE : empty;
}

function paintRock(g: Graphics, asteroid: Asteroid, pal: FloraPalette): void {
  g.clear();
  const rng = mulberry32(asteroid.seed);
  const r = asteroid.radius;
  const owned = asteroid.owner === 'player' || asteroid.owner === 'enemy';
  const wild = asteroid.owner === 'grey';
  const outline = rockOutline(asteroid, 64);

  g.poly(outline);
  g.fill({ color: pal.rock, alpha: 0.92 });

  const stains = 16 + Math.floor(rng() * 8);
  for (let i = 0; i < stains; i++) {
    const a = rng() * Math.PI * 2;
    const rim = rockRadiusAt(asteroid, a);
    const d = rng() * rim * 0.7;
    const sr = range(rng, r * 0.06, r * 0.28);
    if (d + sr > rim * 0.9) continue;
    const pick = rng();
    const color = pick > 0.7 ? pal.stain : pick > 0.4 ? pal.rockLit : pal.rockShadow;
    g.circle(Math.cos(a) * d, Math.sin(a) * d, sr);
    g.fill({ color, alpha: 0.09 + rng() * 0.1 });
  }

  g.poly(outline.map((p) => ({ x: p.x * 0.64, y: p.y * 0.64 })));
  g.fill({ color: pal.rockShadow, alpha: 0.1 });
  const litA = rng() * Math.PI * 2;
  g.circle(Math.cos(litA) * r * 0.22, Math.sin(litA) * r * 0.26, r * 0.46);
  g.fill({ color: pal.rockLit, alpha: 0.16 });
  g.circle(
    Math.cos(litA + Math.PI) * r * 0.2,
    Math.sin(litA + Math.PI) * r * 0.24,
    r * 0.36,
  );
  g.fill({ color: pal.rockShadow, alpha: 0.08 });

  if (owned || wild) {
    g.poly(outline.map((p) => ({ x: p.x * 0.52, y: p.y * 0.52 })));
    g.fill({ color: pal.stain, alpha: owned ? 0.1 : 0.05 });
    paintLichen(g, asteroid, pal, rng);
  }

  g.poly(outline);
  g.stroke({ width: 3.4, color: pal.outline, alpha: 0.1 });
  g.poly(outline.map((p) => ({ x: p.x * 0.985, y: p.y * 0.985 })));
  g.stroke({ width: 1.15, color: pal.rockShadow, alpha: 0.22 });
}

/** Soft pigment on the disc — no blades sticking into space. */
function paintLichen(
  g: Graphics,
  asteroid: Asteroid,
  pal: FloraPalette,
  rng: () => number,
): void {
  const owned = asteroid.owner === 'player' || asteroid.owner === 'enemy';
  const r = asteroid.radius;
  const life = owned ? pal.leaf : pal.stain;
  const mul = owned ? 1 : 0.55;

  const islands = owned ? 4 + Math.floor(rng() * 3) : 2;
  for (let i = 0; i < islands; i++) {
    const a = rng() * Math.PI * 2;
    const rim = rockRadiusAt(asteroid, a);
    const d = rim * range(rng, 0.38, 0.74);
    const cx = Math.cos(a) * d;
    const cy = Math.sin(a) * d;
    const n = 3 + Math.floor(rng() * 3);
    for (let k = 0; k < n; k++) {
      const ox = cx + range(rng, -r * 0.12, r * 0.12);
      const oy = cy + range(rng, -r * 0.12, r * 0.12);
      const sr = range(rng, r * 0.06, r * 0.18);
      const dist = Math.hypot(ox, oy);
      const localRim = rockRadiusAt(asteroid, Math.atan2(oy, ox));
      if (dist + sr > localRim * 0.92) continue;
      const color = rng() > 0.45 ? life : pal.grass;
      g.circle(ox, oy, sr);
      g.fill({ color, alpha: (0.08 + rng() * 0.07) * mul });
    }
  }
}

type Pt = { x: number; y: number };

type GrassBit = {
  theta: number;
  x: number;
  y: number;
  lean: number;
  length: number;
  width: number;
  radius: number;
  jitter: number;
  kind: 'moss' | 'blade' | 'tuft';
  /** Tip droop as a fraction of length (AMD / Jahrmann bezier lean). */
  droop: number;
  /** 0..1 mix toward leaf / tuft color. */
  shade: number;
  slot?: number;
};

type PollenGrain = {
  fromTheta: number;
  toTheta: number;
  hover: number;
  age: number;
  life: number;
  size: number;
  wobble: number;
};

function spawnPollen(
  asteroid: Asteroid,
  tree: Tree,
  rng: () => number,
): PollenGrain {
  const polar = slotPolar(asteroid, tree.slotIndex);
  const reach = lifeReach(tree.maturity);
  const dir = rng() > 0.5 ? 1 : -1;
  const fromTheta = polar.angle + range(rng, -0.1, 0.1);
  const span = range(rng, 0.14, Math.max(0.2, reach * 0.62 + 0.18));
  return {
    fromTheta,
    toTheta: fromTheta + dir * span,
    hover: range(rng, 2.2, 4.8) * Math.min(1.2, asteroid.radius / 90),
    age: 0,
    life: range(rng, 2.4, 5.2),
    size: range(rng, 0.85, 1.55),
    wobble: rng() * Math.PI * 2,
  };
}

function maturityBucket(maturity: number): number {
  return Math.floor(Math.min(1, Math.max(0, maturity)) * 80);
}

function maxFeed(trees: Tree[]): number {
  let best = 0;
  for (const tree of trees) {
    best = Math.max(best, rootFeedActive(tree.maturity, tree.coreFeed));
  }
  return best;
}

function feedKeyFor(trees: Tree[]): string {
  let key = `${trees.length}`;
  for (const tree of trees) {
    key += `|${tree.id}:${Math.round(rootFeedActive(tree.maturity, tree.coreFeed) * 20)}`;
  }
  return key;
}

function crustPoint(
  asteroid: Asteroid,
  theta: number,
  inset = 0,
): { x: number; y: number; rim: number } {
  const rim = rockRadiusAt(asteroid, theta);
  const d = Math.max(0, rim - inset);
  return { x: Math.cos(theta) * d, y: Math.sin(theta) * d, rim };
}

function pushClump(
  bits: GrassBit[],
  asteroid: Asteroid,
  rng: () => number,
  theta: number,
  count: number,
  density: 'grove' | 'meadow',
  slot?: number,
): void {
  const r = asteroid.radius;
  const inset = range(rng, r * 0.002, r * 0.016);
  const origin = crustPoint(asteroid, theta, inset);
  const tx = -Math.sin(theta);
  const ty = Math.cos(theta);
  const grove = density === 'grove';
  // Shared clump pose — blades mostly agree, then fan a little (Tsushima-style).
  const clumpLean = theta + range(rng, -0.2, 0.2);
  const clumpHeight = grove ? range(rng, 7.5, 14.5) : range(rng, 4.2, 8.6);
  const clumpDroop = range(rng, 0.28, 0.52);
  const clumpShade = rng();
  const sameDir = grove ? range(rng, 0.38, 0.62) : range(rng, 0.62, 0.86);
  const fanAmp = grove ? range(rng, 0.28, 0.55) : range(rng, 0.1, 0.24);
  const spread = grove ? range(rng, 2.2, 4.4) : range(rng, 1.4, 2.8);

  const mossN = grove ? 2 + Math.floor(rng() * 3) : rng() > 0.55 ? 1 : 0;
  for (let m = 0; m < mossN; m++) {
    const along = range(rng, -spread * 0.7, spread * 0.7);
    bits.push({
      theta,
      x: origin.x + tx * along,
      y: origin.y + ty * along,
      lean: theta + range(rng, -0.4, 0.4),
      length: 0,
      width: 0,
      radius: range(rng, r * 0.012, r * 0.03),
      jitter: rng(),
      kind: 'moss',
      droop: 0,
      shade: clumpShade * 0.5 + rng() * 0.5,
      slot,
    });
  }

  for (let i = 0; i < count; i++) {
    const along = range(rng, -spread, spread);
    const x = origin.x + tx * along;
    const y = origin.y + ty * along;
    const tuft = rng() > (grove ? 0.42 : 0.62);
    const fan = (along / Math.max(spread, 0.001)) * fanAmp;
    const outward = theta + fan;
    let lean =
      clumpLean * sameDir + outward * (1 - sameDir) + range(rng, -0.07, 0.07);
    const tall = Math.pow(rng(), grove ? 0.55 : 0.95);
    let length = clumpHeight * (0.42 + tall * 0.7);
    let droop = clumpDroop * range(rng, 0.7, 1.35);
    // A few weeds arch over instead of standing.
    if (rng() < 0.12) {
      lean = theta + (rng() > 0.5 ? 1 : -1) * range(rng, 0.7, 1.25);
      droop = range(rng, 0.7, 1.15);
      length *= 0.78;
    }
    bits.push({
      theta,
      x,
      y,
      lean,
      length,
      width: tuft
        ? range(rng, 0.55, 1.15)
        : range(rng, 0.22, 0.58),
      radius: 0,
      jitter: rng(),
      kind: tuft ? 'tuft' : 'blade',
      droop,
      shade: clumpShade * 0.62 + rng() * 0.38,
      slot,
    });
  }
}

function slotNear(asteroid: Asteroid, theta: number): number | undefined {
  let best = -1;
  let bestDa = 0.32;
  for (let slot = 0; slot < asteroid.treeSlots; slot++) {
    const polar = slotPolar(asteroid, slot);
    const da = Math.abs(shortestAngle(theta, polar.angle));
    if (da < bestDa) {
      bestDa = da;
      best = slot;
    }
  }
  return best >= 0 ? best : undefined;
}

function buildGrassField(asteroid: Asteroid): GrassBit[] {
  const rng = mulberry32((asteroid.seed ^ 0x6a55c0de) >>> 0);
  const bits: GrassBit[] = [];

  // Continuous jittered sward around the whole rim.
  let theta = rng() * Math.PI * 2;
  const turns = Math.PI * 2;
  let walked = 0;
  while (walked < turns) {
    const step = range(rng, 0.024, 0.044);
    const blades = 5 + Math.floor(rng() * 5);
    pushClump(
      bits,
      asteroid,
      rng,
      theta,
      blades,
      'meadow',
      slotNear(asteroid, theta),
    );
    theta += step;
    walked += step;
  }

  // Extra stand at each planting scar — origin of life.
  for (let slot = 0; slot < asteroid.treeSlots; slot++) {
    const polar = slotPolar(asteroid, slot);
    const clumps = 8 + Math.floor(rng() * 5);
    for (let c = 0; c < clumps; c++) {
      const base = polar.angle + range(rng, -0.4, 0.4);
      const blades = 8 + Math.floor(rng() * 7);
      pushClump(bits, asteroid, rng, base, blades, 'grove', slot);
    }
  }

  bits.sort((a, b) => a.length - b.length);
  return bits;
}

function sampleSubstrate(substrate: Float32Array | undefined, theta: number): number {
  if (!substrate || substrate.length === 0) return 1;
  const n = substrate.length;
  const u = ((theta / (Math.PI * 2)) % 1 + 1) % 1;
  const x = u * n;
  const i0 = Math.floor(x) % n;
  const i1 = (i0 + 1) % n;
  const t = x - Math.floor(x);
  return substrate[i0]! * (1 - t) + substrate[i1]! * t;
}

function paintLife(
  g: Graphics,
  sap: Graphics,
  asteroid: Asteroid,
  pal: FloraPalette,
  bits: GrassBit[],
  trees: Tree[],
  time = 0,
  substrate?: Float32Array,
): void {
  g.clear();
  sap.clear();
  if (trees.length === 0) return;

  const origins = trees.map((tree) => {
    const polar = slotPolar(asteroid, tree.slotIndex);
    return {
      tree,
      angle: polar.angle,
      feed: rootFeedActive(tree.maturity, tree.coreFeed),
      seed: tree.seed,
    };
  });

  // Thin crust mark under the grove — not a face stain.
  for (const o of origins) {
    const t = groveSpread(o.tree.maturity, 0.08);
    if (t <= 0.02) continue;
    const span = 0.1 + 0.12 * o.tree.maturity;
    const steps = 5;
    const grassU = sapRiseU(time, o.seed);
    const grassStage = sapStage(
      grassU,
      SAP_WINDOW.grass[0],
      SAP_WINDOW.grass[1],
      0.2,
    );
    for (let i = 0; i <= steps; i++) {
      const u = i / steps - 0.5;
      const theta = o.angle + u * span * 2;
      const p = crustPoint(asteroid, theta, asteroid.radius * 0.012);
      const sr = asteroid.radius * (0.016 + (1 - Math.abs(u) * 1.6) * 0.014) * t;
      if (sr <= 0.35) continue;
      g.circle(p.x, p.y, sr);
      g.fill({ color: pal.grass, alpha: 0.14 * t * (1 - Math.abs(u)) });
      if (grassStage.glow > 0.05 && o.feed > 0.04) {
        const k = grassStage.glow * o.feed * t * (1 - Math.abs(u)) * 0.8;
        sap.circle(p.x, p.y, sr * (2.4 + grassStage.progress * 0.8));
        sap.fill({ color: pal.core, alpha: 0.12 * k });
      }
    }
  }

  for (const bit of bits) {
    let grow = 0;
    let prox = 0;
    let feed = 0;
    let nearestDa = Math.PI;
    let sapSeed = origins[0]?.seed ?? 0;
    for (const o of origins) {
      const da = Math.abs(shortestAngle(bit.theta, o.angle));
      if (da <= nearestDa) {
        nearestDa = da;
        sapSeed = o.seed;
      }
      grow = Math.max(grow, lifeSpread(o.tree.maturity, da, bit.jitter));
      prox = Math.max(prox, lifeProximity(da));
      feed = Math.max(feed, o.feed * lifeProximity(da));
      if (bit.slot === o.tree.slotIndex && da < 0.38) {
        const scar = groveSpread(o.tree.maturity, bit.jitter);
        grow = Math.max(grow, scar * (1 - da / 0.42));
        feed = Math.max(feed, o.feed * (0.55 + 0.45 * lifeProximity(da)));
        sapSeed = o.seed;
      }
    }
    const film = sampleSubstrate(substrate, bit.theta);
    if (film < 0.08) continue;
    grow = Math.max(grow, film * 0.82);
    if (grow <= 0.03) continue;
    const density = lifeDensity(prox, grow);
    if (bit.jitter > density * 1.35) continue;
    const lush = lifeLushScale(prox);
    if (bit.kind === 'moss') {
      const rad =
        bit.radius * (0.35 + 0.55 * grow) * (0.7 + 0.4 * prox);
      g.circle(bit.x, bit.y, rad);
      g.fill({
        color: mixHex(pal.grass, pal.leaf, bit.shade * 0.35),
        alpha: (0.12 + bit.jitter * 0.1) * grow,
      });
      g.circle(
        bit.x + Math.cos(bit.lean) * rad * 0.28,
        bit.y + Math.sin(bit.lean) * rad * 0.28,
        rad * 0.55,
      );
      g.fill({
        color: pal.leaf,
        alpha: (0.06 + bit.jitter * 0.05) * grow,
      });
      if (feed > 0.04) {
        const start =
          SAP_WINDOW.grass[0] + Math.min(0.16, nearestDa * 0.4);
        const moss = sapStage(sapRiseU(time, sapSeed), start, start + 0.32, 0.2);
        if (moss.glow > 0.04) {
          const k = moss.glow * feed * grow * 0.8;
          sap.circle(bit.x, bit.y, rad * (2.2 + moss.progress * 1.1));
          sap.fill({ color: pal.core, alpha: 0.14 * k });
          sap.circle(bit.x, bit.y, rad * (1.1 + moss.progress * 0.4));
          sap.fill({ color: pal.coreHot, alpha: 0.12 * k });
        }
      }
      continue;
    }
    drawGrassBlade(g, sap, bit, grow, lush, pal, feed, time, nearestDa, sapSeed);
  }
}

function lerpPt(a: Pt, b: Pt, t: number): Pt {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

function quadBezier(p0: Pt, p1: Pt, p2: Pt, t: number): Pt {
  return lerpPt(lerpPt(p0, p1, t), lerpPt(p1, p2, t), t);
}

function quadBezierDeriv(p0: Pt, p1: Pt, p2: Pt, t: number): Pt {
  return {
    x: 2 * (1 - t) * (p1.x - p0.x) + 2 * t * (p2.x - p1.x),
    y: 2 * (1 - t) * (p1.y - p0.y) + 2 * t * (p2.y - p1.y),
  };
}

/** Tapered ribbon along a quadratic spine — widest near the stem, needle at the tip. */
function bladePoly(
  p0: Pt,
  p1: Pt,
  p2: Pt,
  width: number,
  t0 = 0,
  t1 = 1,
  steps = 5,
): Pt[] {
  const left: Pt[] = [];
  const right: Pt[] = [];
  for (let i = 0; i <= steps; i++) {
    const u = i / steps;
    const t = t0 + (t1 - t0) * u;
    const p = quadBezier(p0, p1, p2, t);
    const d = quadBezierDeriv(p0, p1, p2, t);
    const l = Math.hypot(d.x, d.y) || 1;
    const nx = -d.y / l;
    const ny = d.x / l;
    const envelope =
      t < 0.14 ? 0.5 + 0.5 * (t / 0.14) : Math.pow(1 - (t - 0.14) / 0.86, 1.08);
    const w = width * 0.5 * envelope;
    left.push({ x: p.x + nx * w, y: p.y + ny * w });
    right.push({ x: p.x - nx * w, y: p.y - ny * w });
  }
  for (let i = right.length - 1; i >= 0; i--) left.push(right[i]!);
  return left;
}

function drawGrassBlade(
  g: Graphics,
  sap: Graphics,
  bit: GrassBit,
  t: number,
  lush: number,
  pal: FloraPalette,
  feed: number,
  time: number,
  angleDelta: number,
  sapSeed: number,
): void {
  const len = bit.length * (0.18 + 0.82 * t) * lush;
  if (len < 0.7) return;
  const width = bit.width * (0.35 + 0.65 * t) * (0.55 + 0.5 * lush);
  const tuft = bit.kind === 'tuft';
  const nx = Math.cos(bit.theta);
  const ny = Math.sin(bit.theta);
  const lx = Math.cos(bit.lean);
  const ly = Math.sin(bit.lean);
  const breeze =
    feed > 0.04
      ? Math.sin(time * 1.55 + bit.jitter * 6.2) * len * 0.06 * feed
      : 0;
  const p0: Pt = { x: bit.x, y: bit.y };
  let p1: Pt = {
    x: bit.x + nx * len * 0.58,
    y: bit.y + ny * len * 0.58,
  };
  let p2: Pt = {
    x: bit.x + nx * len * 0.82 + lx * len * bit.droop * 0.55 - ny * breeze,
    y: bit.y + ny * len * 0.82 + ly * len * bit.droop * 0.55 + nx * breeze,
  };
  const chord = Math.hypot(p2.x - p0.x, p2.y - p0.y) || 1;
  const keep = len / chord;
  p1 = {
    x: p0.x + (p1.x - p0.x) * keep,
    y: p0.y + (p1.y - p0.y) * keep,
  };
  p2 = {
    x: p0.x + (p2.x - p0.x) * keep,
    y: p0.y + (p2.y - p0.y) * keep,
  };

  const base = mixHex(pal.tuft, pal.grass, 0.28 + bit.shade * 0.4);
  const tip = mixHex(
    pal.grass,
    pal.leaf,
    tuft ? 0.45 + bit.shade * 0.5 : 0.22 + bit.shade * 0.45,
  );
  const alpha =
    (tuft ? 0.72 : 0.52) * (0.4 + 0.6 * t) * (0.78 + bit.jitter * 0.22);

  g.poly(bladePoly(p0, p1, p2, width));
  g.fill({ color: base, alpha });
  g.poly(bladePoly(p0, p1, p2, width * 0.72, 0.32, 1, 4));
  g.fill({ color: tip, alpha: alpha * 0.78 });

  if (feed <= 0.03 || lush < 0.28) return;
  const start = SAP_WINDOW.grass[0] + Math.min(0.2, angleDelta * 0.42);
  const end = Math.min(0.98, start + 0.36);
  const stage = sapStage(sapRiseU(time, sapSeed), start, end, 0.22);
  if (stage.glow <= 0.03) return;

  const headT = Math.max(0.08, stage.progress);
  const k = stage.glow * feed * (0.55 + 0.45 * lush) * 0.56;
  sap.poly(bladePoly(p0, p1, p2, width * 3.8, 0, headT, 4));
  sap.fill({ color: pal.core, alpha: 0.14 * k });
  sap.poly(bladePoly(p0, p1, p2, width * 1.8, 0, headT, 4));
  sap.fill({ color: pal.coreHot, alpha: 0.16 * k });
  const head = quadBezier(p0, p1, p2, headT);
  sap.circle(head.x, head.y, Math.max(1.8, width * (1.8 + stage.progress * 0.8)));
  sap.fill({ color: pal.core, alpha: 0.18 * k });
  sap.circle(head.x, head.y, Math.max(0.8, width * 0.7));
  sap.fill({ color: pal.coreHot, alpha: 0.16 * k });
}
