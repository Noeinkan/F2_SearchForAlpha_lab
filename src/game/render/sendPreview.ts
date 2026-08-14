import { Container, Graphics, Text } from 'pixi.js';
import type { ScenePalette } from './palette';

export class SendPreview {
  readonly root = new Container();
  private line = new Graphics();
  private label: Text;
  private scene: ScenePalette;

  constructor(scene: ScenePalette) {
    this.scene = scene;
    this.root.eventMode = 'none';
    this.root.visible = false;
    this.root.addChild(this.line);
    this.label = new Text({
      text: '',
      style: {
        fontFamily: 'Georgia, serif',
        fontSize: 15,
        fill: scene.ink,
        fontStyle: 'italic',
      },
    });
    this.label.anchor.set(0.5);
    this.root.addChild(this.label);
  }

  hide(): void {
    this.root.visible = false;
  }

  show(
    fromX: number,
    fromY: number,
    toX: number,
    toY: number,
    count: number,
    valid: boolean,
  ): void {
    this.root.visible = true;
    this.line.clear();
    const mx = (fromX + toX) / 2;
    const my = (fromY + toY) / 2;
    const dx = toX - fromX;
    const dy = toY - fromY;
    const len = Math.hypot(dx, dy) || 1;
    const cx = mx - (dy / len) * 28;
    const cy = my + (dx / len) * 28;

    this.line.moveTo(fromX, fromY);
    this.line.quadraticCurveTo(cx, cy, toX, toY);
    this.line.stroke({
      width: valid ? 1.8 : 1.2,
      color: valid ? this.scene.ink : this.scene.inkSoft,
      alpha: valid ? 0.7 : 0.28,
      cap: 'round',
    });
    this.line.circle(toX, toY, valid ? 5 : 3);
    this.line.fill({
      color: valid ? this.scene.ink : this.scene.inkSoft,
      alpha: valid ? 0.55 : 0.22,
    });

    this.label.text = String(count);
    this.label.position.set(cx, cy - 12);
    this.label.style.fill = valid ? this.scene.ink : this.scene.inkSoft;
    this.label.alpha = valid ? 0.95 : 0.4;
  }
}
