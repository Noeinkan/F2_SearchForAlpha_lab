import type { GameAudio } from '../audio/audio';
import type { Camera } from '../render/camera';
import type { SendPreview } from '../render/sendPreview';
import {
  countFactionOrbiting,
  plantDyson,
  sendSeedlings,
} from '../sim/commands';
import { shortestPath } from '../sim/graph';
import { PLANT_COST, type World } from '../sim/types';
import { getOccupiedSlots, slotPosition } from '../sim/world';

export interface GameplayState {
  selectedAsteroidId: number | null;
  sendCount: number;
  dragging: boolean;
  dragFromId: number | null;
  hoverTargetId: number | null;
  cursorWorld: { x: number; y: number };
}

export function createGameplayState(homeId: number): GameplayState {
  return {
    selectedAsteroidId: homeId,
    sendCount: 0,
    dragging: false,
    dragFromId: null,
    hoverTargetId: null,
    cursorWorld: { x: 0, y: 0 },
  };
}

const DRAG_THRESHOLD = 8;

export function bindGameplay(opts: {
  canvas: HTMLCanvasElement;
  camera: Camera;
  world: World;
  state: GameplayState;
  preview: SendPreview;
  audio: GameAudio;
  onPlanted: () => void;
}): () => void {
  const { canvas, camera, world, state, preview, audio, onPlanted } = opts;

  let pointerDown = false;
  let downX = 0;
  let downY = 0;
  let downWorld = { x: 0, y: 0 };
  let shiftOnDown = false;
  let didDrag = false;

  const orbitCount = (asteroidId: number) =>
    countFactionOrbiting(world, asteroidId, 'player');

  const refreshSendCountDefault = (fromId: number, scout: boolean) => {
    const n = orbitCount(fromId);
    state.sendCount = scout ? Math.min(1, n) : n;
  };

  const hitAsteroid = (wx: number, wy: number): number | null => {
    let best: number | null = null;
    let bestDist = Infinity;
    for (const a of world.asteroids.values()) {
      const d = Math.hypot(wx - a.x, wy - a.y);
      // Include the orbit band so clicking seedlings still selects the rock
      if (d <= a.radius + 42 && d < bestDist) {
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
    let bestDist = 22;
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

  const onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    pointerDown = true;
    didDrag = false;
    downX = e.clientX;
    downY = e.clientY;
    downWorld = worldFromEvent(e);
    state.cursorWorld = downWorld;
    shiftOnDown = e.shiftKey;

    const slot = hitSlot(downWorld.x, downWorld.y);
    if (slot) {
      // Plant on click-up if no drag — remember for pointerup
      return;
    }

    const hit = hitAsteroid(downWorld.x, downWorld.y);
    if (hit !== null) {
      state.selectedAsteroidId = hit;
      state.dragFromId = hit;
      refreshSendCountDefault(hit, shiftOnDown);
    } else if (state.selectedAsteroidId !== null) {
      // Drag from the selected rock even if the press starts in empty space nearby
      state.dragFromId = state.selectedAsteroidId;
      refreshSendCountDefault(state.selectedAsteroidId, shiftOnDown);
    }
  };

  const onPointerMove = (e: PointerEvent) => {
    const w = worldFromEvent(e);
    state.cursorWorld = w;
    if (!pointerDown) return;

    const dist = Math.hypot(e.clientX - downX, e.clientY - downY);
    if (!didDrag && dist >= DRAG_THRESHOLD && state.dragFromId !== null) {
      didDrag = true;
      state.dragging = true;
      refreshSendCountDefault(state.dragFromId, shiftOnDown);
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
    const w = worldFromEvent(e);

    if (!didDrag) {
      const slot = hitSlot(w.x, w.y);
      if (slot) {
        const result = plantDyson(
          world,
          slot.asteroidId,
          slot.slotIndex,
          'player',
        );
        if (result.ok) {
          audio.plant();
          onPlanted();
        }
      } else {
        const hit = hitAsteroid(w.x, w.y);
        if (hit !== null) state.selectedAsteroidId = hit;
      }
    } else if (
      state.dragging &&
      state.dragFromId !== null &&
      state.hoverTargetId !== null
    ) {
      const result = sendSeedlings(
        world,
        state.dragFromId,
        state.hoverTargetId,
        state.sendCount,
        'player',
      );
      if (result.ok) audio.send();
    }

    pointerDown = false;
    didDrag = false;
    state.dragging = false;
    state.dragFromId = null;
    state.hoverTargetId = null;
    preview.hide();
  };

  const onWheel = (e: WheelEvent) => {
    if (!state.dragging || state.dragFromId === null) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const max = orbitCount(state.dragFromId);
    if (max < 1) {
      state.sendCount = 0;
      return;
    }
    const delta = e.deltaY < 0 ? 1 : -1;
    state.sendCount = Math.min(max, Math.max(1, state.sendCount + delta));
  };

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('wheel', onWheel, { passive: false, capture: true });

  return () => {
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerUp);
    canvas.removeEventListener('wheel', onWheel, true);
  };
}
