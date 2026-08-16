import { Container } from 'pixi.js';

export class Camera {
  readonly world = new Container();
  x = 0;
  y = 0;
  private _zoom = 1;
  private targetZoom = 1;
  private zoomScreenX = 0;
  private zoomScreenY = 0;

  readonly minZoom = 0.25;
  readonly maxZoom = 8;

  get zoom(): number {
    return this._zoom;
  }

  set zoom(v: number) {
    this._zoom = this.clampZoom(v);
    this.targetZoom = this._zoom;
  }

  apply(): void {
    this.world.scale.set(this._zoom);
    this.world.position.set(this.x, this.y);
  }

  /** Pan by screen-space delta (pixels). */
  pan(dx: number, dy: number): void {
    this.x += dx;
    this.y += dy;
    this.apply();
  }

  /**
   * Zoom toward a screen point (relative to stage / canvas).
   * screenX/Y are in CSS pixels from canvas top-left.
   * Default eases toward the new zoom; pinch should pass `immediate`.
   */
  zoomAt(
    screenX: number,
    screenY: number,
    factor: number,
    immediate = false,
  ): void {
    if (factor === 1) return;
    this.zoomScreenX = screenX;
    this.zoomScreenY = screenY;
    this.targetZoom = this.clampZoom(this.targetZoom * factor);
    if (immediate) this.commitZoom(this.targetZoom);
  }

  /** Ease zoom toward the last wheel/pinch focus. Call once per frame. */
  tick(dt: number): void {
    const gap = this.targetZoom - this._zoom;
    if (Math.abs(gap) < 1e-4) {
      if (gap !== 0) this.commitZoom(this.targetZoom);
      return;
    }
    const t = 1 - Math.exp(-18 * dt);
    this.commitZoom(this._zoom + gap * t);
  }

  screenToWorld(screenX: number, screenY: number): { x: number; y: number } {
    return {
      x: (screenX - this.x) / this._zoom,
      y: (screenY - this.y) / this._zoom,
    };
  }

  centerOn(worldX: number, worldY: number, viewW: number, viewH: number): void {
    this.x = viewW / 2 - worldX * this._zoom;
    this.y = viewH / 2 - worldY * this._zoom;
    this.apply();
  }

  /** Soft lerp toward centering world coords in the view (t in 0..1). */
  followToward(
    worldX: number,
    worldY: number,
    viewW: number,
    viewH: number,
    t: number,
  ): void {
    const k = Math.min(1, Math.max(0, t));
    const tx = viewW / 2 - worldX * this._zoom;
    const ty = viewH / 2 - worldY * this._zoom;
    this.x += (tx - this.x) * k;
    this.y += (ty - this.y) * k;
    this.apply();
  }

  private clampZoom(z: number): number {
    return Math.min(this.maxZoom, Math.max(this.minZoom, z));
  }

  private commitZoom(next: number): void {
    const z = this.clampZoom(next);
    if (z === this._zoom) return;
    const before = this.screenToWorld(this.zoomScreenX, this.zoomScreenY);
    this._zoom = z;
    this.apply();
    const after = this.screenToWorld(this.zoomScreenX, this.zoomScreenY);
    this.x += (after.x - before.x) * this._zoom;
    this.y += (after.y - before.y) * this._zoom;
    this.apply();
  }
}
