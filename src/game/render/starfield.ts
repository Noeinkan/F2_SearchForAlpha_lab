import { Container, FillGradient, Graphics } from 'pixi.js';
import { mulberry32 } from '../sim/rng';
import type { ScenePalette } from './palette';

export function createStarfield(seed: number, scene: ScenePalette): Container {
  const root = new Container();
  root.eventMode = 'none';

  const wash = new Graphics();
  const grad = new FillGradient({
    type: 'linear',
    start: { x: 0, y: 0 },
    end: { x: 1, y: 0 },
    colorStops: [
      { offset: 0, color: scene.bgA },
      { offset: 0.45, color: scene.bgB },
      { offset: 1, color: scene.bgC },
    ],
  });
  const size = 4800;
  wash.rect(-size, -size, size * 2, size * 2);
  wash.fill(grad);
  root.addChild(wash);

  const dust = drawDust(seed, scene);
  root.addChild(dust);

  (root as Container & { far: Graphics; near: Graphics }).far = dust;
  (root as Container & { far: Graphics; near: Graphics }).near = dust;
  return root;
}

function drawDust(seed: number, scene: ScenePalette): Graphics {
  const rng = mulberry32(seed);
  const g = new Graphics();
  const clouds = scene.dark ? 22 : 28;
  for (let i = 0; i < clouds; i++) {
    const x = (rng() - 0.5) * 3200;
    const y = (rng() - 0.5) * 3200;
    const r = 18 + rng() * 90;
    g.circle(x, y, r);
    g.fill({
      color: rng() > 0.5 ? scene.mist : scene.dust,
      alpha: scene.dark ? 0.04 + rng() * 0.06 : 0.07 + rng() * 0.08,
    });
  }
  if (scene.dark) {
    for (let i = 0; i < 90; i++) {
      const x = (rng() - 0.5) * 3600;
      const y = (rng() - 0.5) * 3600;
      g.circle(x, y, rng() > 0.85 ? 1.4 : 0.7);
      g.fill({
        color: rng() > 0.5 ? scene.mist : scene.dust,
        alpha: 0.18 + rng() * 0.45,
      });
    }
  }
  return g;
}

export function updateStarfieldParallax(
  starfield: Container,
  camX: number,
  camY: number,
): void {
  const layers = starfield as Container & { far?: Graphics; near?: Graphics };
  if (layers.far) {
    layers.far.position.set(-camX * 0.04, -camY * 0.04);
  }
}
