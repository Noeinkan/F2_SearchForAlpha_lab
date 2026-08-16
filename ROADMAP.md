# Asterbloom — long-term plan

Original Eufloria-inspired browser strategy. The **core loop already runs**: grow trees, send seedlings, fight in real time, burn undefended trees, plant, and a hostile empire that raids. What is missing is a **session** (start → play → win/lose → replay), then enough map, opponent, and feedback that a run feels like a game.

Balance numbers live in `src/game/sim/types.ts`. Simulation stays Pixi-free. Views do not mutate `World`.

---

## Now

| Piece | State |
| --- | --- |
| Loop | Grow / send / fight / burn / plant |
| Map | Skirmish generator + 8 authored campaign maps |
| AI | Energy / Defense / Dyson; Easy / Normal / Hard knobs |
| Session | Title Play / Campaign / Settings; pause menu; tab-hide pause |
| HUD | Title shell, pause overlay, census, toasts, first-run, mute, follow-send |
| Capture | Burn-then-plant. `coreEnergy` unused (no siege-the-core) |
| Win rules | Eliminate, hold N rocks, claim Energy well |
| Audio | Ambient pad + combat / plant blips; mute persisted |
| Ship | `npm run build` → `dist/`; version **0.1.0** |
| Tests | Graph, combat, match rules, campaign, AI knobs, pacing, prefs |

Phases **0–6** are implemented (ship **0.1.0**). **Phase 7** touch is done; other stretch items remain.

---

## Phase 0 — Keep the loop honest — done

**Goal.** Do not add campaign or juice until the existing 5-rock demo can be finished and restarted.

**Work**

- [x] Win: last enemy tree gone (or no enemy-owned rocks with trees).
- [x] Lose: player has no trees and not enough seedlings left to plant anywhere.
- [x] End overlay: win/lose copy, **Restart** (same seed), **New map** can wait until Phase 2.
- [x] Pause (`Esc` or space) — freeze sim ticker, keep camera.
- [x] Mute toggle for ambient + SFX.
- [x] Sim function `matchStatus(world)` so tests assert outcomes, not HUD.

**Done when** you can wipe the enemy rock, see a win, restart, and lose by sending everything away and letting the AI take home.

**Out of scope.** New seedling types, story, save files, `coreEnergy`.

---

## Phase 1 — Opponent that uses the same rules — done

**Goal.** The enemy empire is a rival, not a raid timer.

**Work**

- [x] Plant Energy trees on high-Energy rocks; Defense on borders.
- [x] Keep a garrison; reinforce threatened rocks; retake lost home.
- [x] Prefer Sentinels on raids; do not starve them by over-planting Energy.
- [x] Difficulty knobs (think interval, garrison, raid size) in `types.ts`.
- [x] Tests: AI plants non-Dyson when eligible; does not strip a rock below garrison.

**Done when** a patient player can still win, but leaving home empty loses it.

---

## Phase 2 — A map worth a match — done

**Goal.** One generated (or seeded) layout is the default session, not the 5-rock test bed.

**Work**

- [x] Generator in `layout.ts`: ~12–25 rocks, connected travel graph, choke points. (skirmish uses ~14–20)
- [x] Roles mixed by seed: empty, wild (grey), energy wells, 1–2 enemy clusters.
- [x] Home at a leaf or edge, not the geometric center every time.
- [x] **New map** on the end screen (new seed). **Restart** keeps the seed.
- [x] Optional: expose seed in HUD or URL hash for rematches.
- [x] Keep `createCoreLoopWorld` as a unit-test fixture.

**Done when** two seeds feel like different wars (stats, chokes, where the Energy well sits).

**Later in this phase if matches drag.** Minimap / galaxy dots. Not required at 12 rocks. (still open — see Phase 7)

---

## Phase 3 — Speak like a game — done

**Goal.** Failed actions and fights are readable without opening the debugger.

**Work**

- [x] HUD: You / Wild / Enemy — never `grey` or `neutral` in player copy.
- [x] Selected rock: seedlings, minerals, energy pool, shield, tree slots, why 2/3 are locked.
- [x] Toast or HUD line for `CommandResult.reason` (need 10, contested, no path, not energy-rich).
- [x] Tree-kind selection visible (1/2/3), not only a keyboard secret.
- [x] Combat/capture juice (render only): hit flash, death motes, shield shimmer, trees darkening while `burnTimer` runs.
- [x] SFX: clash, death, burn, fail plant — still procedural Web Audio, no asset pack unless we decide otherwise.
- [x] First-run: one short overlay (select → drag send → plant slot). Dismiss forever (`localStorage` is enough).

