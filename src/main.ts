import './style.css';
import { Application } from 'pixi.js';
import { GameAudio } from './game/audio/audio';
import { createSessionHud } from './game/hud/sessionHud';
import { createTitleHud } from './game/hud/titleHud';
import { bindCameraControls } from './game/input/cameraControls';
import { travelCentroid } from './game/input/followSend';
import {
  bindGameplay,
  createGameplayState,
  type GameplayState,
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
  sceneAtTime,
  writeScene,
  type ScenePalette,
} from './game/render/palette';
import { SeedlingLayer } from './game/render/seedlingView';
import { SendPreview } from './game/render/sendPreview';
import { Starfield } from './game/render/starfield';
import { TreeView } from './game/render/treeView';
import { tickAi } from './game/sim/ai';
import {
  CAMPAIGN_MAPS,
  startCampaignMap,
  startSkirmishWorld,
  writeCampaignIndex,
} from './game/sim/campaign';
import {
  createMatchRuntime,
  DEFAULT_MATCH_CONFIG,
  matchStatus,
  tickMatchRuntime,
  type MatchConfig,
  type MatchRuntime,
  type MatchStatus,
} from './game/sim/match';
import type {
  Difficulty,
  FactionId,
  SeedlingState,
  Tree,
  World,
} from './game/sim/types';
import { countOrbitingKind, createEmptyWorld, tick } from './game/sim/world';

const SIM_DT = 1 / 60;
const DEFAULT_SESSION_SEED = 0xc0a1f00d;

function parseSeedFromHash(): number | null {
  const m = /^#s=([0-9a-fA-F]{1,8})$/.exec(location.hash);
  if (!m) return null;
  return Number.parseInt(m[1]!, 16) >>> 0;
}

function writeSeedHash(seed: number): void {
  const hex = (seed >>> 0).toString(16).padStart(8, '0');
  const next = `#s=${hex}`;
  if (location.hash !== next) {
    history.replaceState(null, '', `${location.pathname}${location.search}${next}`);
  }
}

function formatSeedHex(seed: number): string {
  return (seed >>> 0).toString(16).padStart(8, '0');
}

function freshSeed(): number {
  return (Math.random() * 0xffffffff) >>> 0;
}

interface CombatSnap {
  hp: Map<number, number>;
  state: Map<number, SeedlingState>;
  burn: Map<number, number>;
  trees: Set<number>;
}

function emptyCombatSnap(): CombatSnap {
  return {
    hp: new Map(),
    state: new Map(),
    burn: new Map(),
    trees: new Set(),
  };
}

function fillCombatSnap(world: World, snap: CombatSnap): CombatSnap {
  snap.hp.clear();
  snap.state.clear();
  snap.burn.clear();
  snap.trees.clear();
  for (const s of world.seedlings.values()) {
    snap.hp.set(s.id, s.hp);
    snap.state.set(s.id, s.state);
  }
  for (const a of world.asteroids.values()) {
    snap.burn.set(a.id, a.burnTimer);
  }
  for (const id of world.trees.keys()) snap.trees.add(id);
  return snap;
}

function playCombatSfx(
  audio: GameAudio,
  before: CombatSnap,
  world: World,
  into: CombatSnap,
): CombatSnap {
  let hpDrop = false;
  for (const s of world.seedlings.values()) {
    const prev = before.hp.get(s.id);
    if (prev !== undefined && s.hp < prev - 0.01) {
      hpDrop = true;
      break;
    }
  }
  if (hpDrop) audio.clash();

  for (const [id, st] of before.state) {
    if (world.seedlings.has(id)) continue;
    if (st !== 'plant') audio.death();
  }

  for (const a of world.asteroids.values()) {
    const prevBurn = before.burn.get(a.id) ?? 0;
    if (prevBurn <= 0 && a.burnTimer > 0) {
      audio.burn();
      break;
    }
  }
  for (const id of before.trees) {
    if (world.trees.has(id)) continue;
    let burning = false;
    for (const a of world.asteroids.values()) {
      if (a.burnTimer > 0) {
        burning = true;
        break;
      }
    }
    if (!burning) {
      for (const t of before.burn.values()) {
        if (t > 0) {
          burning = true;
          break;
        }
      }
    }
    if (burning) audio.burn();
    break;
  }

  return fillCombatSnap(world, into);
}

