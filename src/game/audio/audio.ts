/**
 * Procedural garden-space music + SFX (Web Audio, no samples).
 *
 * In the spirit of Eufloria's score (Brian Grainger / Milieu): a quiet drone
 * plus one sparse original lead, replayed slower / backwards / at other octaves.
 * Several original pieces; one is picked at random when audio (or a match) starts.
 */

import type { TreeKind } from '../sim/types';

const A2 = 110;
const MASTER = 0.4;
const MUSIC_GAIN = 0.55;
const SFX_GAIN = 0.95;

/** Pleasant transpositions around the color wheel (semitones from A). */
const KEYS = [0, 2, 3, 5, 7, 8, 10];

interface PhraseNote {
  semi: number;
  beats: number;
}

interface Piece {
  id: string;
  beat: number;
  drone: [number, number];
  theme: PhraseNote[];
  answer: PhraseNote[];
  leadFilter: number;
  gap: [number, number];
}

/** Original beds — not transcriptions. Sparse leads over a still fifth. */
const PIECES: Piece[] = [
  {
    id: 'vine',
    beat: 0.58,
    drone: [12, 19],
    leadFilter: 1700,
    gap: [4500, 8000],
    theme: [
      { semi: 19, beats: 1 },
      { semi: 21, beats: 1 },
      { semi: 19, beats: 2 },
      { semi: 24, beats: 1 },
      { semi: 21, beats: 1 },
      { semi: 16, beats: 2 },
      { semi: 19, beats: 1 },
      { semi: 12, beats: 3 },
    ],
    answer: [
      { semi: 16, beats: 1 },
      { semi: 19, beats: 1 },
      { semi: 21, beats: 2 },
      { semi: 19, beats: 1 },
      { semi: 16, beats: 2 },
      { semi: 12, beats: 3 },
    ],
  },
  {
    id: 'nightwell',
    beat: 0.74,
    drone: [12, 15],
    leadFilter: 1400,
    gap: [5500, 9500],
    theme: [
      { semi: 19, beats: 2 },
      { semi: 15, beats: 1 },
      { semi: 17, beats: 2 },
      { semi: 15, beats: 1 },
      { semi: 12, beats: 2 },
      { semi: 10, beats: 3 },
    ],
    answer: [
      { semi: 15, beats: 1 },
      { semi: 19, beats: 2 },
      { semi: 22, beats: 2 },
      { semi: 19, beats: 1 },
      { semi: 15, beats: 2 },
      { semi: 12, beats: 3 },
    ],
  },
  {
    id: 'petal',
    beat: 0.48,
    drone: [12, 16],
    leadFilter: 1900,
    gap: [4000, 7000],
    theme: [
      { semi: 24, beats: 1 },
      { semi: 21, beats: 1 },
      { semi: 24, beats: 2 },
      { semi: 28, beats: 1 },
      { semi: 21, beats: 2 },
      { semi: 19, beats: 1 },
      { semi: 16, beats: 3 },
    ],
    answer: [
      { semi: 21, beats: 1 },
      { semi: 24, beats: 1 },
      { semi: 16, beats: 2 },
      { semi: 19, beats: 1 },
      { semi: 12, beats: 3 },
    ],
  },
  {
    id: 'grove',
    beat: 0.88,
    drone: [12, 7],
    leadFilter: 1200,
    gap: [7000, 12000],
    theme: [
      { semi: 19, beats: 3 },
      { semi: 16, beats: 2 },
      { semi: 12, beats: 4 },
      { semi: 16, beats: 3 },
    ],
    answer: [
      { semi: 21, beats: 2 },
      { semi: 19, beats: 3 },
      { semi: 12, beats: 4 },
    ],
  },
  {
    id: 'distances',
    beat: 0.64,
    drone: [12, 21],
    leadFilter: 1600,
    gap: [5000, 9000],
    theme: [
      { semi: 12, beats: 2 },
      { semi: 24, beats: 1 },
      { semi: 19, beats: 2 },
      { semi: 28, beats: 1 },
      { semi: 16, beats: 2 },
      { semi: 24, beats: 1 },
      { semi: 12, beats: 3 },
    ],
    answer: [
      { semi: 21, beats: 1 },
      { semi: 16, beats: 2 },
      { semi: 19, beats: 1 },
      { semi: 12, beats: 2 },
      { semi: 7, beats: 3 },
    ],
  },
];

