/**
 * Procedural ambient music + SFX (Web Audio, no samples).
 *
 * Slow Major7 suspended drone with inharmonic bells, drifting delays, and a
 * synthesized convolution reverb. No melodic lead: the bed is the music.
 * Several harmonically related roots are reachable from a Markov chain; one
 * is picked at random when audio (or a match) starts and glides every minute
 * or so. Inspired by the "non-repeating but never silent" approach used in
 * generative game soundtracks (Eufloria / COCOON / Discreet Music).
 */

import type { TreeKind } from '../sim/types';

const A2 = 110;
const MASTER = 0.32;
const MUSIC_GAIN = 0.45;
const SFX_GAIN = 0.85;

/** Roots reachable from the drone (semitones from A2). Pleasantly spaced. */
const ROOTS = [0, 3, 5, 7, 10, 12, 15, 17, 19];

/**
 * Voice set relative to the current root (semitones from root).
 * Major7 + sus2/add9 chord: root, 5th, octave, maj7, octave-5th, sus2/add9.
 * Each entry has a steady-state gain (very low — these stack).
 */
const VOICES: { semis: number; gain: number; type: OscillatorType }[] = [
  { semis: 0, gain: 0.045, type: 'sine' },
  { semis: 7, gain: 0.028, type: 'sine' },
  { semis: 12, gain: 0.034, type: 'triangle' },
  { semis: 11, gain: 0.022, type: 'sine' },
  { semis: 19, gain: 0.024, type: 'triangle' },
  { semis: 14, gain: 0.018, type: 'sine' },
];

/** Inharmonic bell ratios (slightly stretched). */
const BELLS = [
  { ratio: 2.04, gain: 0.012, type: 'sine' as OscillatorType },
  { ratio: 3.07, gain: 0.008, type: 'sine' as OscillatorType },
  { ratio: 4.11, gain: 0.005, type: 'triangle' as OscillatorType },
];

/** Drifting delay lengths (seconds). Prime-ish so they don't align. */
const DELAY_A_BASE = 3.7;
const DELAY_B_BASE = 5.2;

type Mood = 'play' | 'won' | 'lost';

interface VoiceHandle {
  osc: OscillatorNode;
  gain: GainNode;
  baseSemi: number;
  baseGain: number;
  /** Optional filter this voice is routed through (for cutoff LFO). */
  filter?: BiquadFilterNode;
}

interface BellHandle {
  osc: OscillatorNode;
  gain: GainNode;
  baseFreq: number;
  baseGain: number;
}

/**
 * Tiny LFO helper. Creates a slow oscillator, scales it via a gain node, and
 * routes it to an AudioParam. The center value is maintained by `param` itself
 * via setValueAtTime; the LFO adds a small oscillating offset around it.
 */
class LFO {
  osc: OscillatorNode;
  scaler: GainNode;
  constructor(ctx: AudioContext, freqHz: number, depth: number, dest: AudioParam) {
    this.osc = ctx.createOscillator();
    this.osc.type = 'sine';
    this.osc.frequency.value = Math.max(0.001, freqHz);
    this.scaler = ctx.createGain();
    this.scaler.gain.value = depth;
    this.osc.connect(this.scaler);
    this.scaler.connect(dest);
  }
  start(when: number): void {
    this.osc.start(when);
  }
  stop(): void {
    try {
      this.osc.stop();
    } catch {
      /* already stopped */
    }
    try {
      this.osc.disconnect();
      this.scaler.disconnect();
    } catch {
      /* already disconnected */
    }
  }
}

function hz(semis: number, ratio: number): number {
  return A2 * ratio * 2 ** (semis / 12);
}

function rand(lo: number, hi: number): number {
  return lo + Math.random() * (hi - lo);
}

/** Pink-ish noise buffer (2 s), used both for SFX and reverb IR generation. */
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

/**
 * Build a reverb impulse response from a noise burst that decays
 * exponentially over ~3 s. Smoothed tail (Hann-ish envelope).
 */
