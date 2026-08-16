export interface PauseHud {
  root: HTMLDivElement;
  show(opts: { showNewMap: boolean }): void;
  hide(): void;
  isVisible(): boolean;
  destroy(): void;
}

export function createPauseHud(opts: {
  host: HTMLElement;
  onResume: () => void;
  onRestart: () => void;
  onNewMap: () => void;
  onTitle: () => void;
}): PauseHud {
  const root = document.createElement('div');
  root.className = 'end-overlay pause-overlay';
  root.hidden = true;
  root.innerHTML = `
    <div class="end-card">
      <p class="first-run-title">Paused</p>
      <div class="end-actions">
        <button type="button" id="pause-resume">Resume</button>
        <button type="button" id="pause-restart">Restart</button>
        <button type="button" id="pause-newmap">New map</button>
        <button type="button" id="pause-title">Quit to title</button>
      </div>
    </div>
  `;
  opts.host.appendChild(root);

  const resume = root.querySelector<HTMLButtonElement>('#pause-resume')!;
  const restart = root.querySelector<HTMLButtonElement>('#pause-restart')!;
  const newMap = root.querySelector<HTMLButtonElement>('#pause-newmap')!;
  const title = root.querySelector<HTMLButtonElement>('#pause-title')!;

  resume.addEventListener('click', () => opts.onResume());
  restart.addEventListener('click', () => opts.onRestart());
  newMap.addEventListener('click', () => opts.onNewMap());
  title.addEventListener('click', () => opts.onTitle());

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
    destroy() {
      root.remove();
    },
  };
}
