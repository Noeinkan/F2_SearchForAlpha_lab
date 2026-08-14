import type { Rng } from './rng';
import { pick } from './rng';

const PREFIXES = [
  'Ash',
  'Bloom',
  'Cinder',
  'Drift',
  'Ember',
  'Fern',
  'Glim',
  'Haze',
  'Iris',
  'Jade',
  'Kelp',
  'Lumen',
  'Moss',
  'Nimbus',
  'Orchid',
  'Petal',
  'Quartz',
  'Root',
  'Spore',
  'Thorn',
  'Umbra',
  'Vine',
  'Wisp',
  'Xylem',
  'Yarrow',
  'Zephyr',
] as const;

const SUFFIXES = [
  'ara',
  'elle',
  'ion',
  'ora',
  'ule',
  'yx',
  'eth',
  'ine',
  'os',
  'um',
  'ael',
  'ith',
] as const;

/** Original procedural asteroid names (not from Eufloria). */
export function generateAsteroidName(rng: Rng): string {
  return `${pick(rng, PREFIXES)}${pick(rng, SUFFIXES)}`;
}
