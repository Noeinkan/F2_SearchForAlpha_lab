import type { Seedling } from './types';

/** Simple uniform grid for neighbor queries among units. */
export class SpatialHash {
  private cellSize: number;
  private cells = new Map<string, number[]>();

  constructor(cellSize = 80) {
    this.cellSize = cellSize;
  }

  clear(): void {
    this.cells.clear();
  }

  private key(x: number, y: number): string {
    const cx = Math.floor(x / this.cellSize);
    const cy = Math.floor(y / this.cellSize);
    return `${cx},${cy}`;
  }

  insert(id: number, x: number, y: number): void {
    const k = this.key(x, y);
    let bucket = this.cells.get(k);
    if (!bucket) {
      bucket = [];
      this.cells.set(k, bucket);
    }
    bucket.push(id);
  }

  query(
    x: number,
    y: number,
    radius: number,
    units: Map<number, Seedling>,
  ): Seedling[] {
    const result: Seedling[] = [];
    const r2 = radius * radius;
    const minCx = Math.floor((x - radius) / this.cellSize);
    const maxCx = Math.floor((x + radius) / this.cellSize);
    const minCy = Math.floor((y - radius) / this.cellSize);
    const maxCy = Math.floor((y + radius) / this.cellSize);
    for (let cx = minCx; cx <= maxCx; cx++) {
      for (let cy = minCy; cy <= maxCy; cy++) {
        const bucket = this.cells.get(`${cx},${cy}`);
        if (!bucket) continue;
        for (const id of bucket) {
          const u = units.get(id);
          if (!u) continue;
          const dx = u.x - x;
          const dy = u.y - y;
          if (dx * dx + dy * dy <= r2) result.push(u);
        }
      }
    }
    return result;
  }
}
