import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {BRAND} from '../theme';

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const lerp = (progress: number, from: number, to: number) =>
  from + (to - from) * progress;
const segment = (
  frame: number,
  from: number,
  to: number,
  easing: (progress: number) => number = (progress) => progress,
) => easing(clamp01((frame - from) / Math.max(1, to - from)));
const outCubic = (progress: number) => 1 - Math.pow(1 - progress, 3);
const inOutQuad = (progress: number) =>
  progress < 0.5
    ? 2 * progress * progress
    : -1 + (4 - 2 * progress) * progress;

export const SceneOpen: React.FC = () => {
  // SceneOpen is mounted inside its own Sequence, so this is the shot-local frame.
  const frame = useCurrentFrame();
  const visible = lerp(segment(frame, 0, 7, outCubic), 0.82, 1);
  const expansion = segment(frame, 12, 51, outCubic);
  const sharedScale = lerp(expansion, 0.74, 1);
  const gap = lerp(expansion, 24, 42);
  const letterSpacing = lerp(segment(frame, 38, 57, inOutQuad), -3, -5.5);
  const subtitleIn = segment(frame, 31, 50, outCubic);

  return (
    <AbsoluteFill
      style={{
        background:
          'radial-gradient(circle at 50% 42%, #ffffff 0%, #f3f5f4 48%, #e9edeb 100%)',
        color: BRAND.text,
        fontFamily: BRAND.font,
        overflow: 'hidden',
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage:
            'linear-gradient(rgba(21,26,25,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(21,26,25,0.035) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage:
            'radial-gradient(circle at 50% 50%, black 0%, rgba(0,0,0,.64) 46%, transparent 82%)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: 463,
          display: 'flex',
          alignItems: 'center',
          gap,
          opacity: visible,
          transform: `translate(-50%, -50%) scale(${sharedScale})`,
          transformOrigin: 'center',
        }}
      >
        <Img
          src={staticFile('brand/research-mark.svg')}
          style={{
            width: 172,
            height: 172,
            flex: '0 0 auto',
            filter: 'drop-shadow(0 24px 32px rgba(23,78,68,.18))',
          }}
        />
        <div
          style={{
            color: BRAND.text,
            fontFamily: BRAND.font,
            fontSize: 134,
            fontWeight: 720,
            letterSpacing,
            lineHeight: 1,
            whiteSpace: 'nowrap',
          }}
        >
          DeepResearch
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 154,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 22,
          color: BRAND.textSoft,
          fontSize: 64,
          fontWeight: 610,
          letterSpacing: '-0.025em',
          lineHeight: 1.15,
          opacity: subtitleIn,
          transform: `translateY(${12 * (1 - subtitleIn)}px)`,
        }}
      >
        <span
          style={{
            width: 11,
            height: 11,
            borderRadius: 999,
            background: BRAND.primary,
            boxShadow: '0 0 20px rgba(29,111,95,.32)',
          }}
        />
        从一个问题，到可追溯的证据链
      </div>
    </AbsoluteFill>
  );
};
