# Asterbloom

An original browser strategy game inspired by the systems of **Eufloria** (2009, Omni Systems / Alex May, Rudolf Kremers, Brian Grainger). All art, music, copy, and level scripts are original — no ripped assets or trademarks.

Grow fractal trees on asteroids, raise seedlings, and expand across a dark starfield.

Long-term plan: [ROADMAP.md](ROADMAP.md). Current ship version: **0.1.0**.

## Run

```bash
npm install
npm run dev      # full game: title → Play / Campaign / Settings
npm run field    # skip the shell; drop onto a skirmish map
```

If `npm run dev` is already running, open `/field.html` on the same server. URL hash `#s=<hex>` still rematches a layout.

## Ship

```bash
npm run build    # writes static site to dist/
npm run preview  # local check of the build
```

Host the `dist/` folder on any static server. No console steps required for a first session.

Manual check: Chromium and Firefox at 1280×720 and 1920×1080.

## Test

```bash
npm test
```

## Core loop

Each asteroid holds trees. Trees make seedlings over time.
Select an asteroid, then drag to send seedlings to another.

- **Empty rock** — seedlings land and orbit. Right-click (or hold) the crust to plant a tree (10 seedlings).
- **Wild or enemy rock** — your seedlings fight the defenders in real time. Mass and type decide. After the garrison is gone, enemy trees burn, then you can plant.

## Seedling types

- **Basic** — cheap, weak alone, strong in groups. Grown on Dyson trees.
- **Sentinel** — fighters grown on **Energy trees**. Stronger in combat, drain the asteroid’s energy pool to stay alive.

## Trees

- **1 Dyson** — produces basic seedlings.
- **2 Energy** — requires a high-Energy asteroid. Produces Sentinels.
- **3 Defense** — requires some Energy. Raises a shield that soaks incoming fire.

## Resources

- **Minerals** — fixed per rock. Sets tree-slot count and how fast trees produce.
- **Energy** — regenerating pool. Lets you plant Energy/Defense trees, spawn Sentinels, and keep shields up.
- **Strength / Speed** — inherited by seedlings grown on that rock (combat power and travel).

Early asteroid choice matters: size and minerals do not change.

## Controls

- **Tap / left click** — select asteroid
- **Drag** — send seedlings (path must connect via travel radii)
- **HUD send dock** — Scout / − / count / + / All (also: wheel while dragging; Shift+drag = scout 1)
- **HUD 1 / 2 / 3** or keyboard — Dyson / Energy / Defense tree
- **Tap / click empty slot** — plant (costs 10 orbiting seedlings; claims the rock)
- **HUD Pause** / **Esc / Space** — pause menu (Resume, Restart, New map, Quit to title)
- **M** / HUD **Sound** / title **Settings** — mute ambient and SFX
- **F** / HUD **Follow** — optional follow-send (pan or zoom cancels the current follow)
- **Restart** — same map (skirmish seed or campaign map)
- **New map** — skirmish only: generate a fresh seed
- **Next grove** — campaign win: advance to the next authored map
- **Title** — return to Play / Campaign / Settings
- **Wheel** (idle) / **pinch** — zoom (up to 8× for inspecting tree detail)
- **Empty-space drag** (touch) / **middle / right mouse drag** / **WASD** / **mouse to screen edge** — pan
- First click starts ambient audio
- Hiding the browser tab pauses the match (does not auto-resume)

## Session

Boot opens a **title** screen:

- **Play** — skirmish generator (~14–20 asteroids), Easy / Normal / Hard AI. URL hash `#s=<hex>` rematches the same layout.
- **Campaign** — eight authored maps. The list remembers your last map index in `localStorage`.
- **Settings** — mute and reduced motion (persisted).

### How a match ends

- **Win (eliminate)** — no enemy trees or pending plants left (skirmish default; many campaign maps).
- **Win (hold)** — own N rocks continuously for the required seconds.
- **Win (Energy well)** — own the target Energy rock and plant at least one tree there.
- **Lose** — no trees, no pending plants, and fewer than 10 seedlings left to plant.
