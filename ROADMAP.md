# Asterbloom — long-term plan

Original Eufloria-inspired browser strategy. The **sim loop is real**: grow trees, send seedlings, fight, burn undefended trees, plant, rival AI. Skirmish generator, 8 campaign maps, and win/lose rules live in `src/game/sim`. Phases **0–6** shell is wired (pause menu, mute persist, end copy, first-run, send dock, tab-hide pause, touch pan); `npm run build` is green. Phase **7** stretch is optional next.

Balance numbers live in `src/game/sim/types.ts`. Simulation stays Pixi-free. Views do not mutate `World`.

---

## Now

| Piece | State |
| --- | --- |
| Loop | Grow / send / fight / burn / plant — sim + ticker |
| Map | Skirmish 14–20 rocks + 8 authored campaign maps |
| AI | Energy / Defense / Dyson; Easy / Normal / Hard knobs |
| Session | Title + campaign list + pause menu + end overlay + tab-hide pause |
| HUD | Census, toasts, 1/2/3, send dock (Scout/−/count/+/All), first-run, follow-send |
| Capture | Burn-then-plant. `coreEnergy` unused (no siege-the-core) |
| Win rules | Eliminate, hold N rocks, claim Energy well — sim + tests |
| Audio | Procedural beds + combat / plant SFX. Mute persists (`writeMuted` / boot `readMuted`) |
| Ship | Version **0.1.0** in `package.json` / `prefs.ts`. **`npm run build` green**. Phase 6 shipped |
| Tests | Graph, combat, match rules, campaign, AI knobs, pacing, prefs, palette |

**Honest status.** Phases **0–3**, **5**, and **6** are in. Phase **4** human 8–20 min playtest is not attested. Phase **7** stretch is next when wanted.

---

## Finalize the shell — done

**Goal.** A cold `npm run build` + static host is a complete first session. Do not add features; connect what is already written.

Verified 2026-08-16: `tsc` / tests / build green after Phase 6 Finalize wiring (tab-hide, send dock, touch pan).

### 1. Make TypeScript compile

`package.json` script is `tsc && vite build`. **Green.**

| Error | Fix |
| --- | --- |
| `createTitleHud` requires `onMuteChange` and `onReducedMotionChange`; `main.ts` does not pass them | **Done.** Mute calls `audio.setEnabled` + `writeMuted`. Reduced motion: title writes pref + `applyReducedMotionClass`; boot applies `readReducedMotion()`. |
| `sessionHud.showEnd` is `(outcome, extra?)` but `main.ts` calls `showEnd({ outcome, mode, mapTitle, showNext, campaignComplete })` | **Done.** Object form + `endWinCopy` / `endLoseCopy` / `campaignCompleteCopy`. Campaign hides New map; shows Next / complete copy. |
| `main.ts` calls `graphView.retheme(scene)` — `GraphView` has no `retheme` | **Done** (retheme exists or call removed). |
| `tests/render/palette.test.ts` imports stale palette symbols | **Done** — tests use `sceneAtTime` / `buildScene` / `HUE_CYCLE_SECONDS`. |

### 2. Wire modules that already exist

| Piece | Where it lives | What `main.ts` / HUD actually do |
| --- | --- | --- |
| Pause **menu** | `src/game/hud/pauseHud.ts` — Resume, Restart, New map, Quit to title | **Done.** Esc/Space opens/closes pause menu; freezes ticker. |
| Title Settings | `titleHud.ts` mute + reduced motion | **Done.** Callbacks wired; boot applies `readMuted()` / `readReducedMotion()`. |
| End-screen copy | `copy.ts` `endWinCopy`, `endLoseCopy`, `campaignCompleteCopy` | **Done.** `sessionHud.showEnd` uses them. |
| First-run steps | `copy.ts` `FIRST_RUN_STEPS` («Tap…») + `tests/hud/copy.test.ts` | **Done.** Overlay renders `FIRST_RUN_STEPS`. |
| Send-count dock | CSS `.hud-send` / `.hud-dock`; helpers in `sendCount.ts`; `onSendCountChange` | **Done.** Scout / − / count / + / All in `sessionHud`; syncs `sendMode` / `sendCount`. |
| Field skip-title | `field.html` `data-boot="field"`; CSS hides title buttons | **Done.** `isFieldBoot()` starts a skirmish and skips title. |
| Touch pan / pinch abort | `cameraControls.ts` `shouldLeftPan`, `onMultiTouch`; `gameplay.shouldLeftPan` | **Done.** Empty-space one-finger pan + pinch-abort wired from `main`. |

### 3. Session behavior

- **Tab hide:** **Done.** `document.visibilitychange` calls `pauseMatch()` when hidden; does not auto-resume.
- **Mute persist:** **Done.** In-match toggle writes `writeMuted`; boot applies `readMuted()`.
- **Campaign end:** **Done** for end-overlay Next / complete copy / hide New map in campaign. Restart keeps campaign index / skirmish seed.

### 4. Done when

1. `npx tsc --noEmit` and `npm test` are green. **(done)**
2. `npm run build` writes `dist/`. **(done)**
3. Title → Play (any difficulty) → Esc pause **menu** → Resume / Restart / New map / Quit to title. **(wired)**
4. Title → Settings mute/motion stick across reload. **(wired)**
5. Win/lose overlay: Restart same seed; New map new seed (skirmish); campaign Next map / Title on last grove. **(wired)**
6. Hide tab → sim frozen; come back still paused. **(wired)**
7. Coarse pointer: tap select, drag send, on-screen 1/2/3 **and** send-count dock; empty-space drag pans. **(wired)**

Phase 6 is shipped. Pick Phase 7 leftovers only when wanted.

---

## Phase 0 — Keep the loop honest — done

