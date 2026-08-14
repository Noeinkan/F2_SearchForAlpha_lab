import './style.css';
import { Application } from 'pixi.js';
import { GameAudio } from './game/audio/audio';
import { bindCameraControls } from './game/input/cameraControls';
import {
  bindGameplay,
  createGameplayState,
} from './game/input/gameplay';
import {
  AsteroidView,
  plantableEmptySlots,
} from './game/render/asteroidView';
import { Camera } from './game/render/camera';
import { GraphView } from './game/render/graphView';
import {
  applySceneToDocument,
  createScenePalette,
} from './game/render/palette';
import { SeedlingLayer } from './game/render/seedlingView';
import { SendPreview } from './game/render/sendPreview';
import {
  createStarfield,
  updateStarfieldParallax,
} from './game/render/starfield';
import { TreeView } from './game/render/treeView';
import { countFactionOrbiting } from './game/sim/commands';
import { createCoreLoopWorld } from './game/sim/layout';
import { PLANT_COST } from './game/sim/types';
import { tick } from './game/sim/world';

const SIM_DT = 1 / 60;

async function boot(): Promise<void> {
  const host = document.querySelector<HTMLDivElement>('#app');
  if (!host) throw new Error('#app missing');

  const hud = document.createElement('div');
  hud.className = 'hud';
  hud.innerHTML =
    '<div><strong>Asterbloom</strong></div><div id="hud-stats">…</div><div class="hint">drag to send · wheel for count · click a glowing slot (10) to plant</div>';
  host.appendChild(hud);
  const hudStats = hud.querySelector('#hud-stats')!;

  const world = createCoreLoopWorld();
  const scene = createScenePalette(world.seed);
  applySceneToDocument(scene);
  const home = [...world.asteroids.values()].find((a) => a.owner === 'player')!;

  const app = new Application();
  await app.init({
    resizeTo: window,
    antialias: true,
    backgroundColor: scene.bg,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
    preference: 'webgl',
  });
  host.appendChild(app.canvas);

  const audio = new GameAudio();
  let ambientStarted = false;
  app.canvas.addEventListener(
    'pointerdown',
    () => {
      if (ambientStarted) return;
      ambientStarted = true;
      audio.startAmbient();
    },
    { once: true },
  );

  const camera = new Camera();
  app.stage.addChild(camera.world);

  const starfield = createStarfield(world.seed, scene);
  camera.world.addChild(starfield);

  const graphView = new GraphView(scene);
  camera.world.addChild(graphView.root);

  const asteroidViews = new Map<number, AsteroidView>();
  for (const a of world.asteroids.values()) {
    const view = new AsteroidView(a, scene);
    asteroidViews.set(a.id, view);
    camera.world.addChild(view.root);
  }

  camera.world.sortableChildren = true;
  starfield.zIndex = 0;
  graphView.root.zIndex = 1;
  for (const view of asteroidViews.values()) view.root.zIndex = 3;
  const seedlings = new SeedlingLayer(scene);
  seedlings.root.zIndex = 5;
  camera.world.addChild(seedlings.root);

  const preview = new SendPreview(scene);
  preview.root.zIndex = 6;
  camera.world.addChild(preview.root);

  const treeViews = new Map<number, TreeView>();
  const syncTrees = () => {
    for (const tree of world.trees.values()) {
      if (treeViews.has(tree.id)) continue;
      const asteroid = world.asteroids.get(tree.asteroidId);
      if (!asteroid) continue;
      const view = new TreeView(tree, asteroid, scene);
      view.roots.zIndex = 2;
      view.canopy.zIndex = 4;
      treeViews.set(tree.id, view);
      camera.world.addChild(view.roots, view.canopy);
    }
  };
  syncTrees();

  const gameplay = createGameplayState(home.id);
  camera.zoom = 0.85;
  camera.centerOn(0, 0, app.screen.width, app.screen.height);
  bindCameraControls(app.canvas, camera);
  bindGameplay({
    canvas: app.canvas,
    camera,
    world,
    state: gameplay,
    preview,
    audio,
    onPlanted: syncTrees,
  });

  let acc = 0;
  app.ticker.add((ticker) => {
    const frameDt = Math.min(0.05, ticker.deltaMS / 1000);
    acc += frameDt;
    while (acc >= SIM_DT) {
      tick(world, SIM_DT);
      acc -= SIM_DT;
    }
    syncTrees();

    graphView.sync(world, gameplay.selectedAsteroidId);

    for (const a of world.asteroids.values()) {
      const view = asteroidViews.get(a.id);
      if (!view) continue;
      const local = countFactionOrbiting(world, a.id, 'player');
      const plantable = plantableEmptySlots(world, a.id, local);
      view.update(a, a.id === gameplay.selectedAsteroidId, plantable);
    }

    for (const [id, view] of treeViews) {
      const tree = world.trees.get(id);
      if (!tree) continue;
      const asteroid = world.asteroids.get(tree.asteroidId);
      if (!asteroid) continue;
      view.update(tree, asteroid);
    }

    seedlings.sync(world.seedlings);
    updateStarfieldParallax(starfield, camera.x, camera.y);

    const selId = gameplay.selectedAsteroidId;
    const sel = selId !== null ? world.asteroids.get(selId) : undefined;
    const local = sel ? countFactionOrbiting(world, sel.id, 'player') : 0;
    const trees = world.trees.size;
    const dragInfo = gameplay.dragging
      ? ` · sending ${gameplay.sendCount}`
      : local >= PLANT_COST
        ? ` · plant ready`
        : '';
    hudStats.textContent = sel
      ? `${sel.name} · ${sel.owner} · ${local} seedlings · Energy ${sel.stats.energy}  Strength ${sel.stats.strength}  Speed ${sel.stats.speed}${dragInfo}`
      : `trees ${trees}`;
  });
}

boot().catch((err) => {
  console.error(err);
  document.body.textContent = String(err);
});
