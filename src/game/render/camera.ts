import { Container } from 'pixi.js';

export class Camera {
  readonly world = new Container();
  x = 0;
  y = 0;
  zoom = 1;

  readonly minZoom = 0.25;
  readonly maxZoom = 4;

  apply(): void {
    this.world.scale.set(this.zoom);
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
   */
  zoomAt(screenX: number, screenY: number, factor: number): void {
    const before = this.screenToWorld(screenX, screenY);
    this.zoom = Math.min(
      this.maxZoom,
      Math.max(this.minZoom, this.zoom * factor),
    );
    this.apply();
    const after = this.screenToWorld(screenX, screenY);
    this.x += (after.x - before.x) * this.zoom;
    this.y += (after.y - before.y) * this.zoom;
    this.apply();
  }

  screenToWorld(screenX: number, screenY: number): { x: number; y: number } {
    return {
      x: (screenX - this.x) / this.zoom,
      y: (screenY - this.y) / this.zoom,
    };
  }

  centerOn(worldX: number, worldY: number, viewW: number, viewH: number): void {
    this.x = viewW / 2 - worldX * this.zoom;
    this.y = viewH / 2 - worldY * this.zoom;
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
    const tx = viewW / 2 - worldX * this.zoom;
    const ty = viewH / 2 - worldY * this.zoom;
    this.x += (tx - this.x) * k;
    this.y += (ty - this.y) * k;
    this.apply();
  }
}