**Goal.** Do not add campaign or juice until the existing 5-rock demo can be finished and restarted.

**Work**

- [x] Win: last enemy tree gone (or no enemy-owned rocks with trees). `matchStatus` — no enemy trees and no enemy pending plants.
- [x] Lose: player has no trees, no pending plants, and fewer than `PLANT_COST` seedlings.
- [x] End overlay: win/lose copy, **Restart** (same seed). **New map** landed in Phase 2.
- [x] Pause (`Esc` or space) — freeze sim ticker, keep camera. Pause **menu** wired (`pauseHud.ts`).
- [x] Mute toggle for ambient + SFX. Persist + boot apply via `prefs.ts`.
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
- [x] Optional: expose seed in HUD or URL hash for rematches. (`#s=<hex>` + HUD seed)
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
- [x] First-run overlay + `localStorage` dismiss. Copy uses `FIRST_RUN_STEPS`.

**Done when** a new player can take a wild rock and an enemy rock without reading the README.

---

## Phase 4 — Feel and pacing — numbers in; live playtest not re-verified

**Goal.** A match has an opening, a scramble, and a finish — not a flat production race.

**Work**

- [x] Constants + `tests/sim/pacing.test.ts`: spawn vs `LOCAL_SEEDLING_CAP`, Defense shield soak, `coreEnergy` unchanged during burn.
- [ ] Three full matches on different seeds in the 8–20 minute band (human playtest; not attested in-repo as of 2026-08-16 Phase 0–4 leftover pass).
- [x] Decide `coreEnergy`: leave dead until burn-then-plant feels wrong. Still unused.
- [x] Camera: optional follow-send (`F` / HUD); pan/zoom remain primary.

**Done when** three full matches on different seeds all end in a similar time band (target: 8–20 minutes) and the loser can say why.

---

## Phase 5 — Content beyond one skirmish — done

**Goal.** Replay is a mode, not the whole product.

**Work**

- [x] **Skirmish** — Phase 2 generator, difficulty. Second enemy faction not added (optional; `FactionId` has room — do not add factions the AI cannot run).
- [x] **Campaign** — 8 authored maps in `campaign.ts`. Win rules: eliminate, hold N rocks, claim Energy well. Original copy only.
- [x] Per-map scripts live beside `layout.ts` (data + `create*World` factories), not in the renderer.
- [x] List of maps (no unlock gate). Last index in `localStorage` (`CAMPAIGN_INDEX_KEY`).
- [x] Title → campaign → finish last map with Next / complete overlay (`showEnd` object API).

**Done when** you can play Skirmish or start Campaign from a title screen and finish the last authored map.

---

## Phase 6 — Shell and ship — done

**Goal.** It boots like software people can send a link to.

**Work**

- [x] Title: Play / Campaign / Settings **wired** to audio + reduced motion (UI exists in `titleHud.ts`).
- [x] In-match: pause **menu** (resume, restart, new map, quit to title). `pauseHud.ts` wired from `main.ts`.
- [x] Build: `npm run build` green. Version **0.1.0** is the ship version.
- [x] Browser: **pause when the tab hides** (no auto-resume). Multi-resolution Chromium/Firefox smoke is manual, not automated.
- [x] Input: mouse/keyboard canonical. Touch empty-space pan + pinch-abort + send dock wired (see Finalize).
- [x] README: how a match is won/lost; points at this file. Send dock / tab-hide / touch pan claims match the code.
- [x] Legal/identity: original art, names, audio. No ripped assets or trademarks.

**Done when** a cold `npm run build` + static host is a complete first session with no console instructions required.

---

## Phase 7 — Stretch (only after Finalize + Phase 6)

Do not start leftover stretch to avoid finishing a match.

- [ ] Touch: tap select, drag send, on-screen 1/2/3 **and** send-count. Dock + empty-space pan + pinch-abort are wired via Finalize; leave open for further touch polish if playtests ask.
- [ ] Minimap for 25+ rock maps.
- [x] Music: original procedural beds in `audio.ts` (several pieces, drone + sparse lead). No ripped tracks. Leave this checked; do not replace unless a playtest asks.
- [ ] Extra seedling/tree kinds — only if Phase 4 pacing is bored, not for a feature list.
- [ ] Save/resume a mid-match `World` (serialize Maps). Campaign index is cheaper and already stored.
- [ ] Spectator / replay seed + command log.
- [ ] Accessibility: colorblind faction marks, scalable HUD, screen-flash off. Reduced-motion pref exists and is applied on boot; does not yet gate combat flash.

---

## Principles (every phase)

1. **Sim first.** Win/lose, AI, and layout are `src/game/sim`. Pixi only shows them.
2. **Commands stay the AI’s hands.** `tickAi` calls `plantTree` / `sendSeedlings`; it does not special-case combat.
3. **Tests follow the domain.** New match rules, AI policy, and generators get specs under `tests/sim/`.
4. **One loop.** Campaign maps are layouts + win conditions, not new verbs.
5. **No new dependencies** unless we explicitly decide (stack: TypeScript, Vite, Pixi v8, Vitest).
6. **Wire before rewrite.** Pause, title settings, send-count, and copy helpers are already in tree. Connect them.

---

## Suggested order of attack

```
[x] 1  AI uses Energy + Defense
[x] 2  generated map + new-map seed
[x] 0  session shell (pause menu + mute persist + end copy)
[x] 3  HUD/juice + first-run FIRST_RUN_STEPS
[~] 4  constants/tests in; 8–20 min playtest not attested
[x] 5  campaign maps + end-screen Next/complete
[x] 6  ship shell (tab-hide + send dock + touch pan)
[ ] 7  stretch when wanted (minimap, a11y, save/resume, …)
```

Next agent: optional Phase 4 playtest attestation, or pick a Phase 7 stretch item.
