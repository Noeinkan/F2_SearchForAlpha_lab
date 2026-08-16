import type { FactionId, World } from '../sim/types';

/** Mean position of traveling seedlings for a faction, or null if none. */
export function travelCentroid(
  world: World,
  faction: FactionId = 'player',
): { x: number; y: number } | null {
  let sx = 0;
  let sy = 0;
  let n = 0;
  for (const s of world.seedlings.values()) {
    if (s.faction !== faction) continue;
    if (s.state !== 'travel') continue;
    sx += s.x;
    sy += s.y;
    n++;
  }
  if (n === 0) return null;
  return { x: sx / n, y: sy / n };
}
