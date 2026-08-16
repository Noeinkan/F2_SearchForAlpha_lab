import type { CommandResult } from '../sim/commands';
import { canPlantKind, type TreeKind, type World } from '../sim/types';
import { getOccupiedSlots } from '../sim/world';
import {
  commandReasonCopy,
  CONTROLS_HINT,
  factionLabel,
  FIRST_RUN_STORAGE_KEY,
  plantKindLabel,
  treeKindLockReason,
} from './copy';

const TOAST_MS = 2500;

export interface SessionHud {
  root: HTMLDivElement;
  endOverlay: HTMLDivElement;
  firstRunOverlay: HTMLDivElement;
  setMuted(muted: boolean): void;
  setFollowSend(enabled: boolean): void;
  setPaused(paused: boolean): void;
  setSeed(hex: string): void;
  setVisible(visible: boolean): void;
  showEnd(
    outcome: 'won' | 'lost',
    extra?: { nextMap?: boolean; newMap?: boolean },
  ): void;
  hideEnd(): void;
  /** Returns true if first-run was shown (sim should stay paused). */
  maybeShowFirstRun(): boolean;
  dismissFirstRun(): void;
  isFirstRunVisible(): boolean;
  showCommandResult(result: CommandResult): void;
  setPlantKind(kind: TreeKind): void;
  sync(
    world: World,
    selectedId: number | null,
    local: number,
    sentinels: number,
    plantKind: TreeKind,
    dragging: boolean,
    sendCount: number,
  ): void;
  destroy(): void;
}

