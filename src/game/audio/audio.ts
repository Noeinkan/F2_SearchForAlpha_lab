/** Procedural ambient pad + light SFX via Web Audio (no external assets). */
export class GameAudio {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private ambientTimer: number | null = null;
  private enabled = true;

  private ensure(): AudioContext | null {
    if (!this.enabled) return null;
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.14;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume();
    return this.ctx;
  }

  startAmbient(): void {
    const ctx = this.ensure();
    if (!ctx || !this.master || this.ambientTimer !== null) return;

    const playPad = () => {
      if (!this.ctx || !this.master) return;
      const now = this.ctx.currentTime;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      const freqs = [110, 138.59, 164.81, 207.65];
      osc.frequency.value = freqs[Math.floor(Math.random() * freqs.length)]!;
      osc.type = 'sine';
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(0.045, now + 1.5);
      gain.gain.linearRampToValueAtTime(0, now + 5.5);
      osc.connect(gain);
      gain.connect(this.master);
      osc.start(now);
      osc.stop(now + 6);
    };

    playPad();
    this.ambientTimer = window.setInterval(playPad, 4200);
  }

  stopAmbient(): void {
    if (this.ambientTimer !== null) {
      clearInterval(this.ambientTimer);
      this.ambientTimer = null;
    }
  }

  blip(freq: number, dur = 0.08, type: OscillatorType = 'triangle'): void {
    const ctx = this.ensure();
    if (!ctx || !this.master) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + dur);
    osc.connect(gain);
    gain.connect(this.master);
    osc.start(now);
    osc.stop(now + dur);
  }

  plant(): void {
    this.blip(220, 0.15, 'sine');
    this.blip(330, 0.2, 'sine');
  }

  send(): void {
    this.blip(480, 0.06, 'square');
  }

  capture(): void {
    this.blip(180, 0.2, 'sine');
    this.blip(270, 0.25, 'sine');
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (!on) this.stopAmbient();
  }
}
