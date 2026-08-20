import React from 'react';
import {Audio, interpolate, Sequence, staticFile} from 'remotion';
import {beatF, BGM_TRIM_FRAMES, DURATION_IN_FRAMES, SHOTS} from './timeline';

type SfxCue = {
  from: number;
  src: string;
  volume: number;
  durationInFrames: number;
  note: string;
};

// Central, beat-auditable cue sheet. Every entry is relative to a shot or the
// accepted beat grid; no bare absolute composition frame numbers are used.
export const SFX: SfxCue[] = [
  {from: beatF(1), src: 'gear-lock-metallic.mp3', volume: 0.34, durationInFrames: 34, note: 'open: official mark and wordmark settle'},
  {from: beatF(9), src: 'data-scan.mp3', volume: 0.20, durationInFrames: 61, note: 'search: evidence scan begins'},

  {from: beatF(18.75), src: 'paper-move-quick.mp3', volume: 0.27, durationInFrames: 28, note: 'sources: first card lands'},
  {from: beatF(19.5), src: 'paper-slide.mp3', volume: 0.23, durationInFrames: 33, note: 'sources: second card lands'},
  {from: beatF(20.25), src: 'paper-move-quick.mp3', volume: 0.20, durationInFrames: 28, note: 'sources: third card lands'},
  {from: beatF(21), src: 'paper-slide.mp3', volume: 0.17, durationInFrames: 33, note: 'sources: fourth card lands'},
  {from: beatF(23), src: 'air-woosh-quick.mp3', volume: 0.23, durationInFrames: 46, note: 'sources: dense card flow merges into one whoosh'},

  {from: beatF(28), src: 'switch-click-quick.mp3', volume: 0.17, durationInFrames: 31, note: 'workflow: plan node focus'},
  {from: beatF(30), src: 'switch-click-quick.mp3', volume: 0.15, durationInFrames: 31, note: 'workflow: search node focus'},
  {from: beatF(32), src: 'switch-click-quick.mp3', volume: 0.13, durationInFrames: 31, note: 'workflow: reflection node focus'},
  {from: beatF(34), src: 'switch-click-quick.mp3', volume: 0.11, durationInFrames: 31, note: 'workflow: report node focus'},

  {from: SHOTS.report.from + 6, src: 'typewriter-digital.mp3', volume: 0.30, durationInFrames: 56, note: 'report: content wipe and caret writing'},

  {from: SHOTS.outro.from, src: 'air-whoosh-powerful.mp3', volume: 0.38, durationInFrames: 56, note: 'outro: group-photo assembly buildup'},
  {from: beatF(56), src: 'impact-deep-whoosh.mp3', volume: 0.46, durationInFrames: 122, note: 'outro: wordmark stamp, global SFX peak'},
  {from: beatF(58), src: 'shimmer-sparkle-sweep.mp3', volume: 0.27, durationInFrames: 90, note: 'outro: forest-green rule and sign-off shimmer'},
];

export const AudioLayer: React.FC<{bgm: boolean}> = ({bgm}) => (
  <>
    {bgm ? (
      <Audio
        src={staticFile('audio/bgm/house-vibez.mp3')}
        startFrom={BGM_TRIM_FRAMES}
        volume={(frame) =>
          interpolate(
            frame,
            [0, 30, DURATION_IN_FRAMES - 50, DURATION_IN_FRAMES],
            [0, 0.27, 0.27, 0],
            {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
          )
        }
      />
    ) : null}
    {SFX.map((cue, index) => (
      <Sequence key={`${cue.src}-${index}`} from={cue.from} durationInFrames={cue.durationInFrames}>
        <Audio src={staticFile(`audio/sfx/${cue.src}`)} volume={cue.volume} />
      </Sequence>
    ))}
  </>
);
