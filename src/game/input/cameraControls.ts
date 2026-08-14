import type { Camera } from '../render/camera';

export function bindCameraControls(
  canvas: HTMLCanvasElement,
  camera: Camera,
): () => void {
  const keys = new Set<string>();
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  const onWheel = (e: WheelEvent) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    camera.zoomAt(sx, sy, factor);
  };

  const onPointerDown = (e: PointerEvent) => {
    // Middle (1) or right (2) — left reserved for send-gesture later
    if (e.button !== 1 && e.button !== 2) return;
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: PointerEvent) => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    camera.pan(dx, dy);
  };

  const onPointerUp = (e: PointerEvent) => {
    if (e.button === 1 || e.button === 2) dragging = false;
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
