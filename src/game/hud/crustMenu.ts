export interface CrustMenu {
  show(opts: {
    screenX: number;
    screenY: number;
    ask: string;
    plantLabel: string;
    onPlant: () => void;
  }): void;
  hide(): void;
  isVisible(): boolean;
  destroy(): void;
}

export function createCrustMenu(host: HTMLElement): CrustMenu {
  const root = document.createElement('div');
  root.className = 'crust-menu';
  root.hidden = true;
  root.setAttribute('role', 'menu');
  root.innerHTML = `
    <p class="crust-menu-ask"></p>
    <button type="button" role="menuitem"></button>
  `;
  host.appendChild(root);

  const askEl = root.querySelector<HTMLParagraphElement>('.crust-menu-ask')!;
  const plantBtn = root.querySelector<HTMLButtonElement>('button')!;

  let onPlant: (() => void) | null = null;
  let armed = false;

  const hide = () => {
    root.hidden = true;
    onPlant = null;
    armed = false;
  };

  const onDocPointer = (e: PointerEvent) => {
    if (root.hidden) return;
    if (root.contains(e.target as Node)) return;
    hide();
  };

  plantBtn.addEventListener('click', () => {
    if (!armed) return;
    const act = onPlant;
    hide();
    act?.();
  });

  document.addEventListener('pointerdown', onDocPointer);

  return {
    show({ screenX, screenY, ask, plantLabel, onPlant: next }) {
      askEl.textContent = ask;
      plantBtn.textContent = plantLabel;
      onPlant = next;
      armed = false;
      root.hidden = false;

      const pad = 10;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      root.style.left = `${screenX + 12}px`;
      root.style.top = `${screenY + 8}px`;
      const rect = root.getBoundingClientRect();
      let left = screenX + 12;
      let top = screenY + 8;
      if (left + rect.width > vw - pad) left = Math.max(pad, screenX - rect.width - 12);
      if (top + rect.height > vh - pad) top = Math.max(pad, screenY - rect.height - 8);
      root.style.left = `${left}px`;
      root.style.top = `${top}px`;

      window.setTimeout(() => {
        if (!root.hidden) armed = true;
      }, 180);
    },
    hide,
    isVisible() {
      return !root.hidden;
    },
    destroy() {
      document.removeEventListener('pointerdown', onDocPointer);
      root.remove();
    },
  };
}