async function loadUiFonts(): Promise<void> {
  const load = Promise.all([
    document.fonts.load('700 16px Comfortaa'),
    document.fonts.load('500 13px Nunito'),
  ]);
  await Promise.race([
    load,
    new Promise<void>((resolve) => setTimeout(resolve, 2500)),
  ]);
}

async function boot(): Promise<void> {
  const host = document.querySelector<HTMLDivElement>('#app');
  if (!host) throw new Error('#app missing');
  await loadUiFonts();

  const audio = new GameAudio();

  let sessionSeed = parseSeedFromHash() ?? DEFAULT_SESSION_SEED;
  let world: World = createEmptyWorld(sessionSeed);
  let scene: ScenePalette = createScenePalette(world.seed);
  applySceneToDocument(scene);

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

  host.addEventListener(
    'pointerdown',
    () => {
      audio.startAmbient();
    },
    { once: true },
  );

  const camera = new Camera();
  const starfield = new Starfield(world.seed, scene);
  starfield.resize(app.screen.width, app.screen.height);
  app.stage.addChild(starfield.backdrop);
  app.stage.addChild(camera.world);
  camera.world.addChild(starfield.root);
  app.renderer.on('resize', (width: number, height: number) => {
    starfield.resize(width, height);
  });

  const graphView = new GraphView(scene);
  camera.world.addChild(graphView.root);

  let asteroidViews = new Map<number, AsteroidView>();
  let treeViews = new Map<number, TreeView>();
  let lastOwners = new Map<number, FactionId>();
  let seedlings: SeedlingLayer | null = null;
  const preview = new SendPreview(scene);
  preview.root.zIndex = 6;
  camera.world.addChild(preview.root);

  let gameplay: GameplayState = createGameplayState(0);
  let unbindGameplay: (() => void) | null = null;

  let paused = false;
  let status: MatchStatus = 'playing';
  let sessionMode: 'title' | 'playing' = 'title';
  let playMode: 'skirmish' | 'campaign' = 'skirmish';
  let matchConfig: MatchConfig = DEFAULT_MATCH_CONFIG;
  let matchRuntime: MatchRuntime = createMatchRuntime();
  let campaignIndex = 0;
  let campaignTitle = '';
  let skirmishDifficulty: Difficulty = 'normal';
  let firstRunBlocking = false;
  let followSendEnabled = false;
  let followingSend = false;
  let acc = 0;
  let palTime = 0;
  let palAcc = 0;
  const PAL_DT = 1 / 12;
  let combatSnap = fillCombatSnap(world, emptyCombatSnap());
  let combatSnapB = emptyCombatSnap();
  let lastHueKey = -1;

  const canAct = () =>
    sessionMode === 'playing' &&
    !paused &&
    !firstRunBlocking &&
    status === 'playing';

  let sessionHud!: ReturnType<typeof createSessionHud>;
  let titleHud!: ReturnType<typeof createTitleHud>;

  const syncMuteLabel = () => {
    sessionHud.setMuted(!audio.isEnabled());
  };

  const setMuted = (muted: boolean) => {
    audio.setEnabled(!muted);
    syncMuteLabel();
  };

  const setFollowSend = (enabled: boolean) => {
    followSendEnabled = enabled;
    if (!enabled) followingSend = false;
    sessionHud.setFollowSend(enabled);
  };

  const cancelFollow = () => {
    followingSend = false;
  };

  const syncTrees = () => {
    for (const [id, view] of treeViews) {
      if (world.trees.has(id)) continue;
      view.destroy();
      treeViews.delete(id);
    }
    for (const tree of world.trees.values()) {
      if (treeViews.has(tree.id)) continue;
      const asteroid = world.asteroids.get(tree.asteroidId);
      if (!asteroid) continue;
      const view = new TreeView(tree, asteroid, scene);
      view.root.zIndex = 4;
      treeViews.set(tree.id, view);
      camera.world.addChild(view.root);
    }
  };

  const clearWorldViews = () => {
    unbindGameplay?.();
    unbindGameplay = null;
    preview.hide();
    for (const view of asteroidViews.values()) {
      view.root.destroy({ children: true });
    }
    asteroidViews.clear();
    for (const view of treeViews.values()) view.destroy();
    treeViews.clear();
    if (seedlings) {
      camera.world.removeChild(seedlings.back, seedlings.front);
      seedlings.destroy();
      seedlings = null;
    }
  };

  const beginPlayingWorld = (
    nextWorld: World,
    seed: number,
    config: MatchConfig,
  ) => {
    clearWorldViews();
    world = nextWorld;
    sessionSeed = seed;
    matchConfig = config;
    matchRuntime = createMatchRuntime();
    writeSeedHash(sessionSeed);
    sessionHud.setSeed(formatSeedHex(sessionSeed));
    writeScene(scene, sceneAtTime(world.seed, 0));
    applySceneToDocument(scene);
    audio.beginMatch(scene.hue, scene.dark);
    app.renderer.background.color = scene.bg;
    starfield.retheme(scene);

    const home = [...world.asteroids.values()].find((a) => a.owner === 'player')!;
    asteroidViews = new Map();
    for (const a of world.asteroids.values()) {
      const view = new AsteroidView(a, scene);
      view.root.zIndex = 3;
      asteroidViews.set(a.id, view);
      camera.world.addChild(view.root);
    }

    seedlings = new SeedlingLayer(scene);
    seedlings.back.zIndex = 2.5;
    seedlings.front.zIndex = 5;
    camera.world.addChild(seedlings.back, seedlings.front);

    lastOwners = new Map();
    for (const a of world.asteroids.values()) lastOwners.set(a.id, a.owner);

    treeViews = new Map();
    syncTrees();

    gameplay = createGameplayState(home.id);
    sessionHud.setPlantKind(gameplay.plantKind);
    unbindGameplay = bindGameplay({
      canvas: app.canvas,
      camera,
      world,
      state: gameplay,
      preview,
      audio,
      onPlanted: syncTrees,
      onCommand: (result) => sessionHud.showCommandResult(result),
      onSend: () => {
        if (followSendEnabled) followingSend = true;
      },
      canAct,
    });

    camera.zoom = 0.85;
    camera.centerOn(home.x, home.y, app.screen.width, app.screen.height);
    followingSend = false;

    sessionMode = 'playing';
    paused = false;
    status = 'playing';
    acc = 0;
    palTime = 0;
    palAcc = 0;
    combatSnap = fillCombatSnap(world, combatSnap);
    lastHueKey = Math.round(scene.hue);
    sessionHud.setPaused(false);
    sessionHud.hideEnd();
    sessionHud.setVisible(true);
    titleHud.hide();
  };

  const startSkirmish = (difficulty: Difficulty, seed?: number) => {
    playMode = 'skirmish';
    skirmishDifficulty = difficulty;
    campaignTitle = '';
    const s = seed ?? freshSeed();
    const started = startSkirmishWorld(s, difficulty);
    beginPlayingWorld(started.world, s, started.config);
  };

  const startCampaign = (index: number) => {
    playMode = 'campaign';
    const started = startCampaignMap(index);
    campaignIndex = started.mapIndex;
    campaignTitle = started.title;
    writeCampaignIndex(campaignIndex);
    beginPlayingWorld(started.world, started.world.seed, started.config);
  };

  const restartCurrent = () => {
    if (playMode === 'campaign') startCampaign(campaignIndex);
    else startSkirmish(skirmishDifficulty, sessionSeed);
  };

  const showTitle = () => {
    clearWorldViews();
    sessionMode = 'title';
    status = 'playing';
    paused = false;
    followingSend = false;
    firstRunBlocking = false;
    sessionHud.hideEnd();
    sessionHud.setVisible(false);
    sessionHud.setPaused(false);
    sessionHud.dismissFirstRun();
    titleHud.show();
  };

  sessionHud = createSessionHud({
    host,
    onMuteToggle: () => setMuted(audio.isEnabled()),
    onFollowToggle: () => setFollowSend(!followSendEnabled),
    onRestart: () => restartCurrent(),
    onNewMap: () => startSkirmish(skirmishDifficulty, freshSeed()),
    onNextMap: () => {
      const next = campaignIndex + 1;
      if (next < CAMPAIGN_MAPS.length) startCampaign(next);
      else showTitle();
    },
    onTitle: () => showTitle(),
    onPlantKind: (kind) => {
      gameplay.plantKind = kind;
    },
    onFirstRunDismiss: () => {
      firstRunBlocking = false;
    },
  });

  titleHud = createTitleHud({
    host,
    onSkirmish: (difficulty) => {
      const hashSeed = parseSeedFromHash();
      startSkirmish(difficulty, hashSeed ?? freshSeed());
      if (sessionHud.maybeShowFirstRun()) firstRunBlocking = true;
    },
    onCampaign: (index) => {
      startCampaign(index);
      if (sessionHud.maybeShowFirstRun()) firstRunBlocking = true;
    },
  });

  camera.world.sortableChildren = true;
  starfield.root.zIndex = 0;
  graphView.root.zIndex = 1;
  bindCameraControls(app.canvas, camera, { onUserCamera: cancelFollow });

  syncMuteLabel();
  sessionHud.setFollowSend(followSendEnabled);
  showTitle();

  window.addEventListener('keydown', (e) => {
    if (e.code === 'KeyM' && !e.repeat) {
      setMuted(audio.isEnabled());
      return;
    }
    if (sessionMode !== 'playing') return;
    if (e.code === 'KeyF' && !e.repeat) {
      setFollowSend(!followSendEnabled);
      return;
    }
    if (firstRunBlocking) return;
    if (status !== 'playing') return;
    if (e.code === 'Escape' || e.code === 'Space') {
      e.preventDefault();
      if (e.repeat) return;
      paused = !paused;
      sessionHud.setPaused(paused);
      if (paused) preview.hide();
    }
  });

  // Keep plant-kind chips in sync when 1/2/3 keys change gameplay.plantKind.
  window.addEventListener('keydown', (e) => {
    if (!canAct()) return;
    if (e.key === '1' || e.key === '2' || e.key === '3') {
      sessionHud.setPlantKind(gameplay.plantKind);
    }
  });

  app.ticker.add((ticker) => {
    const frameDt = Math.min(0.05, ticker.deltaMS / 1000);
    palTime += frameDt;
    palAcc += frameDt;

    if (
      sessionMode === 'playing' &&
      !paused &&
      !firstRunBlocking &&
      status === 'playing'
    ) {
      acc += frameDt;
      while (acc >= SIM_DT) {
        const before = combatSnap;
        tick(world, SIM_DT);
        tickAi(world, SIM_DT);
        tickMatchRuntime(world, matchConfig, matchRuntime, SIM_DT);
        combatSnap = playCombatSfx(audio, before, world, combatSnapB);
        combatSnapB = before;
        acc -= SIM_DT;
      }
      const next = matchStatus(world, matchConfig, matchRuntime);
      if (next !== 'playing') {
        status = next;
        paused = false;
        sessionHud.setPaused(false);
        const isLastCampaign =
          playMode === 'campaign' &&
          next === 'won' &&
          campaignIndex >= CAMPAIGN_MAPS.length - 1;
        if (next === 'won' && playMode === 'campaign' && !isLastCampaign) {
          writeCampaignIndex(campaignIndex + 1);
        }
        sessionHud.showEnd({
          outcome: next,
          mode: playMode,
          mapTitle: campaignTitle || undefined,
          showNext:
            playMode === 'campaign' && next === 'won' && !isLastCampaign,
          campaignComplete: isLastCampaign,
        });
        if (next === 'won') audio.win();
        else audio.lose();
      }
    }

    if (sessionMode !== 'playing') {
      starfield.setParallax(camera.x, camera.y);
      starfield.tick(ticker.lastTime * 0.001);
      return;
    }

    syncTrees();

    const playerOrbit = new Map<number, number>();
    for (const s of world.seedlings.values()) {
      if (s.faction !== 'player' || s.state !== 'orbit') continue;
      playerOrbit.set(s.asteroidId, (playerOrbit.get(s.asteroidId) ?? 0) + 1);
    }

    const treesByRock = new Map<number, Tree[]>();
    for (const tree of world.trees.values()) {
      const list = treesByRock.get(tree.asteroidId);
      if (list) list.push(tree);
      else treesByRock.set(tree.asteroidId, [tree]);
    }

    if (palAcc >= PAL_DT) {
      palAcc = 0;
      writeScene(scene, sceneAtTime(world.seed, palTime));
      const hueKey = Math.round(scene.hue);
      if (hueKey !== lastHueKey) {
        lastHueKey = hueKey;
        applySceneToDocument(scene);
        audio.setAtmosphere(scene.hue, scene.dark);
        app.renderer.background.color = scene.bg;
        starfield.retheme(scene);
        seedlings?.retheme(scene);
        preview.retheme();
        graphView.retheme(scene);
        for (const a of world.asteroids.values()) {
          const view = asteroidViews.get(a.id);
          if (!view) continue;
          const local = playerOrbit.get(a.id) ?? 0;
          const plantable = plantableEmptySlots(
            world,
            a.id,
            local,
            gameplay.plantKind,
          );
          view.retheme(
            a,
            scene,
            a.id === gameplay.selectedAsteroidId,
            plantable,
            treesByRock.get(a.id),
          );
        }
        for (const [id, view] of treeViews) {
          const tree = world.trees.get(id);
          if (!tree) continue;
          const asteroid = world.asteroids.get(tree.asteroidId);
          if (!asteroid) continue;
          view.retheme(tree, asteroid, scene);
        }
      }
    }

    for (const a of world.asteroids.values()) {
      const prev = lastOwners.get(a.id);
      if (prev !== a.owner) {
        lastOwners.set(a.id, a.owner);
        if (a.owner === 'player') audio.capture();
      }
    }

    graphView.sync(world, gameplay.selectedAsteroidId);

    for (const a of world.asteroids.values()) {
      const view = asteroidViews.get(a.id);
      if (!view) continue;
      const local = playerOrbit.get(a.id) ?? 0;
      const plantable = plantableEmptySlots(
        world,
        a.id,
        local,
        gameplay.plantKind,
      );
      view.update(
        a,
        a.id === gameplay.selectedAsteroidId,
        plantable,
        treesByRock.get(a.id),
      );
    }

    for (const [id, view] of treeViews) {
      const tree = world.trees.get(id);
      if (!tree) continue;
      const asteroid = world.asteroids.get(tree.asteroidId);
      if (!asteroid) continue;
      view.update(tree, asteroid);
    }

    seedlings?.sync(world.seedlings);

    if (followingSend) {
      const center = travelCentroid(world, 'player');
      if (!center) {
        followingSend = false;
      } else {
        const t = 1 - Math.exp(-3.2 * frameDt);
        camera.followToward(
          center.x,
          center.y,
          app.screen.width,
          app.screen.height,
          t,
        );
      }
    }

    starfield.setParallax(camera.x, camera.y);
    starfield.tick(ticker.lastTime * 0.001);

    const selId = gameplay.selectedAsteroidId;
    const local = selId !== null ? (playerOrbit.get(selId) ?? 0) : 0;
    const sentinels = selId !== null
      ? countOrbitingKind(world, selId, 'player', 'sentinel')
      : 0;
    sessionHud.sync(
      world,
      selId,
      local,
      sentinels,
      gameplay.plantKind,
      gameplay.dragging,
      gameplay.sendCount,
    );
  });
}

boot().catch((err) => {
  console.error(err);
  document.body.textContent = String(err);
});