type Mood = 'play' | 'won' | 'lost';

function hz(semis: number, ratio: number): number {
  return A2 * ratio * 2 ** (semis / 12);
}

function rand(lo: number, hi: number): number {
  return lo + Math.random() * (hi - lo);
}

function makeNoise(ctx: AudioContext): AudioBuffer {
  const length = ctx.sampleRate * 2;
  const buf = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buf.getChannelData(0);
  let b0 = 0;
  let b1 = 0;
  let b2 = 0;
  for (let i = 0; i < length; i++) {
    const white = Math.random() * 2 - 1;
    b0 = 0.99886 * b0 + white * 0.0555179;
    b1 = 0.99332 * b1 + white * 0.0750759;
    b2 = 0.969 * b2 + white * 0.153852;
    data[i] = (b0 + b1 + b2 + white * 0.18) * 0.22;
  }
  return buf;
}

function makeWarmWave(ctx: AudioContext): PeriodicWave {
  const real = new Float32Array([0, 1, 0.18, 0.08, 0.03, 0.015]);
  const imag = new Float32Array(real.length);
  return ctx.createPeriodicWave(real, imag);
}

export class GameAudio {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private music: GainNode | null = null;
  private sfx: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private warm: PeriodicWave | null = null;

  private enabled = true;
  private unlocked = false;
  private dark = true;
  private ratio = 1;
  private mood: Mood = 'play';
  private phraseIndex = 0;
  private piece: Piece = PIECES[0]!;
  private piecePicked = false;

  private lastClashAt = 0;
  private lastDeathAt = 0;
  private lastBurnAt = 0;

  private motifTimer: number | null = null;
  private droneOsc: OscillatorNode[] = [];
  private droneFilter: BiquadFilterNode | null = null;
  private beds: AudioScheduledSourceNode[] = [];
  private bedsStarting = false;
  private gesturesBound = false;

