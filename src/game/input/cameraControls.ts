import type { Camera } from '../render/camera';
import { isCoarsePointer } from './sendCount';

type PointerSample = { x: number; y: number };

export function bindCameraControls(
  canvas: HTMLCanvasElement,
  camera: Camera,
  opts?: {
    onUserCamera?: () => void;
    /** When true, left button on this down may start one-finger pan (coarse). */
    shouldLeftPan?: (e: PointerEvent) => boolean;
    /** Abort gameplay send when multi-touch starts. */
    onMultiTouch?: () => void;
  },
): () => void {
  const keys = new Set<string>();
  const pointers = new Map<number, PointerSample>();
  let buttonPan = false;
  let lastX = 0;
  let lastY = 0;
  let pinchDist = 0;
  let pinchMidX = 0;
  let pinchMidY = 0;
  const onUserCamera = opts?.onUserCamera;

  const twoFingerMetrics = () => {
    const pts = [...pointers.values()];
    if (pts.length < 2) return null;
    const a = pts[0]!;
    const b = pts[1]!;
    const midX = (a.x + b.x) / 2;
    const midY = (a.y + b.y) / 2;
    const dist = Math.hypot(a.x - b.x, a.y - b.y);
    return { midX, midY, dist };
  };

  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    camera.zoomAt(sx, sy, factor);
    onUserCamera?.();
  };

  const onPointerDown = (e: PointerEvent) => {
    const pos = { x: e.clientX, y: e.clientY };
    pointers.set(e.pointerId, pos);

    if (pointers.size === 2) {
      opts?.onMultiTouch?.();
      buttonPan = false;
      const m = twoFingerMetrics();
      if (m) {
        pinchDist = m.dist;
        pinchMidX = m.midX;
        pinchMidY = m.midY;
      }
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      return;
    }

    // Middle (1) or right (2) — always pan
    if (e.button === 1 || e.button === 2) {
      buttonPan = true;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.setPointerCapture(e.pointerId);
      return;
    }

    // Coarse left: pan empty space
    if (
      e.button === 0 &&
      isCoarsePointer() &&
      opts?.shouldLeftPan?.(e)
    ) {
      buttonPan = true;
      lastX = e.clientX;
      lastY = e.clientY;
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    }
  };

  const onPointerMove = (e: PointerEvent) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pointers.size >= 2) {
      const m = twoFingerMetrics();
      if (!m) return;
      const dx = m.midX - pinchMidX;
      const dy = m.midY - pinchMidY;
      if (dx || dy) {
        camera.pan(dx, dy);
        onUserCamera?.();
      }
      if (pinchDist > 8 && m.dist > 8) {
        const factor = m.dist / pinchDist;
        if (factor > 0.01 && factor < 100) {
          const rect = canvas.getBoundingClientRect();
          camera.zoomAt(m.midX - rect.left, m.midY - rect.top, factor);
          onUserCamera?.();
        }
      }
      pinchDist = m.dist;
      pinchMidX = m.midX;
      pinchMidY = m.midY;
      return;
    }

    if (!buttonPan) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    camera.pan(dx, dy);
    onUserCamera?.();
  };

  const onPointerUp = (e: PointerEvent) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) {
      pinchDist = 0;
    }
    if (pointers.size === 1) {
      const remaining = [...pointers.values()][0]!;
      lastX = remaining.x;
      lastY = remaining.y;
      // After pinch, do not resume left-pan unless middle/right started it
      if (e.button === 0 && isCoarsePointer()) buttonPan = false;
    }
    if (pointers.size === 0) {
      buttonPan = false;
    }
    if (e.button === 1 || e.button === 2) {
      if (pointers.size === 0) buttonPan = false;
    }
  };

  const onContextMenu = (e: Event) => e.preventDefault();

  const onKeyDown = (e: KeyboardEvent) => {
    keys.add(e.key.toLowerCase());
  };
  const onKeyUp = (e: KeyboardEvent) => {
    keys.delete(e.key.toLowerCase());
  };

  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', onPointerUp);
  canvas.addEventListener('pointercancel', onPointerUp);
  canvas.addEventListener('contextmenu', onContextMenu);
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);

  const panSpeed = 420;
  let raf = 0;
  let last = performance.now();

  const tickKeys = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    let dx = 0;
    let dy = 0;
    if (keys.has('a') || keys.has('arrowleft')) dx += 1;
    if (keys.has('d') || keys.has('arrowright')) dx -= 1;
    if (keys.has('w') || keys.has('arrowup')) dy += 1;
    if (keys.has('s') || keys.has('arrowdown')) dy -= 1;
    if (dx || dy) {
      const len = Math.hypot(dx, dy) || 1;
      camera.pan((dx / len) * panSpeed * dt, (dy / len) * panSpeed * dt);
      onUserCamera?.();
    }
    raf = requestAnimationFrame(tickKeys);
  };
  raf = requestAnimationFrame(tickKeys);

  return () => {
    cancelAnimationFrame(raf);
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('pointerdown', onPointerDown);
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('pointerup', onPointerUp);
    canvas.removeEventListener('pointercancel', onPointerUp);
    canvas.removeEventListener('contextmenu', onContextMenu);
    window.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('keyup', onKeyUp);
  };
}
