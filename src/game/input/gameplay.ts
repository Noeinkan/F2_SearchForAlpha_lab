import type { GameAudio } from '../audio/audio';
import type { Camera } from '../render/camera';
import type { SendPreview } from '../render/sendPreview';
import {
  countFactionOrbiting,
  plantTree,
  sendSeedlings,
  type CommandResult,
} from '../sim/commands';
import { shortestPath } from '../sim/graph';
import { PLANT_COST, orbitBand, type TreeKind, type World } from '../sim/types';
import { getOccupiedSlots, slotPosition } from '../sim/world';
import {
  bumpSendCount,
  isCoarsePointer,
  resolveSendCount,
  type SendMode,
} from './sendCount';

export type { SendMode };

export interface GameplayState {
  selectedAsteroidId: number | null;
  sendCount: number;
  sendMode: SendMode;
  dragging: boolean;
  dragFromId: number | null;
  hoverTargetId: number | null;
  cursorWorld: { x: number; y: number };
  plantKind: TreeKind;
}

export function createGameplayState(homeId: number): GameplayState {
  return {
    selectedAsteroidId: homeId,
    sendCount: 0,
    sendMode: 'all',
    dragging: false,
    dragFromId: null,
    hoverTargetId: null,
    cursorWorld: { x: 0, y: 0 },
    plantKind: 'dyson',
  };
}

const DRAG_THRESHOLD = 8;
const FINE_ASTEROID_PAD = 28;
const COARSE_ASTEROID_PAD = 48;
const FINE_SLOT_HIT = 22;
const COARSE_SLOT_HIT = 40;

