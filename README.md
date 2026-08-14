# Asterbloom

An original browser strategy game inspired by the systems of **Eufloria** (2009, Omni Systems / Alex May, Rudolf Kremers, Brian Grainger). All art, music, copy, and level scripts are original — no ripped assets or trademarks.

Grow fractal trees on asteroids, raise seedlings, and expand across a dark starfield.

## Run

```bash
npm install
npm run dev
```

## Test

```bash
npm test
```

## Controls (core loop)

- **Left click** — select asteroid
- **Left drag** — send seedlings (path must connect via travel radii)
- **Wheel while dragging** — change send count (Shift+drag = scout 1)
- **Click empty slot** — plant Dyson (costs 10 orbiting seedlings; claims neutral rocks)
- **Wheel** (idle) — zoom toward cursor
- **Middle / right mouse drag** / **WASD** — pan
- First click starts ambient audio
