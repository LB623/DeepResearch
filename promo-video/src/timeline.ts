export const FPS = 30;
export const DURATION_IN_FRAMES = 900;

// Audited from analysis/music/beat_data.json. The source track starts two
// frames in, placing its first detected transient on composition frame zero.
export const BGM_TRIM_FRAMES = 2;
export const SOURCE_BEAT0 = 0.06026933490930375;
export const BEAT0 = SOURCE_BEAT0 - BGM_TRIM_FRAMES / FPS;
export const BEAT_INT = 0.49183407359764697;

export const beatT = (beat: number) => BEAT0 + beat * BEAT_INT;
export const beatF = (beat: number) => Math.max(0, Math.round(beatT(beat) * FPS));

const shot = (fromBeat: number, toBeat: number) => ({
  fromBeat,
  toBeat,
  from: beatF(fromBeat),
  to: beatF(toBeat),
  duration: beatF(toBeat) - beatF(fromBeat),
});

export const SHOTS = {
  open: shot(0, 8),
  search: shot(8, 18),
  sources: shot(18, 26),
  workflow: shot(26, 36),
  breath: shot(36, 40),
  report: shot(40, 50),
  outro: shot(50, 61),
} as const;

export const localBeatFrame = (shotFromBeat: number, beat: number) =>
  beatF(shotFromBeat + beat) - beatF(shotFromBeat);