export function createSessionHud(opts: {
  host: HTMLElement;
  onMuteToggle: () => void;
  onFollowToggle: () => void;
  onRestart: () => void;
  onNewMap: () => void;
  onNextMap?: () => void;
  onTitle?: () => void;
  onPlantKind: (kind: TreeKind) => void;
  onFirstRunDismiss: () => void;
}): SessionHud {
  const hud = document.createElement('div');
  hud.className = 'hud';
  hud.innerHTML = `
    <div class="hud-top">
      <strong>Asterbloom</strong>
      <span id="hud-seed" class="hud-seed"></span>
      <button type="button" class="hud-mute" id="hud-mute" aria-label="Mute">Sound on</button>
      <button type="button" class="hud-mute" id="hud-follow" aria-label="Follow send">Follow off</button>
    </div>
    <div id="hud-census" class="hud-census"></div>
    <div id="hud-stats" class="hud-stats">…</div>
    <div class="hud-kinds" id="hud-kinds" role="group" aria-label="Tree kind">
      <button type="button" class="hud-kind" data-kind="dyson" title="Dyson tree">1 Dyson</button>
      <button type="button" class="hud-kind" data-kind="energy" title="Energy tree">2 Energy</button>
      <button type="button" class="hud-kind" data-kind="defense" title="Defense tree">3 Defense</button>
    </div>
    <div id="hud-pause" class="hud-pause" hidden>Paused</div>
    <div id="hud-hint" class="hint">${CONTROLS_HINT}</div>
  `;
  opts.host.appendChild(hud);

  const endOverlay = document.createElement('div');
  endOverlay.className = 'end-overlay';
  endOverlay.hidden = true;
  endOverlay.innerHTML = `
    <div class="end-card">
      <p id="end-copy"></p>
      <div class="end-actions">
        <button type="button" id="end-restart">Restart</button>
        <button type="button" id="end-newmap">New map</button>
        <button type="button" id="end-next" hidden>Next map</button>
        <button type="button" id="end-title" hidden>Title</button>
      </div>
    </div>
  `;
  opts.host.appendChild(endOverlay);

  const firstRunOverlay = document.createElement('div');
  firstRunOverlay.className = 'end-overlay first-run-overlay';
  firstRunOverlay.hidden = true;
  firstRunOverlay.innerHTML = `
    <div class="end-card">
      <p class="first-run-title">How to play</p>
      <ol class="first-run-steps">
        <li>Select a rock</li>
        <li>Drag to send seedlings</li>
        <li>Click a glowing slot to plant (10)</li>
      </ol>
      <div class="end-actions">
        <button type="button" id="first-run-got-it">Got it</button>
      </div>
    </div>
  `;
  opts.host.appendChild(firstRunOverlay);

  const hudSeed = hud.querySelector('#hud-seed')!;
  const hudCensus = hud.querySelector('#hud-census')!;
  const hudStats = hud.querySelector('#hud-stats')!;
  const hudPause = hud.querySelector<HTMLDivElement>('#hud-pause')!;
  const hudHint = hud.querySelector('#hud-hint')!;
  const muteBtn = hud.querySelector<HTMLButtonElement>('#hud-mute')!;
  const followBtn = hud.querySelector<HTMLButtonElement>('#hud-follow')!;
  const kindBtns = [
    ...hud.querySelectorAll<HTMLButtonElement>('.hud-kind'),
  ];
  const endCopy = endOverlay.querySelector('#end-copy')!;
  const endRestart = endOverlay.querySelector<HTMLButtonElement>('#end-restart')!;
  const endNewMap = endOverlay.querySelector<HTMLButtonElement>('#end-newmap')!;
  const endNext = endOverlay.querySelector<HTMLButtonElement>('#end-next')!;
  const endTitle = endOverlay.querySelector<HTMLButtonElement>('#end-title')!;
  const gotIt = firstRunOverlay.querySelector<HTMLButtonElement>('#first-run-got-it')!;

  let toastTimer: number | null = null;
  let plantKind: TreeKind = 'dyson';
  let lockEnergy: number | null = null;

  const refreshKindButtons = () => {
    for (const btn of kindBtns) {
      const kind = btn.dataset.kind as TreeKind;
      const selected = kind === plantKind;
      btn.classList.toggle('is-selected', selected);
      const locked =
        lockEnergy !== null && !canPlantKind(lockEnergy, kind);
      btn.classList.toggle('is-locked', locked);
      const lock = lockEnergy !== null ? treeKindLockReason(lockEnergy, kind) : null;
      btn.title = lock ?? `${plantKindLabel(kind)} tree`;
    }
  };

  muteBtn.addEventListener('click', () => opts.onMuteToggle());
  followBtn.addEventListener('click', () => opts.onFollowToggle());
  endRestart.addEventListener('click', () => opts.onRestart());
  endNewMap.addEventListener('click', () => opts.onNewMap());
  endNext.addEventListener('click', () => opts.onNextMap?.());
  endTitle.addEventListener('click', () => opts.onTitle?.());
  gotIt.addEventListener('click', () => {
    try {
      localStorage.setItem(FIRST_RUN_STORAGE_KEY, '1');
    } catch {
      /* ignore quota / private mode */
    }
    firstRunOverlay.hidden = true;
    opts.onFirstRunDismiss();
  });

  for (const btn of kindBtns) {
    btn.addEventListener('click', () => {
      const kind = btn.dataset.kind as TreeKind;
      plantKind = kind;
      refreshKindButtons();
      opts.onPlantKind(kind);
    });
  }

  const api: SessionHud = {
    root: hud,
    endOverlay,
    firstRunOverlay,

    setMuted(muted: boolean) {
      muteBtn.textContent = muted ? 'Muted' : 'Sound on';
    },

    setFollowSend(enabled: boolean) {
      followBtn.textContent = enabled ? 'Follow on' : 'Follow off';
    },

    setPaused(paused: boolean) {
      hudPause.hidden = !paused;
    },

    setSeed(hex: string) {
      hudSeed.textContent = `seed ${hex}`;
    },

    setVisible(visible: boolean) {
      hud.hidden = !visible;
      if (!visible) endOverlay.hidden = true;
    },

    showEnd(
      outcome: 'won' | 'lost',
      extra?: { nextMap?: boolean; newMap?: boolean },
    ) {
      endCopy.textContent =
        outcome === 'won'
          ? 'The grove is yours. The last hostile trees have fallen.'
          : 'The grove is gone. Too few seedlings remain to plant again.';
      endNewMap.hidden = extra?.newMap === false;
      endNext.hidden = extra?.nextMap !== true;
      endTitle.hidden = false;
      endOverlay.hidden = false;
    },

    hideEnd() {
      endOverlay.hidden = true;
    },

    maybeShowFirstRun() {
      let seen = false;
      try {
        seen = localStorage.getItem(FIRST_RUN_STORAGE_KEY) === '1';
      } catch {
        seen = false;
      }
      if (seen) {
        firstRunOverlay.hidden = true;
        return false;
      }
      firstRunOverlay.hidden = false;
      return true;
    },

    dismissFirstRun() {
      firstRunOverlay.hidden = true;
    },

    isFirstRunVisible() {
      return !firstRunOverlay.hidden;
    },

    showCommandResult(result: CommandResult) {
      if (result.ok) return;
      const line = commandReasonCopy(result.reason);
      hudHint.textContent = line;
      hudHint.classList.add('is-toast');
      if (toastTimer !== null) window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => {
        toastTimer = null;
        hudHint.textContent = CONTROLS_HINT;
        hudHint.classList.remove('is-toast');
      }, TOAST_MS);
    },

    setPlantKind(kind: TreeKind) {
      plantKind = kind;
      refreshKindButtons();
    },

    sync(
      world,
      selectedId,
      local,
      sentinels,
      kind,
      dragging,
      sendCount,
    ) {
      plantKind = kind;
      const counts = census(world);
      hudCensus.textContent = `You ${counts.player} · Wild ${counts.grey} · Enemy ${counts.enemy}`;

      const sel = selectedId !== null ? world.asteroids.get(selectedId) : undefined;
      lockEnergy = sel ? sel.stats.energy : null;
      refreshKindButtons();

      if (!sel) {
        hudStats.textContent = `trees ${world.trees.size}`;
        return;
      }

      const occupied = getOccupiedSlots(world, sel.id).size;
      const owner = factionLabel(sel.owner);
      const parts = [
        `${sel.name} · ${owner}`,
        `${local} seedlings (${sentinels} sentinel)`,
        `Minerals ${Math.round(sel.minerals)}`,
        `Energy ${Math.round(sel.energyPool)}/${Math.round(sel.maxEnergyPool)}`,
      ];
      if (sel.maxShield > 0) {
        parts.push(`Shield ${Math.round(sel.shield)}`);
      }
      parts.push(`Trees ${occupied}/${sel.treeSlots}`);

      const lockForKind = treeKindLockReason(sel.stats.energy, kind);
      if (lockForKind) parts.push(lockForKind);
      else {
        const energyLock = treeKindLockReason(sel.stats.energy, 'energy');
        const defenseLock = treeKindLockReason(sel.stats.energy, 'defense');
        if (energyLock && defenseLock) {
          parts.push(
            `2 & 3 locked — rock Energy ${Math.round(sel.stats.energy)}`,
          );
        } else if (energyLock) {
          parts.push(energyLock);
        } else if (defenseLock) {
          parts.push(defenseLock);
        }
      }

      if (dragging) parts.push(`sending ${sendCount}`);
      else parts.push(`plant ${plantKindLabel(kind)}`);

      hudStats.textContent = parts.join(' · ');
    },

    destroy() {
      if (toastTimer !== null) window.clearTimeout(toastTimer);
      hud.remove();
      endOverlay.remove();
      firstRunOverlay.remove();
    },
  };

  refreshKindButtons();
  return api;
}

function census(world: World): Record<'player' | 'grey' | 'enemy', number> {
  const out = { player: 0, grey: 0, enemy: 0 };
  for (const a of world.asteroids.values()) {
    if (a.owner === 'player' || a.owner === 'grey' || a.owner === 'enemy') {
      out[a.owner] += 1;
    }
  }
  return out;
}
