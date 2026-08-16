import './style.css';
import { Application } from 'pixi.js';
import { GameAudio } from './game/audio/audio';
import { createCrustMenu } from './game/hud/crustMenu';
import {
  CRUST_MENU_ASK,
  crustPlantActionLabel,
} from './game/hud/copy';
import { createPauseHud } from './game/hud/pauseHud';
import {
  applyReducedMotionClass,
  readMuted,
  readReducedMotion,
  writeMuted,
} from './game/hud/prefs';
import { createSessionHud } from './game/hud/sessionHud';
import { createTitleHud } from './game/hud/titleHud';
import { bindCameraControls } from './game/input/cameraControls';
import { travelCentroid } from './game/input/followSend';
import {
  bindGameplay,
  createGameplayState,
  plantOnCrust,
  shouldLeftPan,
  type GameplayState,
} from './game/input/gameplay';
import {
  bumpSendCount,
  resolveSendCount,
} from './game/input/sendCount';
import {
  AsteroidView,
  EMPTY_PLANTABLE,
} from './game/render/asteroidView';
import { Camera } from './game/render/camera';
import { GraphView } from './game/render/graphView';
import {
  applySceneToDocument,
  createScenePalette,
  sceneAtTime,
  themeAt,
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
import { countFactionOrbiting } from './game/sim/commands';
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
const FPS_SAMPLE_MS = 500;
const DEFAULT_SESSION_SEED = 0xc0a1f00d;

function rockOnScreen(
  x: number,
  y: number,
  radius: number,
  camX: number,
  camY: number,
  zoom: number,
  viewW: number,
  viewH: number,
  pad = 90,
): boolean {
  const sx = x * zoom + camX;
  const sy = y * zoom + camY;
  const pr = (radius + pad) * zoom;
  return sx + pr > 0 && sy + pr > 0 && sx - pr < viewW && sy - pr < viewH;
}

/** `/field.html` skips title / campaign and drops onto a skirmish map. */
function isFieldBoot(): boolean {
  return document.documentElement.dataset.boot === 'field';
}

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

  applyReducedMotionClass(readReducedMotion());
  const audio = new GameAudio();
  audio.setEnabled(!readMuted());

  let sessionSeed = parseSeedFromHash() ?? DEFAULT_SESSION_SEED;
  let world: World = createEmptyWorld(sessionSeed);
  let scene: ScenePalette = createScenePalette(world.seed);
  applySceneToDocument(scene);

  const app = new Application();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  await app.init({
    resizeTo: window,
    antialias: true,
    backgroundColor: scene.bg,
    autoDensity: true,
    resolution: dpr,
    preference: 'webgl',
    powerPreference: 'high-performance',
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
  let abortGameplay: (() => void) | null = null;

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
  let hudAcc = 0;
  let lastHudKey = '';
  let combatSnap = fillCombatSnap(world, emptyCombatSnap());
  let combatSnapB = emptyCombatSnap();
  let lastHueKey = -1;
  let fpsSampleStarted = performance.now();
  let fpsSampleFrames = 0;

  const canAct = () =>
    sessionMode === 'playing' &&
    !paused &&
    !firstRunBlocking &&
    status === 'playing';

  let sessionHud!: ReturnType<typeof createSessionHud>;
  let titleHud!: ReturnType<typeof createTitleHud>;
  let pauseHud!: ReturnType<typeof createPauseHud>;
  let crustMenu!: ReturnType<typeof createCrustMenu>;

  const syncMuteLabel = () => {
    const muted = !audio.isEnabled();
    pauseHud.setMuted(muted);
    sessionHud.setMuted(muted);
  };

  const setMuted = (muted: boolean) => {
    audio.setEnabled(!muted);
    writeMuted(muted);
    syncMuteLabel();
  };

  const resumeMatch = () => {
    paused = false;
    pauseHud.hide();
  };

  const pauseMatch = () => {
    paused = true;
    preview.hide();
    crustMenu.hide();
    pauseHud.show({ showNewMap: playMode === 'skirmish' });
  };

  const setFollowSend = (enabled: boolean) => {
    followSendEnabled = enabled;
    if (!enabled) followingSend = false;
    pauseHud.setFollowSend(enabled);
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
      view.roots.zIndex = 2;
      view.canopy.zIndex = 4;
      treeViews.set(tree.id, view);
      camera.world.addChild(view.roots, view.canopy);
    }
  };

  const clearWorldViews = () => {
    unbindGameplay?.();
    unbindGameplay = null;
    abortGameplay = null;
    preview.hide();
    crustMenu?.hide();
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
    pauseHud.setSeed(formatSeedHex(sessionSeed));
    writeScene(scene, sceneAtTime(world.seed, 0));
    applySceneToDocument(scene);
    audio.beginMatch(scene.hue, scene.dark);
    app.renderer.background.color = scene.bg;
    {
      const themes = themeAt(world.seed, palTime);
      starfield.retheme(scene, themes.themeA, themes.themeB, themes.mix);
    }

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
    const bound = bindGameplay({
      canvas: app.canvas,
      camera,
      world,
      state: gameplay,
      preview,
      audio,
      onCommand: (result) => sessionHud.showCommandResult(result),
      onSend: () => {
        if (followSendEnabled) followingSend = true;
      },
      canAct,
      onSendCountChange: () => {
        sessionHud.syncSendDock(gameplay.sendCount, gameplay.sendMode);
      },
      onCrustMenu: (hit) => {
        crustMenu.show({
          screenX: hit.screenX,
          screenY: hit.screenY,
          ask: CRUST_MENU_ASK,
          plantLabel: crustPlantActionLabel(gameplay.plantKind),
          onPlant: () => {
            const result = plantOnCrust(
              world,
              gameplay,
              hit.asteroidId,
              hit.angle,
            );
            sessionHud.showCommandResult(result);
            if (result.ok) {
              audio.plant(gameplay.plantKind);
              syncTrees();
            } else {
              audio.fail();
            }
          },
        });
      },
    });
    unbindGameplay = bound.unbind;
    abortGameplay = bound.abort;

    camera.zoom = 0.85;
    camera.centerOn(home.x, home.y, app.screen.width, app.screen.height);
    followingSend = false;

    sessionMode = 'playing';
    paused = false;
    status = 'playing';
    acc = 0;
    palTime = 0;
    combatSnap = fillCombatSnap(world, combatSnap);
    lastHueKey = Math.round(scene.hue);
    pauseHud.hide();
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
    if (isFieldBoot()) {
      startSkirmish(skirmishDifficulty, sessionSeed);
      return;
    }
    clearWorldViews();
    sessionMode = 'title';
    status = 'playing';
    paused = false;
    followingSend = false;
    firstRunBlocking = false;
    pauseHud.hide();
    sessionHud.hideEnd();
    sessionHud.setVisible(false);
    sessionHud.dismissFirstRun();
    titleHud.show();
  };

  sessionHud = createSessionHud({
    host,
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
    onMuteToggle: () => setMuted(audio.isEnabled()),
    onSendScout: () => {
      if (!canAct()) return;
      const id = gameplay.selectedAsteroidId;
      if (id === null) return;
      const max = countFactionOrbiting(world, id, 'player');
      gameplay.sendMode = 'scout';
      gameplay.sendCount = resolveSendCount(max, 'scout', 1);
    },
    onSendAll: () => {
      if (!canAct()) return;
      const id = gameplay.selectedAsteroidId;
      if (id === null) return;
      const max = countFactionOrbiting(world, id, 'player');
      gameplay.sendMode = 'all';
      gameplay.sendCount = resolveSendCount(max, 'all', 0);
    },
    onSendBump: (delta) => {
      if (!canAct()) return;
      const id = gameplay.selectedAsteroidId;
      if (id === null) return;
      const max = countFactionOrbiting(world, id, 'player');
      if (max < 1) {
        gameplay.sendCount = 0;
        gameplay.sendMode = 'fixed';
        return;
      }
      gameplay.sendMode = 'fixed';
      gameplay.sendCount = bumpSendCount(max, gameplay.sendCount, delta);
    },
    onFirstRunDismiss: () => {
      firstRunBlocking = false;
    },
  });

  crustMenu = createCrustMenu(host);

  pauseHud = createPauseHud({
    host,
    onResume: () => resumeMatch(),
    onRestart: () => {
      pauseHud.hide();
      restartCurrent();
    },
    onNewMap: () => {
      pauseHud.hide();
      startSkirmish(skirmishDifficulty, freshSeed());
    },
    onTitle: () => showTitle(),
    onMuteToggle: () => setMuted(audio.isEnabled()),
    onFollowToggle: () => setFollowSend(!followSendEnabled),
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
    onMuteChange: (muted) => setMuted(muted),
    onReducedMotionChange: () => {
      /* title already wrote pref + applied class */
    },
  });

  camera.world.sortableChildren = true;
  starfield.root.zIndex = 0;
  graphView.root.zIndex = 1;
  const cameraInput = bindCameraControls(app.canvas, camera, {
    onUserCamera: cancelFollow,
    shouldLeftPan: (e) => {
      const rect = app.canvas.getBoundingClientRect();
      const w = camera.screenToWorld(
        e.clientX - rect.left,
        e.clientY - rect.top,
      );
      return shouldLeftPan(world, w.x, w.y);
    },
    onMultiTouch: () => abortGameplay?.(),
  });

  syncMuteLabel();
  pauseHud.setFollowSend(followSendEnabled);
  if (isFieldBoot()) {
    startSkirmish('normal', parseSeedFromHash() ?? DEFAULT_SESSION_SEED);
  } else {
    showTitle();
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) return;
    if (sessionMode !== 'playing') return;
    if (!sessionHud.endOverlay.hidden) return;
    if (pauseHud.isVisible()) return;
    pauseMatch();
  });

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
    if (e.code === 'Escape' && crustMenu.isVisible()) {
      e.preventDefault();
      crustMenu.hide();
      return;
    }
    if (e.code === 'Escape' || e.code === 'Space') {
      e.preventDefault();
      if (e.repeat) return;
      if (pauseHud.isVisible()) resumeMatch();
      else pauseMatch();
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
    fpsSampleFrames += 1;
    const fpsNow = performance.now();
    const fpsElapsed = fpsNow - fpsSampleStarted;
    if (fpsElapsed >= FPS_SAMPLE_MS) {
      sessionHud.setFps((fpsSampleFrames * 1000) / fpsElapsed);
      fpsSampleFrames = 0;
      fpsSampleStarted = fpsNow;
    }
    cameraInput.tick(frameDt);
    palTime += frameDt;

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
        pauseHud.hide();
        const isLastCampaign =
          playMode === 'campaign' &&
          next === 'won' &&
          campaignIndex >= CAMPAIGN_MAPS.length - 1;
        if (next === 'won' && playMode === 'campaign' && !isLastCampaign) {
          writeCampaignIndex(campaignIndex + 1);
        }
        crustMenu.hide();
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

    if (world.trees.size !== treeViews.size) syncTrees();

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

    // Scene writes happen every frame so the hue drift is continuous. Each
// view caches a 1° hue bucket and skips Graphics work unless its bucket
// changed — so the visible cost is ~360 repaints per cycle, not 60 per
// second. The only throttled path is audio.setAtmosphere (per integer
// hue), because the audio env crossfade doesn't need 60 Hz updates.
writeScene(scene, sceneAtTime(world.seed, palTime));
{
  const hueKey = Math.round(scene.hue);
  if (hueKey !== lastHueKey) {
    lastHueKey = hueKey;
    audio.setAtmosphere(scene.hue, scene.dark);
  }
}
applySceneToDocument(scene);
app.renderer.background.color = scene.bg;
{
  const themes = themeAt(world.seed, palTime);
  starfield.retheme(scene, themes.themeA, themes.themeB, themes.mix);
}
seedlings?.retheme(scene);
preview.retheme();
graphView.retheme(scene);
for (const a of world.asteroids.values()) {
  const view = asteroidViews.get(a.id);
  if (!view) continue;
  view.retheme(
    a,
    scene,
    a.id === gameplay.selectedAsteroidId,
    EMPTY_PLANTABLE,
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

    for (const a of world.asteroids.values()) {
      const prev = lastOwners.get(a.id);
      if (prev !== a.owner) {
        lastOwners.set(a.id, a.owner);
        if (a.owner === 'player') audio.capture();
      }
    }

    graphView.sync(world, gameplay.selectedAsteroidId);

    const viewW = app.screen.width;
    const viewH = app.screen.height;
    for (const a of world.asteroids.values()) {
      const view = asteroidViews.get(a.id);
      if (!view) continue;
      const on = rockOnScreen(
        a.x,
        a.y,
        a.radius,
        camera.x,
        camera.y,
        camera.zoom,
        viewW,
        viewH,
      );
      view.root.visible = on;
      if (!on) continue;
      view.update(
        a,
        a.id === gameplay.selectedAsteroidId,
        EMPTY_PLANTABLE,
        treesByRock.get(a.id),
      );
    }

    const seedlingsArr = [...world.seedlings.values()];

    for (const [id, view] of treeViews) {
      const tree = world.trees.get(id);
      if (!tree) continue;
      const asteroid = world.asteroids.get(tree.asteroidId);
      if (!asteroid) continue;
      const on = rockOnScreen(
        asteroid.x,
        asteroid.y,
        asteroid.radius,
        camera.x,
        camera.y,
        camera.zoom,
        viewW,
        viewH,
      );
      view.canopy.visible = on;
      view.roots.visible = on;
      if (!on) continue;
      view.update(tree, asteroid);
      view.setDepartingSeedlings(seedlingsArr, tree, asteroid);
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
    hudAcc += frameDt;
    const hudKey = `${selId}:${gameplay.dragging}:${gameplay.plantKind}:${gameplay.sendMode}:${gameplay.sendCount}:${local}`;
    if (hudAcc >= 0.12 || hudKey !== lastHudKey) {
      hudAcc = 0;
      lastHudKey = hudKey;
      sessionHud.sync(
        world,
        selId,
        local,
        sentinels,
        gameplay.plantKind,
        gameplay.dragging,
        gameplay.sendCount,
        gameplay.sendMode,
      );
    }
  });
}

boot().catch((err) => {
  console.error(err);
  document.body.textContent = String(err);
});