  constructor() {
    this.bindGestures();
    this.pickPiece();
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  setAtmosphere(hue: number, dark: boolean): void {
    this.dark = dark;
    const idx = Math.round((hue / 360) * KEYS.length) % KEYS.length;
    this.ratio = 2 ** (KEYS[idx]! / 12);
    this.retuneDrone();
  }

  beginMatch(hue: number, dark: boolean): void {
    this.mood = 'play';
    this.phraseIndex = 0;
    this.pickPiece();
    this.setAtmosphere(hue, dark);
    if (this.droneOsc.length > 0) this.scheduleMelody(500);
  }

  private pickPiece(): void {
    const pool = this.piecePicked
      ? PIECES.filter((p) => p.id !== this.piece.id)
      : PIECES;
    const src = pool.length > 0 ? pool : PIECES;
    this.piece = src[Math.floor(Math.random() * src.length)]!;
    this.piecePicked = true;
  }

  private ensure(): AudioContext | null {
    if (!this.enabled) return null;
    if (!this.ctx) {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      try {
        this.ctx = new AC({ latencyHint: 'interactive' });
      } catch {
        this.ctx = new AC();
      }
      this.noise = makeNoise(this.ctx);
      this.warm = makeWarmWave(this.ctx);

      this.master = this.ctx.createGain();
      this.master.gain.value = MASTER;
      this.music = this.ctx.createGain();
      this.music.gain.value = MUSIC_GAIN;
      this.sfx = this.ctx.createGain();
      this.sfx.gain.value = SFX_GAIN;

      this.music.connect(this.master);
      this.sfx.connect(this.master);
      this.master.connect(this.ctx.destination);
    }
    return this.ctx;
  }

  private bindGestures(): void {
    if (this.gesturesBound) return;
    this.gesturesBound = true;
    const kick = () => this.startAmbient();
    document.addEventListener('pointerdown', kick);
    document.addEventListener('keydown', kick);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) this.startAmbient();
    });
  }

  /** Unlock + start the bed. Safe to call from any gesture (click, plant, send). */
  startAmbient(): void {
    this.whenRunning(() => {});
  }

  /** Resume if needed, then run. Oscillators never start while suspended. */
  private whenRunning(fn: () => void): void {
    this.unlocked = true;
    if (!this.enabled) return;
    const ctx = this.ensure();
    if (!ctx) return;
    const go = () => {
      if (!this.enabled || !this.ctx || this.ctx.state !== 'running') return;
      void this.startBedsWhenReady();
      fn();
    };
    if (ctx.state === 'running') {
      go();
      return;
    }
    void ctx.resume().then(go).catch(() => {});
  }

  private async startBedsWhenReady(): Promise<void> {
    const ctx = this.ctx;
    if (!ctx || !this.enabled || this.droneOsc.length > 0 || this.bedsStarting) {
      return;
    }
    if (ctx.state !== 'running') {
      try {
        await ctx.resume();
      } catch {
        return;
      }
    }
    if (!this.enabled || this.droneOsc.length > 0 || ctx.state !== 'running') {
      return;
    }
    this.bedsStarting = true;
    try {
      this.startDrone();
      this.scheduleMelody(800);
    } finally {
      this.bedsStarting = false;
    }
  }

  stopAmbient(): void {
    this.stopMusicBeds();
  }

  private stopMusicBeds(): void {
    if (this.motifTimer !== null) {
      clearTimeout(this.motifTimer);
      this.motifTimer = null;
    }
    for (const src of this.beds) this.stopSrc(src);
    this.beds = [];
    this.droneOsc = [];
    this.droneFilter = null;
    this.bedsStarting = false;
  }

  private stopSrc(node: AudioScheduledSourceNode | null | undefined): void {
    if (!node) return;
    try {
      node.stop();
    } catch {
      /* already stopped */
    }
    try {
      node.disconnect();
    } catch {
      /* already disconnected */
    }
  }

  private startDrone(): void {
    const ctx = this.ctx;
    const music = this.music;
    if (!ctx || !music || !this.warm) return;

    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.Q.value = 0.5;
    filter.frequency.value = this.dark ? 720 : 980;
    this.droneFilter = filter;

    const voices: { semis: number; gain: number }[] = [
      { semis: this.piece.drone[0], gain: 0.04 },
      { semis: this.piece.drone[1], gain: 0.02 },
    ];

    const now = ctx.currentTime;
    for (const v of voices) {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = hz(v.semis, this.ratio);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, now);
      g.gain.linearRampToValueAtTime(v.gain, now + 3.5);
      osc.connect(g);
      g.connect(filter);
      osc.start(now);
      this.droneOsc.push(osc);
      this.beds.push(osc);
    }
    filter.connect(music);
  }

  private retuneDrone(): void {
    if (!this.ctx || this.droneOsc.length === 0) return;
    const now = this.ctx.currentTime;
    const semis = this.piece.drone;
    for (let i = 0; i < this.droneOsc.length; i++) {
      const osc = this.droneOsc[i]!;
      osc.frequency.setTargetAtTime(hz(semis[i] ?? 12, this.ratio), now, 1.4);
    }
    if (this.droneFilter) {
      this.droneFilter.frequency.setTargetAtTime(this.dark ? 720 : 980, now, 0.8);
    }
  }

  private scheduleMelody(waitMs?: number): void {
    if (this.motifTimer !== null) clearTimeout(this.motifTimer);
    this.motifTimer = window.setTimeout(() => {
      const dur = this.playPhrase();
      const gap =
        this.mood === 'lost'
          ? rand(7000, 11000)
          : rand(this.piece.gap[0], this.piece.gap[1]);
      this.scheduleMelody(dur * 1000 + gap);
    }, waitMs ?? 1600);
  }

  private playPhrase(): number {
    if (!this.enabled || !this.music) return 4;
    const piece = this.piece;
    const i = this.phraseIndex++ % 4;
    let seq = i === 2 ? piece.answer : [...piece.theme];
    if (i === 3) seq = [...piece.theme].reverse();
    const beat =
      this.mood === 'lost' || i === 3
        ? piece.beat * 1.55
        : this.mood === 'won'
          ? piece.beat * 0.9
          : piece.beat;
    const flipOct = i === 1 || i === 3 || this.mood === 'won';
    let t = 0;
    for (const n of seq) {
      let s = n.semi;
      if (flipOct && Math.random() < 0.4) {
        s += Math.random() < 0.55 ? 12 : -12;
      }
      if (s < 7) s += 12;
      if (s > 33) s -= 12;
      this.lead(hz(s, this.ratio), t, n.beats * beat, piece.leadFilter);
      t += n.beats * beat;
    }
    return t;
  }

  private lead(freq: number, delay: number, hold: number, filterFreq: number): void {
    const dur = Math.max(1.4, hold * 1.1 + 0.55);
    this.tone({
      freq,
      dur,
      type: 'triangle',
      gain: 0.07,
      attack: 0.05,
      delay,
      dest: this.music ?? undefined,
      filterFreq,
    });
    this.tone({
      freq: freq / 2,
      dur: dur + 0.25,
      type: 'sine',
      gain: 0.022,
      attack: 0.08,
      delay,
      dest: this.music ?? undefined,
      filterFreq: 800,
    });
  }

  private duck(amount = 0.42, recover = 0.85): void {
    if (!this.music || !this.ctx) return;
    const now = this.ctx.currentTime;
    const g = this.music.gain;
    g.cancelScheduledValues(now);
    g.setValueAtTime(g.value, now);
    g.linearRampToValueAtTime(MUSIC_GAIN * amount, now + 0.05);
    g.linearRampToValueAtTime(MUSIC_GAIN, now + recover);
  }

  private tone(opts: {
    freq: number;
    dur: number;
    type?: OscillatorType | 'warm';
    gain?: number;
    attack?: number;
    delay?: number;
    slideTo?: number;
    detune?: number;
    pan?: number;
    filterFreq?: number;
    dest?: AudioNode;
  }): void {
    const ctx = this.ctx;
    const dest = opts.dest ?? this.sfx;
    if (!ctx || !dest) return;
    const now = ctx.currentTime + (opts.delay ?? 0);
    const osc = ctx.createOscillator();
    if (opts.type === 'warm' && this.warm) osc.setPeriodicWave(this.warm);
    else osc.type = opts.type === 'warm' ? 'sine' : (opts.type ?? 'sine');
    osc.frequency.setValueAtTime(opts.freq, now);
    if (opts.slideTo !== undefined) {
      osc.frequency.exponentialRampToValueAtTime(
        Math.max(20, opts.slideTo),
        now + opts.dur * 0.85,
      );
    }
    if (opts.detune) osc.detune.value = opts.detune;

    let node: AudioNode = osc;
    if (opts.filterFreq) {
      const f = ctx.createBiquadFilter();
      f.type = 'lowpass';
      f.frequency.value = opts.filterFreq;
      f.Q.value = 0.8;
      osc.connect(f);
      node = f;
    }

    const g = ctx.createGain();
    const amp = opts.gain ?? 0.08;
    const attack = Math.min(opts.attack ?? 0.012, opts.dur * 0.4);
    g.gain.setValueAtTime(0.0001, now);
    if (attack > 0.08) {
      g.gain.linearRampToValueAtTime(amp, now + attack);
    } else {
      g.gain.exponentialRampToValueAtTime(amp, now + Math.max(0.008, attack));
    }
    g.gain.exponentialRampToValueAtTime(0.0001, now + opts.dur);

    if (opts.pan !== undefined && opts.pan !== 0) {
      const p = ctx.createStereoPanner();
      p.pan.value = opts.pan;
      node.connect(g);
      g.connect(p);
      p.connect(dest);
    } else {
      node.connect(g);
      g.connect(dest);
    }

    osc.start(now);
    osc.stop(now + opts.dur + 0.02);
  }

  private noiseBurst(opts: {
    dur: number;
    gain: number;
    filterType?: BiquadFilterType;
    filterFreq?: number;
    filterTo?: number;
    q?: number;
    delay?: number;
    pan?: number;
  }): void {
    const ctx = this.ctx;
    if (!ctx || !this.sfx || !this.noise) return;
    const now = ctx.currentTime + (opts.delay ?? 0);
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = opts.filterType ?? 'bandpass';
    f.frequency.setValueAtTime(opts.filterFreq ?? 900, now);
    if (opts.filterTo !== undefined) {
      f.frequency.exponentialRampToValueAtTime(opts.filterTo, now + opts.dur);
    }
    f.Q.value = opts.q ?? 1.4;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, now);
    g.gain.exponentialRampToValueAtTime(opts.gain, now + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, now + opts.dur);
    src.connect(f);
    f.connect(g);
    if (opts.pan) {
      const p = ctx.createStereoPanner();
      p.pan.value = opts.pan;
      g.connect(p);
      p.connect(this.sfx);
    } else {
      g.connect(this.sfx);
    }
    src.start(now, Math.random() * 1.4);
    src.stop(now + opts.dur + 0.02);
  }

  plant(kind: TreeKind = 'dyson'): void {
    this.whenRunning(() => this.plantNow(kind));
  }

  private plantNow(kind: TreeKind): void {
    const shift = kind === 'energy' ? 4 : kind === 'defense' ? -3 : 0;
    const notes = [12, 19, 24].map((s) => hz(s + shift, this.ratio));
    for (let i = 0; i < notes.length; i++) {
      this.tone({
        freq: notes[i]!,
        dur: 0.5,
        type: 'sine',
        gain: 0.09,
        attack: 0.014,
        delay: i * 0.06,
      });
      this.tone({
        freq: notes[i]! * 2,
        dur: 0.28,
        type: 'triangle',
        gain: 0.02,
        delay: i * 0.06,
      });
    }
    this.noiseBurst({
      dur: 0.08,
      gain: 0.04,
      filterType: 'lowpass',
      filterFreq: 900,
      q: 0.6,
    });
  }

  send(count = 1): void {
    this.whenRunning(() => this.sendNow(count));
  }

  private sendNow(count: number): void {
    const intensity = Math.min(1.15, 0.55 + Math.log2(1 + count) * 0.18);
    this.noiseBurst({
      dur: 0.22,
      gain: 0.07 * intensity,
      filterType: 'bandpass',
      filterFreq: 380,
      filterTo: 2200,
      q: 1.1,
    });
    this.tone({
      freq: 340,
      slideTo: 620,
      dur: 0.16,
      type: 'sine',
      gain: 0.045 * intensity,
      attack: 0.01,
    });
  }

  capture(): void {
    this.whenRunning(() => this.captureNow());
  }

  private captureNow(): void {
    const notes = [12, 19, 24, 28];
    for (let i = 0; i < notes.length; i++) {
      this.tone({
        freq: hz(notes[i]!, this.ratio),
        dur: 0.7,
        type: 'sine',
        gain: 0.08,
        attack: 0.02,
        delay: i * 0.08,
      });
    }
    for (const s of [0, 4, 7, 12]) {
      this.tone({
        freq: hz(s, this.ratio),
        dur: 1.4,
        type: 'warm',
        gain: 0.04,
        attack: 0.12,
      });
    }
  }

  clash(): void {
    this.whenRunning(() => {
      const t = performance.now();
      if (t - this.lastClashAt < 180) return;
      this.lastClashAt = t;
      this.clashNow();
    });
  }

  private clashNow(): void {
    this.duck(0.5, 0.7);
    this.noiseBurst({
      dur: 0.07,
      gain: 0.11,
      filterType: 'bandpass',
      filterFreq: 720,
      filterTo: 1400,
      q: 3.2,
    });
    this.tone({
      freq: 210,
      slideTo: 150,
      dur: 0.09,
      type: 'triangle',
      gain: 0.05,
      filterFreq: 1200,
    });
  }

  death(): void {
    this.whenRunning(() => {
      const t = performance.now();
      if (t - this.lastDeathAt < 90) return;
      this.lastDeathAt = t;
      this.deathNow();
    });
  }

  private deathNow(): void {
    this.tone({
      freq: 240,
      slideTo: 72,
      dur: 0.28,
      type: 'sine',
      gain: 0.07,
      filterFreq: 900,
    });
    this.noiseBurst({
      dur: 0.1,
      gain: 0.05,
      filterType: 'lowpass',
      filterFreq: 600,
      q: 0.5,
    });
  }

  burn(): void {
    this.whenRunning(() => {
      const t = performance.now();
      if (t - this.lastBurnAt < 400) return;
      this.lastBurnAt = t;
      this.burnNow();
    });
  }

  private burnNow(): void {
    this.duck(0.45, 1.1);
    this.tone({
      freq: 64,
      dur: 0.55,
      type: 'sine',
      gain: 0.06,
      attack: 0.04,
      filterFreq: 180,
    });
    this.noiseBurst({
      dur: 0.45,
      gain: 0.07,
      filterType: 'lowpass',
      filterFreq: 420,
      filterTo: 160,
      q: 0.5,
    });
    for (let i = 0; i < 5; i++) {
      this.noiseBurst({
        dur: 0.05,
        gain: 0.045,
        filterType: 'highpass',
        filterFreq: 1800,
        q: 0.8,
        delay: 0.04 + i * 0.07,
        pan: rand(-0.5, 0.5),
      });
    }
  }

  fail(): void {
    this.whenRunning(() => this.failNow());
  }

  private failNow(): void {
    this.tone({
      freq: hz(7, this.ratio),
      dur: 0.16,
      type: 'sine',
      gain: 0.07,
      filterFreq: 1400,
    });
    this.tone({
      freq: hz(3, this.ratio),
      dur: 0.22,
      type: 'triangle',
      gain: 0.05,
      delay: 0.07,
      filterFreq: 1100,
    });
  }

  win(): void {
    this.mood = 'won';
    this.whenRunning(() => {
      const notes = [12, 16, 19, 24, 28, 31];
      for (let i = 0; i < notes.length; i++) {
        this.tone({
          freq: hz(notes[i]!, this.ratio),
          dur: 0.85,
          type: 'sine',
          gain: 0.085,
          attack: 0.02,
          delay: i * 0.09,
        });
      }
      for (const s of [0, 4, 7, 11, 16]) {
        this.tone({
          freq: hz(s, this.ratio),
          dur: 2.2,
          type: 'warm',
          gain: 0.05,
          attack: 0.2,
        });
      }
    });
  }

  lose(): void {
    this.mood = 'lost';
    this.whenRunning(() => {
      const notes = [12, 7, 3, 0, -5];
      for (let i = 0; i < notes.length; i++) {
        this.tone({
          freq: hz(notes[i]!, this.ratio),
          dur: 1.05,
          type: 'sine',
          gain: 0.07,
          attack: 0.04,
          delay: i * 0.2,
          filterFreq: 700,
        });
      }
    });
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (this.master && this.ctx) {
      const now = this.ctx.currentTime;
      this.master.gain.cancelScheduledValues(now);
      this.master.gain.setValueAtTime(on ? MASTER : 0.0001, now);
    }
    if (!on) {
      this.stopMusicBeds();
      return;
    }
    if (this.unlocked) this.startAmbient();
  }
}
