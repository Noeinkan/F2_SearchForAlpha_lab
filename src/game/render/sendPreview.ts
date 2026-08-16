import { Container, Graphics, Text } from 'pixi.js';
import type { ScenePalette } from './palette';

export class SendPreview {
  readonly root = new Container();
  private line = new Graphics();
  private label: Text;
  private scene: ScenePalette;
  private last:
    | {
        fromX: number;
        fromY: number;
        toX: number;
        toY: number;
        count: number;
        valid: boolean;
      }
    | null = null;

  constructor(scene: ScenePalette) {
    this.scene = scene;
    this.root.eventMode = 'none';
    this.root.visible = false;
    this.root.addChild(this.line);
    this.label = new Text({
      text: '',
      style: {
        fontFamily: 'Comfortaa, Nunito, "Segoe UI", system-ui, sans-serif',
        fontSize: 16,
        fontWeight: '700',
        fill: scene.ink,
      },
    });
    this.label.anchor.set(0.5);
    this.root.addChild(this.label);
  }

  hide(): void {
    this.root.visible = false;
    this.last = null;
  }

  retheme(): void {
    if (!this.last || !this.root.visible) return;
    const { fromX, fromY, toX, toY, count, valid } = this.last;
    this.show(fromX, fromY, toX, toY, count, valid);
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
    this.last = { fromX, fromY, toX, toY, count, valid };
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
      width: valid ? 5.5 : 3.5,
      color: valid ? this.scene.mist : this.scene.dust,
      alpha: valid ? 0.22 : 0.08,
      cap: 'round',
    });
    this.line.moveTo(fromX, fromY);
    this.line.quadraticCurveTo(cx, cy, toX, toY);
    this.line.stroke({
      width: valid ? 1.7 : 1.1,
      color: valid ? this.scene.ink : this.scene.inkSoft,
      alpha: valid ? 0.72 : 0.28,
      cap: 'round',
    });
    this.line.circle(toX, toY, valid ? 6 : 3.5);
    this.line.fill({
      color: valid ? this.scene.mist : this.scene.dust,
      alpha: valid ? 0.28 : 0.1,
    });
    this.line.circle(toX, toY, valid ? 3.2 : 2);
    this.line.fill({
      color: valid ? this.scene.ink : this.scene.inkSoft,
      alpha: valid ? 0.7 : 0.25,
    });

    this.label.text = String(count);
    this.label.position.set(cx, cy - 12);
    this.label.style.fill = valid ? this.scene.ink : this.scene.inkSoft;
    this.label.alpha = valid ? 0.95 : 0.4;
  }
}
