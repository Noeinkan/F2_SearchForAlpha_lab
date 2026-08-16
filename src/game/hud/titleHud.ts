import {
  CAMPAIGN_MAPS,
  readCampaignIndex,
} from '../sim/campaign';
import type { Difficulty } from '../sim/types';
import { difficultyLabel } from './copy';
import {
  applyReducedMotionClass,
  GAME_VERSION,
  readMuted,
  readReducedMotion,
  writeMuted,
  writeReducedMotion,
} from './prefs';

export interface TitleHud {
  root: HTMLDivElement;
  show(): void;
  hide(): void;
  isVisible(): boolean;
  destroy(): void;
}

type TitleView = 'home' | 'skirmish' | 'campaign' | 'settings';

export function createTitleHud(opts: {
  host: HTMLElement;
  onSkirmish: (difficulty: Difficulty) => void;
  onCampaign: (index: number) => void;
  onMuteChange: (muted: boolean) => void;
  onReducedMotionChange: (enabled: boolean) => void;
}): TitleHud {
  const root = document.createElement('div');
  root.className = 'end-overlay title-overlay';
  root.hidden = true;
  opts.host.appendChild(root);

  let view: TitleView = 'home';
  let muted = readMuted();
  let reducedMotion = readReducedMotion();

  const render = () => {
    if (view === 'home') {
      root.innerHTML = `
        <div class="end-card title-card">
          <p class="title-brand">Asterbloom</p>
          <p class="title-tag">Grow. Send. Claim the dark.</p>
          <div class="end-actions title-actions">
            <button type="button" data-nav="skirmish">Play</button>
            <button type="button" data-nav="campaign">Campaign</button>
            <button type="button" data-nav="settings">Settings</button>
          </div>
          <p class="title-version">v${GAME_VERSION}</p>
        </div>
      `;
    } else if (view === 'skirmish') {
      root.innerHTML = `
        <div class="end-card title-card">
          <p class="first-run-title">Skirmish</p>
          <p class="title-tag">A seeded war. Pick how hard the rival presses.</p>
          <div class="end-actions title-actions">
            <button type="button" data-diff="easy">${difficultyLabel('easy')}</button>
            <button type="button" data-diff="normal">${difficultyLabel('normal')}</button>
            <button type="button" data-diff="hard">${difficultyLabel('hard')}</button>
          </div>
          <div class="end-actions title-actions title-back-row">
            <button type="button" data-nav="home">Back</button>
          </div>
        </div>
      `;
    } else if (view === 'campaign') {
      const last = readCampaignIndex();
      const items = CAMPAIGN_MAPS.map((m, i) => {
        const mark = i === last ? ' is-last' : '';
        return `<button type="button" class="title-map${mark}" data-map="${i}">
          <span class="title-map-n">${i + 1}</span>
          <span class="title-map-body">
            <strong>${m.title}</strong>
            <span>${m.blurb}</span>
          </span>
        </button>`;
      }).join('');
      root.innerHTML = `
        <div class="end-card title-card title-card-wide">
          <p class="first-run-title">Campaign</p>
          <p class="title-tag">Eight authored groves. Pick any map.</p>
          <div class="title-map-list">${items}</div>
          <div class="end-actions title-actions title-back-row">
            <button type="button" data-nav="home">Back</button>
          </div>
        </div>
      `;
    } else {
      root.innerHTML = `
        <div class="end-card title-card">
          <p class="first-run-title">Settings</p>
          <div class="title-settings">
            <button type="button" class="hud-mute" data-pref="mute">
              ${muted ? 'Muted' : 'Sound on'}
            </button>
            <button type="button" class="hud-mute" data-pref="motion">
              ${reducedMotion ? 'Reduced motion on' : 'Reduced motion off'}
            </button>
          </div>
          <p class="title-version">v${GAME_VERSION}</p>
          <div class="end-actions title-actions title-back-row">
            <button type="button" data-nav="home">Back</button>
          </div>
        </div>
      `;
    }

    root.querySelectorAll<HTMLButtonElement>('[data-nav]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const nav = btn.dataset.nav;
        if (nav === 'skirmish') view = 'skirmish';
        else if (nav === 'campaign') view = 'campaign';
        else if (nav === 'settings') view = 'settings';
        else view = 'home';
        render();
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-diff]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const d = btn.dataset.diff as Difficulty;
        opts.onSkirmish(d);
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-map]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const i = Number.parseInt(btn.dataset.map ?? '0', 10);
        opts.onCampaign(i);
      });
    });
    root.querySelectorAll<HTMLButtonElement>('[data-pref]').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (btn.dataset.pref === 'mute') {
          muted = !muted;
          writeMuted(muted);
          opts.onMuteChange(muted);
        } else if (btn.dataset.pref === 'motion') {
          reducedMotion = !reducedMotion;
          writeReducedMotion(reducedMotion);
          applyReducedMotionClass(reducedMotion);
          opts.onReducedMotionChange(reducedMotion);
        }
        render();
      });
    });
  };

  render();

  return {
    root,
    show() {
      view = 'home';
      muted = readMuted();
      reducedMotion = readReducedMotion();
      render();
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