**Done when** a new player can take a wild rock and an enemy rock without reading the README.

---

## Phase 4 — Feel and pacing — done

**Goal.** A match has an opening, a scramble, and a finish — not a flat production race.

**Work**

- [x] Playtest pass on `types.ts`: spawn rates, `LOCAL_SEEDLING_CAP`, burn time, Sentinel upkeep, shield soak.
- [x] Opening: home produces enough to scout before the AI snowballs.
- [x] Mid: Energy wells and Defense chokes matter more than stacking Dyson everywhere.
- [x] Late: capturing the last cluster is a fight, not mopping 40 leftovers.
- [x] Decide whether unused `coreEnergy` stays dead or becomes a second capture beat (siege the core instead of only burning trees). Default: leave it until burn-then-plant feels wrong. (`coreEnergy` still unused.)
- [x] Camera: optional follow-send; keep pan/zoom as primary.

**Done when** three full matches on different seeds all end in a similar time band (target: 8–20 minutes) and the loser can say why.

---

## Phase 5 — Content beyond one skirmish — done

**Goal.** Replay is a mode, not the whole product.

**Work**

- [x] **Skirmish** — Phase 2 generator, difficulty, optional second enemy hue/faction if the sim stays clean (`FactionId` already has room; do not add factions that AI cannot run). (second enemy faction not added — optional.)
- [x] **Campaign** — short authored sequence (6–10 maps). Each map is a layout + win rule (eliminate, hold N rocks, reach a far Energy well). Original copy only; no Eufloria names or plot. (8 maps.)
- [x] Per-map scripts live beside `layout.ts` (data + `create*World` factories), not in the renderer.
- [x] Unlock or just a list — list is enough for v1.
- [x] Still no account, cloud save, or meta-progression required. Optional: remember last campaign index in `localStorage`.

**Done when** you can play Skirmish or start Campaign from a title screen and finish the last authored map.

---

## Phase 6 — Shell and ship — done

**Goal.** It boots like software people can send a link to.

**Work**

- [x] Title: Play / Campaign / Settings (mute, maybe reduced motion).
- [x] In-match: pause menu (resume, restart, new map, quit to title).
- [x] Build: `npm run build` is the ship artifact. Set a real version when tagging. (version **0.1.0**)
- [x] Browser: Chromium + Firefox at 1280×720 and 1920×1080; pause when the tab hides.
- [x] Input: keep mouse/keyboard as canonical. Touch later (Phase 7) unless a playtester cannot play at all.
- [x] README: how a match is won/lost; point at this file for the plan.
- [x] Legal/identity: keep original art, names, audio. No ripped assets or trademarks.

**Done when** a cold `npm run build` + static host is a complete first session with no console instructions required.

---

## Phase 7 — Stretch (only after 0–6) — in progress

Do not start these to avoid finishing a match.

- [x] Touch: tap select, drag send, on-screen 1/2/3 and send-count.
- [ ] Minimap for 25+ rock maps.
- [ ] Music: original procedural or commissioned bed; still no ripped tracks.
- [ ] Extra seedling/tree kinds — only if Phase 4 pacing is bored, not for a feature list.
- [ ] Save/resume a mid-match `World` (serialize Maps). Campaign index is cheaper and should come first.
- [ ] Spectator / replay seed + command log.
- [ ] Accessibility: colorblind faction marks, scalable HUD, screen-flash off.

---

## Principles (every phase)

1. **Sim first.** Win/lose, AI, and layout are `src/game/sim`. Pixi only shows them.
2. **Commands stay the AI’s hands.** `tickAi` calls `plantTree` / `sendSeedlings`; it does not special-case combat.
3. **Tests follow the domain.** New match rules, AI policy, and generators get specs under `tests/sim/`.
4. **One loop.** Campaign maps are layouts + win conditions, not new verbs.
5. **No new dependencies** unless we explicitly decide (stack: TypeScript, Vite, Pixi v8, Vitest).

---

## Suggested order of attack

```
[x] 0  session (win/lose/restart/pause)
[x] 1  AI uses Energy + Defense
[x] 2  generated map + new-map seed
[x] 3  HUD, toasts, combat juice, first-run
[x] 4  balance / pacing pass
[x] 5  title + skirmish + short campaign
[x] 6  ship shell
[~] 7  stretch (touch done; rest open)
```

Phases 0–6 shipped in **0.1.0**. Phase 7 touch controls shipped; other stretch items remain.
