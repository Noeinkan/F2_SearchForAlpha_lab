import { CONTROLS_HINT } from './copy';

export interface PauseHud {
  root: HTMLDivElement;
  show(opts: { showNewMap: boolean }): void;
  hide(): void;
  isVisible(): boolean;
  setSeed(hex: string): void;
  setMuted(muted: boolean): void;
  setFollowSend(enabled: boolean): void;
  destroy(): void;
}

export function createPauseHud(opts: {
  host: HTMLElement;
  onResume: () => void;
  onRestart: () => void;
  onNewMap: () => void;
  onTitle: () => void;
  onMuteToggle: () => void;
  onFollowToggle: () => void;
}): PauseHud {
  const root = document.createElement('div');
  root.className = 'end-overlay pause-overlay';
  root.hidden = true;
  root.innerHTML = `
    <div class="end-card">
      <p class="first-run-title">Paused</p>
      <p id="pause-seed" class="pause-seed"></p>
      <div class="pause-settings">
        <button type="button" class="hud-mute" id="pause-mute" aria-label="Mute">Sound on</button>
        <button type="button" class="hud-mute" id="pause-follow" aria-label="Follow send">Follow off</button>
      </div>
      <div class="end-actions">
        <button type="button" id="pause-resume">Resume</button>
        <button type="button" id="pause-restart">Restart</button>
        <button type="button" id="pause-newmap">New map</button>
        <button type="button" id="pause-title">Quit to title</button>
      </div>
      <p class="pause-hint">${CONTROLS_HINT}</p>
    </div>
  `;
  opts.host.appendChild(root);

  const seedEl = root.querySelector('#pause-seed')!;
  const muteBtn = root.querySelector<HTMLButtonElement>('#pause-mute')!;
  const followBtn = root.querySelector<HTMLButtonElement>('#pause-follow')!;
  const resume = root.querySelector<HTMLButtonElement>('#pause-resume')!;
  const restart = root.querySelector<HTMLButtonElement>('#pause-restart')!;
  const newMap = root.querySelector<HTMLButtonElement>('#pause-newmap')!;
  const title = root.querySelector<HTMLButtonElement>('#pause-title')!;

  resume.addEventListener('click', () => opts.onResume());
  restart.addEventListener('click', () => opts.onRestart());
  newMap.addEventListener('click', () => opts.onNewMap());
  title.addEventListener('click', () => opts.onTitle());
  muteBtn.addEventListener('click', () => opts.onMuteToggle());
  followBtn.addEventListener('click', () => opts.onFollowToggle());

  return {
    root,
    show({ showNewMap }) {
      newMap.hidden = !showNewMap;
      root.hidden = false;
    },
    hide() {
      root.hidden = true;
    },
    isVisible() {
      return !root.hidden;
    },
    setSeed(hex: string) {
      seedEl.textContent = `seed ${hex}`;
    },
    setMuted(muted: boolean) {
      muteBtn.textContent = muted ? 'Muted' : 'Sound on';
    },
    setFollowSend(enabled: boolean) {
      followBtn.textContent = enabled ? 'Follow on' : 'Follow off';
    },
    destroy() {
      root.remove();
    },
  };
}
