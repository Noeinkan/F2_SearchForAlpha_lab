import type { Asteroid, World } from './types';

/** Outbound edge if distance ≤ source travelRadius. */
export function canReach(from: Asteroid, to: Asteroid): boolean {
  if (from.id === to.id) return false;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  return dx * dx + dy * dy <= from.travelRadius * from.travelRadius;
}

export function neighbors(world: World, asteroidId: number): number[] {
  const from = world.asteroids.get(asteroidId);
  if (!from) return [];
  const out: number[] = [];
  for (const other of world.asteroids.values()) {
    if (canReach(from, other)) out.push(other.id);
  }
  return out;
}

/** BFS shortest path of asteroid ids including start and end. Null if unreachable. */
export function shortestPath(
  world: World,
  fromId: number,
  toId: number,
): number[] | null {
  if (fromId === toId) return [fromId];
  if (!world.asteroids.has(fromId) || !world.asteroids.has(toId)) return null;

  const queue: number[] = [fromId];
  const prev = new Map<number, number | null>();
  prev.set(fromId, null);

  while (queue.length > 0) {
    const cur = queue.shift()!;
    if (cur === toId) break;
    for (const n of neighbors(world, cur)) {
      if (prev.has(n)) continue;
      prev.set(n, cur);
      queue.push(n);
    }
  }

  if (!prev.has(toId)) return null;

  const path: number[] = [];
  let walk: number | null = toId;
  while (walk !== null) {
    path.push(walk);
    walk = prev.get(walk) ?? null;
  }
  path.reverse();
  return path;
}

export function isGraphConnected(world: World): boolean {
  const ids = [...world.asteroids.keys()];
  if (ids.length === 0) return true;
  const start = ids[0]!;
  const seen = new Set<number>();
  const queue = [start];
  seen.add(start);
  while (queue.length > 0) {
    const cur = queue.shift()!;
    for (const n of neighbors(world, cur)) {
      if (seen.has(n)) continue;
      seen.add(n);
      queue.push(n);
    }
  }
  return seen.size === ids.length;
}

export function allEdges(world: World): Array<[number, number]> {
  const edges: Array<[number, number]> = [];
  for (const a of world.asteroids.values()) {
    for (const b of world.asteroids.values()) {
      if (b.id <= a.id) continue;
      if (canReach(a, b) || canReach(b, a)) {
        edges.push([a.id, b.id]);
      }
    }
  }
  return edges;
}
