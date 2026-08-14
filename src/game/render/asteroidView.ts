import { Container, Graphics, Text } from 'pixi.js';
import { mulberry32, range } from '../sim/rng';
import type { Asteroid, World } from '../sim/types';
import { getOccupiedSlots, slotPosition } from '../sim/world';
import { PAL } from './palette';

const ROCKS = [PAL.rockA, PAL.rockB, PAL.rockC, 0xd8c8ce, 0xc0c4c8] as const;

export class AsteroidView {
  readonly root = new Container();
  readonly asteroidId: number;
  private core: Graphics;
  private slotsGfx: Graphics;
  private selectionRing: Graphics;
  private label: Text;
  private lastSelected = false;
  private lastPlantKey = '';

  constructor(asteroid: Asteroid) {
    this.asteroidId = asteroid.id;
    this.root.position.set(asteroid.x, asteroid.y);
    this.root.addChild(drawRock(asteroid));

    this.core = new Graphics();
    this.root.addChild(this.core);

    this.selectionRing = new Graphics();
    this.root.addChild(this.selectionRing);

    this.slotsGfx = new Graphics();
    this.root.addChild(this.slotsGfx);

    this.label = new Text({
      text: asteroid.name,
      style: {
        fontFamily: 'Georgia, "Times New Roman", serif',
        fontSize: 13,
        fontStyle: 'italic',
        fill: 0x5a4850,
        align: 'center',
      },
    });
    this.label.anchor.set(0.5, 0);
    this.label.position.set(0, asteroid.radius + 16);
    this.label.alpha = 0.7;
    this.root.addChild(this.label);

    this.redrawCore(asteroid, false);
    this.redrawSlots(asteroid, new Set(), false);
  }

  update(
    asteroid: Asteroid,
    selected: boolean,
    plantableSlots: Set<number>,
  ): void {
    this.root.position.set(asteroid.x, asteroid.y);
    const plantKey = [...plantableSlots].join(',');
    const selChanged = selected !== this.lastSelected;
    if (selChanged) {
      this.redrawCore(asteroid, selected);
      this.lastSelected = selected;
    }
    if (plantKey !== this.lastPlantKey || selChanged) {
      this.redrawSlots(asteroid, plantableSlots, selected);
      this.lastPlantKey = plantKey;
    }
    this.label.text = asteroid.name;
  }

  private redrawCore(asteroid: Asteroid, selected: boolean): void {
    const g = this.core;
    g.clear();
    const owned = asteroid.owner === 'player';
    const glow = owned ? PAL.core : 0xb8b0b8;
    const hot = owned ? PAL.coreHot : 0x9a9098;
    g.circle(0, 0, asteroid.radius * 0.34);
    g.fill({ color: hot, alpha: selected ? 0.22 : 0.12 });
    g.circle(0, 0, asteroid.radius * 0.16);
    g.fill({ color: glow, alpha: selected ? 0.7 : 0.5 });
    g.circle(0, 0, asteroid.radius * 0.055);
    g.fill({ color: 0xfff6d8, alpha: 0.95 });

    this.selectionRing.clear();
    if (selected) {
      this.selectionRing.circle(0, 0, asteroid.radius + 9);
      this.selectionRing.stroke({ width: 1.2, color: PAL.magenta, alpha: 0.35 });
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
      g.circle(lx, ly, plantable ? 6 : 3);
      g.stroke({
        width: plantable ? 1.4 : 0.9,
        color: plantable ? PAL.flower : PAL.magenta,
        alpha: plantable ? 0.85 : selected ? 0.35 : 0.18,
      });
    }
  }
}

export function plantableEmptySlots(
  world: World,
  asteroidId: number,
  localOrbitCount: number,
): Set<number> {
  const empty = new Set<number>();
  if (localOrbitCount < 10) return empty;
  const asteroid = world.asteroids.get(asteroidId);
  if (!asteroid) return empty;
  const occupied = getOccupiedSlots(world, asteroidId);
  for (let i = 0; i < asteroid.treeSlots; i++) {
    if (!occupied.has(i)) empty.add(i);
  }
  return empty;
}

function drawRock(asteroid: Asteroid): Graphics {
  const rng = mulberry32(asteroid.seed);
  const body = ROCKS[Math.floor(rng() * ROCKS.length)]!;
  const g = new Graphics();
  const r = asteroid.radius;

  g.circle(0, 0, r);
  g.fill({ color: body, alpha: 0.78 });

  for (let i = 0; i < 9; i++) {
    const a = rng() * Math.PI * 2;
    const d = rng() * r * 0.62;
    g.circle(Math.cos(a) * d, Math.sin(a) * d, range(rng, 6, 16));
    g.fill({ color: rng() > 0.5 ? 0xb8b0b8 : 0xd8d0d4, alpha: 0.18 });
  }

  g.circle(r * 0.18, r * 0.22, r * 0.72);
  g.fill({ color: 0x8a8088, alpha: 0.1 });
  g.circle(-r * 0.22, -r * 0.28, r * 0.4);
  g.fill({ color: 0xf4eef0, alpha: 0.14 });

  g.circle(0, 0, r);
  g.stroke({ width: 1.35, color: PAL.outline, alpha: 0.55 });
  return g;
}