export function bindGameplay(opts: {
  canvas: HTMLCanvasElement;
  camera: Camera;
  world: World;
  state: GameplayState;
  preview: SendPreview;
  audio: GameAudio;
  onPlanted: () => void;
  /** Fired for every plant/send attempt (success or failure). */
  onCommand?: (result: CommandResult) => void;
  /** Fired after a successful player send (optional follow-send). */
  onSend?: () => void;
  /** When false, ignore send / plant / selection gestures. */
  canAct?: () => boolean;
  /** Called when send count / mode changes (HUD dock). */
  onSendCountChange?: () => void;
}): () => void {
  const {
    canvas,
    camera,
    world,
    state,
    preview,
    audio,
    onPlanted,
    onCommand,
    onSend,
    canAct = () => true,
    onSendCountChange,
  } = opts;

  let pointerDown = false;
  let activePointerId: number | null = null;
  let downX = 0;
  let downY = 0;
  let downWorld = { x: 0, y: 0 };
  let shiftOnDown = false;
  let didDrag = false;
  let aborted = false;

  const coarse = () => isCoarsePointer();

  const orbitCount = (asteroidId: number) =>
    countFactionOrbiting(world, asteroidId, 'player');

  const applySendForRock = (fromId: number, forceScout: boolean) => {
    const n = orbitCount(fromId);
    if (forceScout) {
      state.sendMode = 'scout';
      state.sendCount = resolveSendCount(n, 'scout', 1);
    } else {
      state.sendCount = resolveSendCount(n, state.sendMode, state.sendCount);
    }
    onSendCountChange?.();
  };

  const hitAsteroid = (wx: number, wy: number): number | null => {
    const pad = coarse() ? COARSE_ASTEROID_PAD : FINE_ASTEROID_PAD;
    let best: number | null = null;
    let bestDist = Infinity;
    for (const a of world.asteroids.values()) {
      const d = Math.hypot(wx - a.x, wy - a.y);
      // Include the orbit band so clicking seedlings still selects the rock
      if (d <= a.radius + orbitBand(a.radius) + pad && d < bestDist) {
        bestDist = d;
        best = a.id;
      }
    }
    return best;
  };

  const hitSlot = (
    wx: number,
    wy: number,
  ): { asteroidId: number; slotIndex: number } | null => {
    let best: { asteroidId: number; slotIndex: number } | null = null;
    let bestDist = coarse() ? COARSE_SLOT_HIT : FINE_SLOT_HIT;
    for (const a of world.asteroids.values()) {
      if (orbitCount(a.id) < PLANT_COST) continue;
      const occupied = getOccupiedSlots(world, a.id);
      for (let i = 0; i < a.treeSlots; i++) {
        if (occupied.has(i)) continue;
        const pos = slotPosition(a, i);
        const d = Math.hypot(wx - pos.x, wy - pos.y);
        if (d <= bestDist) {
          bestDist = d;
          best = { asteroidId: a.id, slotIndex: i };
        }
      }
    }
    return best;
  };

  const worldFromEvent = (e: PointerEvent) => {
    const rect = canvas.getBoundingClientRect();
    return camera.screenToWorld(e.clientX - rect.left, e.clientY - rect.top);
  };

  const clearGesture = () => {
    pointerDown = false;
    activePointerId = null;
    didDrag = false;
    aborted = false;
    state.dragging = false;
    state.dragFromId = null;
    state.hoverTargetId = null;
    preview.hide();
  };

  const abortGesture = () => {
    if (!pointerDown && !state.dragging) return;
    aborted = true;
    clearGesture();
  };

  const onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    if (!canAct()) return;

    // Second finger: abort send so camera pinch can take over.
    if (pointerDown && activePointerId !== null && e.pointerId !== activePointerId) {
      abortGesture();
      return;
    }

    pointerDown = true;
    activePointerId = e.pointerId;
    didDrag = false;
    aborted = false;
    downX = e.clientX;
    downY = e.clientY;
    downWorld = worldFromEvent(e);
    state.cursorWorld = downWorld;
    shiftOnDown = e.shiftKey;

    try {
      canvas.setPointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }

    const slot = hitSlot(downWorld.x, downWorld.y);
    if (slot) {
      // Plant on click-up if no drag — remember for pointerup
      return;
    }

    const hit = hitAsteroid(downWorld.x, downWorld.y);
    if (hit !== null) {
      state.selectedAsteroidId = hit;
      state.dragFromId = hit;
      applySendForRock(hit, shiftOnDown);
    } else if (!coarse() && state.selectedAsteroidId !== null) {
      // Fine pointer: drag from the selected rock even from empty space
      state.dragFromId = state.selectedAsteroidId;
      applySendForRock(state.selectedAsteroidId, shiftOnDown);
    }
  };

  const onPointerMove = (e: PointerEvent) => {
    if (activePointerId !== null && e.pointerId !== activePointerId) return;
    const w = worldFromEvent(e);
    state.cursorWorld = w;
    if (!pointerDown || aborted || !canAct()) return;

    const dist = Math.hypot(e.clientX - downX, e.clientY - downY);
    if (!didDrag && dist >= DRAG_THRESHOLD && state.dragFromId !== null) {
      didDrag = true;
      state.dragging = true;
      applySendForRock(state.dragFromId, shiftOnDown);
    }

    if (state.dragging && state.dragFromId !== null) {
      const target = hitAsteroid(w.x, w.y);
      state.hoverTargetId =
        target !== null && target !== state.dragFromId ? target : null;
      const from = world.asteroids.get(state.dragFromId)!;
      const path =
        state.hoverTargetId !== null
          ? shortestPath(world, state.dragFromId, state.hoverTargetId)
          : null;
      const valid = !!path && path.length >= 2 && state.sendCount > 0;
      const toX =
        state.hoverTargetId !== null
          ? world.asteroids.get(state.hoverTargetId)!.x
          : w.x;
      const toY =
        state.hoverTargetId !== null
          ? world.asteroids.get(state.hoverTargetId)!.y
          : w.y;
      preview.show(from.x, from.y, toX, toY, state.sendCount, valid);
    }
  };

  const onPointerUp = (e: PointerEvent) => {
    if (e.button !== 0) return;
    if (activePointerId !== null && e.pointerId !== activePointerId) return;

    const wasAborted = aborted;
    const wasDragging = didDrag && state.dragging;
    const fromId = state.dragFromId;
    const toId = state.hoverTargetId;
    const sendN = state.sendCount;
    const w = worldFromEvent(e);

    if (!wasAborted && canAct()) {
      if (!didDrag) {
        const slot = hitSlot(w.x, w.y);
        if (slot) {
          const result = plantTree(
            world,
            slot.asteroidId,
            slot.slotIndex,
            'player',
            state.plantKind,
          );
          onCommand?.(result);
          if (result.ok) {
            audio.plant(state.plantKind);
            onPlanted();
          } else {
            audio.fail();
          }
        } else {
          const hit = hitAsteroid(w.x, w.y);
          if (hit !== null) {
            state.selectedAsteroidId = hit;
            applySendForRock(hit, false);
          }
        }
      } else if (wasDragging && fromId !== null && toId !== null) {
        const result = sendSeedlings(world, fromId, toId, sendN, 'player');
        onCommand?.(result);
        if (result.ok) {
          audio.send(sendN);
          onSend?.();
        } else audio.fail();
      }
    }

    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    clearGesture();
  };

  const onPointerCancel = (e: PointerEvent) => {
    if (activePointerId !== null && e.pointerId !== activePointerId) return;
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
    abortGesture();
  };

  const onWheel = (e: WheelEvent) => {
    if (!canAct() || !state.dragging || state.dragFromId === null) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const max = orbitCount(state.dragFromId);
    if (max < 1) {
      state.sendCount = 0;
      state.sendMode = 'fixed';
      onSendCountChange?.();
      return;
    }
    const delta = e.deltaY < 0 ? 1 : -1;
    state.sendMode = 'fixed';
    state.sendCount = bumpSendCount(max, state.sendCount, delta);
    onSendCountChange?.();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (!canAct()) return;
    if (e.key === '1') state.plantKind = 'dyson';
    else if (e.key === '2') state.plantKind = 'energy';
    else if (e.key === '3') state.plantKind = 'defense';
  };

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerCancel);
  canvas.addEventListener('wheel', onWheel, { passive: false, capture: true });

  window.addEventListener('keydown', onKeyDown);

  return () => {
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerCancel);
    canvas.removeEventListener('wheel', onWheel, true);
    window.removeEventListener('keydown', onKeyDown);
  };
}

/** True when a left-finger press on empty space should pan the camera (coarse). */
export function shouldLeftPan(
  world: World,
  wx: number,
  wy: number,
): boolean {
  if (!isCoarsePointer()) return false;
  const pad = COARSE_ASTEROID_PAD;
  for (const a of world.asteroids.values()) {
    const d = Math.hypot(wx - a.x, wy - a.y);
    if (d <= a.radius + orbitBand(a.radius) + pad) return false;
  }
  return true;
}