function makeReverbIR(ctx: AudioContext): AudioBuffer {
  const length = Math.floor(ctx.sampleRate * 3);
  const buf = ctx.createBuffer(2, length, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const data = buf.getChannelData(ch);
    for (let i = 0; i < length; i++) {
      const t = i / length;
      const env = Math.pow(1 - t, 3.2);
      data[i] = (Math.random() * 2 - 1) * env;
    }
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
  private musicDry: GainNode | null = null;
  private musicWet: GainNode | null = null;
  private sfx: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private warm: PeriodicWave | null = null;

  private enabled = true;
  private unlocked = false;
  private dark = true;
  /** Multiplier derived from scene hue (semitone transposition of A2). */
  private ratio = 1;
  private mood: Mood = 'play';

  /** Active root index (into ROOTS) and applied ratio (transposition). */
  private rootIdx = 0;
  private pendingRootIdx: number | null = null;

  private reverb: ConvolverNode | null = null;
  private delayA: DelayNode | null = null;
  private delayB: DelayNode | null = null;
  private delayAFb: GainNode | null = null;
  private delayBFb: GainNode | null = null;
  private delayAWet: GainNode | null = null;
  private delayBWet: GainNode | null = null;
  private delayALfo: LFO | null = null;
  private delayBLfo: LFO | null = null;

  private voices: VoiceHandle[] = [];
  private voiceFilter: BiquadFilterNode | null = null;
  private voiceLfos: LFO[] = [];

  private bells: BellHandle[] = [];
  private bellLfos: LFO[] = [];
  private markovTimer: number | null = null;

  private lastClashAt = 0;
  private lastDeathAt = 0;
  private lastBurnAt = 0;
  private lastCaptureAt = 0;

  private beds: AudioScheduledSourceNode[] = [];
  private bedsStarting = false;
  private gesturesBound = false;

  constructor() {
    this.bindGestures();
    this.pickRoot();
  }

  isEnabled(): boolean {
    return this.enabled;
  }

  setAtmosphere(hue: number, dark: boolean): void {
    this.dark = dark;
    // Slight chromatic transpose from hue; same idea as before, gentler range.
    const semis = ((Math.round((hue / 360) * 12) % 12) - 6) * 0.5;
    this.ratio = 2 ** (semis / 12);
    this.applyTranspose();
    if (this.voiceFilter) {
      const now = this.ctx?.currentTime ?? 0;
      this.voiceFilter.frequency.setTargetAtTime(this.dark ? 760 : 1080, now, 1.2);
    }
  }

  beginMatch(hue: number, dark: boolean): void {
    this.mood = 'play';
    this.pickRoot();
    this.setAtmosphere(hue, dark);
    this.scheduleMarkov(8000);
  }

  private pickRoot(): void {
    let next = Math.floor(Math.random() * ROOTS.length);
    if (next === this.rootIdx && ROOTS.length > 1) {
      next = (next + 1 + Math.floor(Math.random() * (ROOTS.length - 1))) % ROOTS.length;
    }
    this.rootIdx = next;
    this.applyTranspose();
  }

  private applyTranspose(): void {
    if (!this.ctx || this.voices.length === 0) return;
    const now = this.ctx.currentTime;
    const rootSemi = ROOTS[this.rootIdx] ?? 0;
    const r = this.ratio;
    for (const v of this.voices) {
      const semi = rootSemi + v.baseSemi;
      v.osc.frequency.setTargetAtTime(hz(semi, r), now, 6);
    }
    for (const b of this.bells) {
      const f = b.baseFreq * 2 ** (rootSemi / 12) * (this.ratio / 1);
      b.osc.frequency.setTargetAtTime(f, now, 6);
    }
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
      this.reverb = this.ctx.createConvolver();
      this.reverb.buffer = makeReverbIR(this.ctx);

      this.master = this.ctx.createGain();
      this.master.gain.value = MASTER;
      this.music = this.ctx.createGain();
      this.music.gain.value = MUSIC_GAIN;
      this.musicDry = this.ctx.createGain();
      this.musicDry.gain.value = 0.65;
      this.musicWet = this.ctx.createGain();
      this.musicWet.gain.value = 0.35;
      this.sfx = this.ctx.createGain();
      this.sfx.gain.value = SFX_GAIN;

      // Music dry path -> music gain -> master.
      this.musicDry.connect(this.music);
      // Music wet path: into reverb (pre-volume) then to music gain.
      this.music.connect(this.reverb);
      this.reverb.connect(this.musicWet);
      this.musicWet.connect(this.master);

      // Two drifting delays on the wet bus. Each delay taps back into itself.
      this.delayA = this.ctx.createDelay(8);
      this.delayA.delayTime.value = DELAY_A_BASE;
      this.delayAFb = this.ctx.createGain();
      this.delayAFb.gain.value = 0.45;
      this.delayAWet = this.ctx.createGain();
      this.delayAWet.gain.value = 0.5;

      this.delayB = this.ctx.createDelay(8);
      this.delayB.delayTime.value = DELAY_B_BASE;
      this.delayBFb = this.ctx.createGain();
      this.delayBFb.gain.value = 0.4;
      this.delayBWet = this.ctx.createGain();
      this.delayBWet.gain.value = 0.45;

      this.delayA.connect(this.delayAFb);
      this.delayAFb.connect(this.delayA);
      this.delayA.connect(this.delayAWet);
      this.delayAWet.connect(this.musicWet);

      this.delayB.connect(this.delayBFb);
      this.delayBFb.connect(this.delayB);
      this.delayB.connect(this.delayBWet);
      this.delayBWet.connect(this.musicWet);

      // Drift the delay times slowly (±2%) via LFOs.
      this.delayALfo = new LFO(this.ctx, 0.018, DELAY_A_BASE * 0.02, this.delayA.delayTime);
      this.delayBLfo = new LFO(this.ctx, 0.013, DELAY_B_BASE * 0.02, this.delayB.delayTime);

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

  startAmbient(): void {
    this.whenRunning(() => {});
  }

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
    if (!ctx || !this.enabled || this.voices.length > 0 || this.bedsStarting) {
      return;
    }
    if (ctx.state !== 'running') {
      try {
        await ctx.resume();
      } catch {
        return;
      }
    }
    if (!this.enabled || this.voices.length > 0 || ctx.state !== 'running') {
      return;
    }
    this.bedsStarting = true;
    try {
      this.startDrone();
      this.startLfoSource(this.delayALfo);
      this.startLfoSource(this.delayBLfo);
      this.scheduleMarkov(12000);
    } finally {
      this.bedsStarting = false;
    }
  }

  private startLfoSource(lfo: LFO | null): void {
    if (!lfo || !this.ctx) return;
    const now = this.ctx.currentTime + 0.05;
    lfo.start(now);
    this.beds.push(lfo.osc);
  }

  stopAmbient(): void {
    this.stopMusicBeds();
  }

  private stopMusicBeds(): void {
    if (this.markovTimer !== null) {
      window.clearTimeout(this.markovTimer);
      this.markovTimer = null;
    }
    for (const src of this.beds) this.stopSrc(src);
    this.beds = [];
    for (const v of this.voices) {
      try {
        v.osc.stop();
      } catch {
        /* already stopped */
      }
      try {
        v.osc.disconnect();
        v.gain.disconnect();
        v.filter?.disconnect();
      } catch {
        /* already disconnected */
      }
    }
    this.voices = [];
    this.voiceLfos = [];
    this.voiceFilter = null;
    for (const b of this.bells) {
      try {
        b.osc.stop();
      } catch {
        /* already stopped */
      }
      try {
        b.osc.disconnect();
        b.gain.disconnect();
      } catch {
        /* already disconnected */
      }
    }
    this.bells = [];
    this.bellLfos = [];
    for (const lfo of [this.delayALfo, this.delayBLfo]) lfo?.stop();
    this.delayALfo = null;
    this.delayBLfo = null;
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
    const dry = this.musicDry;
    const wet = this.musicWet;
    if (!ctx || !dry || !wet) return;

    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.Q.value = 0.5;
    filter.frequency.value = this.dark ? 760 : 1080;
    this.voiceFilter = filter;

    const now = ctx.currentTime;
    const rootSemi = ROOTS[this.rootIdx] ?? 0;
    const r = this.ratio;

    // Voices: major7 + sus2/add9 stack, each with its own LFO on detune/amp.
    const GOLDEN = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < VOICES.length; i++) {
      const def = VOICES[i]!;
      const osc = ctx.createOscillator();
      osc.type = def.type;
      osc.frequency.value = hz(rootSemi + def.semi, r);
      // Per-voice detune (±3 to ±14 cents) for "beating" warmth.
      const cents = rand(3, 14) * (Math.random() < 0.5 ? -1 : 1);
      osc.detune.value = cents;

      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, now);
      g.gain.linearRampToValueAtTime(def.gain, now + 4);

      osc.connect(g);
      g.connect(filter);

      osc.start(now);
      this.beds.push(osc);

      // Per-voice slow LFO on amplitude (~0.005–0.02 Hz, golden-angle spread).
      const ampFreq = 0.005 + (i * GOLDEN) % 0.018;
      const ampDepth = def.gain * 0.22;
      const ampLfo = new LFO(ctx, ampFreq, ampDepth, g.gain);
      ampLfo.start(now);
      this.voiceLfos.push(ampLfo);
      this.beds.push(ampLfo.osc);

      this.voices.push({ osc, gain: g, baseSemi: def.semi, baseGain: def.gain });
    }

    filter.connect(dry);
    filter.connect(wet);

    // Inharmonic bells — sparse "sparkles", gated by Markov.
    for (let i = 0; i < BELLS.length; i++) {
      const def = BELLS[i]!;
      const osc = ctx.createOscillator();
      osc.type = def.type;
      const baseFreq = hz(rootSemi + 12, r) * def.ratio * 0.5;
      osc.frequency.value = baseFreq;
      const g = ctx.createGain();
      // Start silent — Markov gate fades them in.
      g.gain.setValueAtTime(0.0001, now);
      osc.connect(g);
      g.connect(wet);
      osc.start(now);
      this.bells.push({ osc, gain: g, baseFreq, baseGain: def.gain });
      this.beds.push(osc);

      // Per-bell slow LFO on amplitude.
      const lfo = new LFO(ctx, 0.04 + i * 0.011, def.gain * 0.8, g.gain);
      lfo.start(now);
      this.bellLfos.push(lfo);
      this.beds.push(lfo.osc);
    }
  }

  /** Markov-style gate: each tick decides which bells to fade in/out. */
  private scheduleMarkov(waitMs?: number): void {
    if (this.markovTimer !== null) window.clearTimeout(this.markovTimer);
    this.markovTimer = window.setTimeout(() => {
      this.markovStep();
      const next = rand(45000, 90000);
      this.scheduleMarkov(next);
    }, waitMs ?? 60000);
  }

  private markovStep(): void {
    if (!this.ctx || !this.musicDry) return;
    const now = this.ctx.currentTime;

    // 60% chance to glide to a new root (must differ).
    if (Math.random() < 0.6) {
      let next = Math.floor(Math.random() * ROOTS.length);
      if (next === this.rootIdx && ROOTS.length > 1) {
        next = (next + 1 + Math.floor(Math.random() * Math.max(1, ROOTS.length - 1))) % ROOTS.length;
      }
      this.pendingRootIdx = next;
    }
    // Apply glide.
    const targetIdx = this.pendingRootIdx ?? this.rootIdx;
    if (targetIdx !== this.rootIdx) {
      const prev = this.rootIdx;
      this.rootIdx = targetIdx;
      this.pendingRootIdx = null;
      const r = this.ratio;
      const newRoot = ROOTS[this.rootIdx] ?? 0;
      const oldRoot = ROOTS[prev] ?? 0;
      for (const v of this.voices) {
        v.osc.frequency.cancelScheduledValues(now);
        v.osc.frequency.setValueAtTime(hz(oldRoot + v.baseSemi, r), now);
        v.osc.frequency.setTargetAtTime(hz(newRoot + v.baseSemi, r), now + 0.5, 6);
      }
      for (const b of this.bells) {
        const oldF = b.baseFreq * 2 ** (oldRoot / 12);
        const newF = b.baseFreq * 2 ** (newRoot / 12);
        b.osc.frequency.cancelScheduledValues(now);
        b.osc.frequency.setValueAtTime(oldF, now);
        b.osc.frequency.setTargetAtTime(newF, now + 0.5, 6);
      }
    }

    // Bell gate: each bell fades toward its base gain or zero with prob.
    for (let i = 0; i < this.bells.length; i++) {
      const b = this.bells[i]!;
      const want = Math.random() < 0.5 ? b.baseGain : 0;
      b.gain.gain.cancelScheduledValues(now);
      b.gain.gain.setValueAtTime(b.gain.gain.value, now);
      b.gain.gain.linearRampToValueAtTime(Math.max(0.0001, want), now + 8);
    }
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
        gain: 0.07,
        attack: 0.018,
        delay: i * 0.06,
      });
      this.tone({
        freq: notes[i]! * 2,
        dur: 0.28,
        type: 'triangle',
        gain: 0.016,
        delay: i * 0.06,
      });
    }
    this.noiseBurst({
      dur: 0.08,
      gain: 0.035,
      filterType: 'lowpass',
      filterFreq: 900,
      q: 0.6,
    });
  }

  send(count = 1): void {
    this.whenRunning(() => this.sendNow(count));
  }

  private sendNow(count: number): void {
    const intensity = Math.min(1.1, 0.5 + Math.log2(1 + count) * 0.16);
    this.noiseBurst({
      dur: 0.22,
      gain: 0.06 * intensity,
      filterType: 'bandpass',
      filterFreq: 380,
      filterTo: 1800,
      q: 1.0,
    });
    this.tone({
      freq: 320,
      slideTo: 540,
      dur: 0.18,
      type: 'sine',
      gain: 0.04 * intensity,
      attack: 0.012,
    });
  }

  capture(): void {
    this.whenRunning(() => {
      const t = performance.now();
      if (t - this.lastCaptureAt < 250) return;
      this.lastCaptureAt = t;
      this.captureNow();
    });
  }

  private captureNow(): void {
    const notes = [12, 19, 24, 28];
    for (let i = 0; i < notes.length; i++) {
      this.tone({
        freq: hz(notes[i]!, this.ratio),
        dur: 0.7,
        type: 'sine',
        gain: 0.07,
        attack: 0.025,
        delay: i * 0.08,
      });
    }
    for (const s of [0, 4, 7, 12]) {
      this.tone({
        freq: hz(s, this.ratio),
        dur: 1.4,
        type: 'warm',
        gain: 0.035,
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
    this.duck(0.55, 0.7);
    // Soft thump — long, low-Q noise burst with gentle filter sweep. No tone.
    this.noiseBurst({
      dur: 0.14,
      gain: 0.09,
      filterType: 'bandpass',
      filterFreq: 520,
      filterTo: 1100,
      q: 1.4,
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
      freq: 200,
      slideTo: 64,
      dur: 0.55,
      type: 'sine',
      gain: 0.06,
      attack: 0.02,
      filterFreq: 500,
    });
    this.noiseBurst({
      dur: 0.18,
      gain: 0.04,
      filterType: 'lowpass',
      filterFreq: 480,
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
      gain: 0.055,
      attack: 0.04,
      filterFreq: 180,
    });
    this.noiseBurst({
      dur: 0.45,
      gain: 0.06,
      filterType: 'lowpass',
      filterFreq: 420,
      filterTo: 160,
      q: 0.5,
    });
    for (let i = 0; i < 5; i++) {
      this.noiseBurst({
        dur: 0.05,
        gain: 0.04,
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
      gain: 0.06,
      filterFreq: 1200,
    });
    this.tone({
      freq: hz(3, this.ratio),
      dur: 0.22,
      type: 'triangle',
      gain: 0.045,
      delay: 0.07,
      filterFreq: 1000,
    });
  }

  win(): void {
    this.mood = 'won';
    this.whenRunning(() => {
      // Brighten the bed: open the wet/dry mix over 8 s, lift cutoff.
      this.transitionBed(1.05, 1.25);
      const notes = [12, 16, 19, 24, 28, 31];
      for (let i = 0; i < notes.length; i++) {
        this.tone({
          freq: hz(notes[i]!, this.ratio),
          dur: 0.85,
          type: 'sine',
          gain: 0.08,
          attack: 0.025,
          delay: i * 0.09,
        });
      }
      for (const s of [0, 4, 7, 11, 16]) {
        this.tone({
          freq: hz(s, this.ratio),
          dur: 2.2,
          type: 'warm',
          gain: 0.045,
          attack: 0.2,
        });
      }
    });
  }

  lose(): void {
    this.mood = 'lost';
    this.whenRunning(() => {
      // Darken the bed: dry cut, wet open, cutoff down — over 8 s.
      this.transitionBed(0.7, 0.5);
      const notes = [12, 7, 3, 0, -5];
      for (let i = 0; i < notes.length; i++) {
        this.tone({
          freq: hz(notes[i]!, this.ratio),
          dur: 1.05,
          type: 'sine',
          gain: 0.06,
          attack: 0.04,
          delay: i * 0.2,
          filterFreq: 600,
        });
      }
    });
  }

  /**
   * Smoothly transition the bed's dry/wet balance and overall cutoff for
   * win/lose moods. Reverts to neutral when called again later.
   */
  private transitionBed(dryMul: number, wetMul: number): void {
    if (!this.ctx || !this.musicDry || !this.musicWet) return;
    const now = this.ctx.currentTime;
    this.musicDry.gain.cancelScheduledValues(now);
    this.musicDry.gain.setValueAtTime(this.musicDry.gain.value, now);
    this.musicDry.gain.linearRampToValueAtTime(0.65 * dryMul, now + 8);
    this.musicWet.gain.cancelScheduledValues(now);
    this.musicWet.gain.setValueAtTime(this.musicWet.gain.value, now);
    this.musicWet.gain.linearRampToValueAtTime(0.35 * wetMul, now + 8);
    if (this.voiceFilter) {
      const target = this.dark ? 760 : 1080;
      const targetMul = this.mood === 'won' ? 1.2 : this.mood === 'lost' ? 0.6 : 1;
      this.voiceFilter.frequency.setTargetAtTime(target * targetMul, now, 3);
    }
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