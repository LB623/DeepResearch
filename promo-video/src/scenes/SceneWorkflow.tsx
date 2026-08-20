import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import layoutJson from '../live-layout.json';
import {BRAND, clamp} from '../theme';
import {SHOTS} from '../timeline';

type Box = {x: number; y: number; w: number; h: number};
type CameraStep = {
  x: number;
  y: number;
  scale: number;
  cursorX: number;
  cursorY: number;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const finite = (value: unknown, fallback: number) =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;

const asBox = (value: unknown, fallback: Box): Box => {
  if (!isRecord(value)) return fallback;
  return {
    x: finite(value.x, fallback.x),
    y: finite(value.y, fallback.y),
    w: Math.max(1, finite(value.w, fallback.w)),
    h: Math.max(1, finite(value.h, fallback.h)),
  };
};

const root: Record<string, unknown> = isRecord(layoutJson) ? layoutJson : {};
const workflowLayout: Record<string, unknown> = isRecord(root.workflow)
  ? root.workflow
  : {};
const PAGE_H = Math.max(1080, finite(workflowLayout.pageH, 1080));
const timeline = asBox(workflowLayout.timeline, {
  x: 510,
  y: 168,
  w: 900,
  h: 730,
});

const fallbackEvents = Array.from({length: 5}, (_, index): Box => ({
  x: timeline.x + 34,
  y: timeline.y + 84 + index * ((timeline.h - 144) / 4),
  w: Math.max(280, timeline.w - 70),
  h: 76,
}));

const arrayEvents = Array.isArray(workflowLayout.events)
  ? workflowLayout.events.map((event: unknown, index: number) =>
      asBox(event, fallbackEvents[Math.min(index, fallbackEvents.length - 1)]),
    )
  : [];

const events = fallbackEvents.map((fallback, index) =>
  asBox(
    workflowLayout[`event${index + 1}`] ?? arrayEvents[index],
    fallback,
  ),
);

const keepCameraOnTexture = (point: number, span: number, scale: number) => {
  const halfViewport = span / (2 * scale);
  return Math.max(halfViewport, Math.min(span - halfViewport, point));
};

const stepFor = (event: Box): CameraStep => {
  // The fixture is DPR2, so a 3× focus remains sharp while lifting the
  // active node's body copy to the 32px effective-reading threshold.
  const scale = 3;
  const eventCenterX = event.x + event.w / 2;
  const eventCenterY = event.y + event.h / 2;
  return {
    // Bias toward the row's leading marker so the bound cursor remains in
    // frame at the higher focus magnification.
    x: keepCameraOnTexture(event.x + Math.min(event.w * 0.27, 290), 1920, scale),
    y: keepCameraOnTexture(eventCenterY, PAGE_H, scale),
    scale,
    // The cursor tip points to the timeline marker at the leading edge of the
    // real captured event row. It shares the same keyframe table as the camera.
    cursorX: event.x + Math.min(54, event.w * 0.08),
    cursorY: eventCenterY,
  };
};

// Four stops preserve the calibrated cursor-flyover grammar. The overview
// still establishes all five real stages; the final stop lands on report and
// citation validation, while the middle close-ups keep adjacent rows readable.
const focusEvents = [events[0], events[1], events[3], events[4]];
const STEPS: CameraStep[] = [
  {
    x: 960,
    y: PAGE_H / 2,
    scale: 0.91,
    cursorX: timeline.x + timeline.w / 2,
    cursorY: timeline.y + 48,
  },
  ...focusEvents.map(stepFor),
];

const WINDOWS = [
  // Landings align exactly with the four beat-derived click SFX cues.
  [12, 30],
  [41, 59],
  [71, 89],
  [100, 118],
] as const;

const cameraAt = (frame: number): CameraStep => {
  const out = {...STEPS[0]};
  let previous = STEPS[0];
  const keys: Array<keyof CameraStep> = [
    'x',
    'y',
    'scale',
    'cursorX',
    'cursorY',
  ];

  WINDOWS.forEach(([from, to], index) => {
    const progress = interpolate(frame, [from, to], [0, 1], {
      ...clamp,
      easing: Easing.inOut(Easing.cubic),
    });
    const target = STEPS[index + 1];
    keys.forEach((key) => {
      out[key] += progress * (target[key] - previous[key]);
    });
    previous = target;
  });

  return out;
};

export const SceneWorkflow: React.FC = () => {
  const frame = useCurrentFrame();
  const camera = cameraAt(frame);
  // Establish the real page on the cut; only the last 15% eases into focus.
  const focusIn = interpolate(frame, [0, 19], [0.85, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  const captionIn = interpolate(frame, [8, 20], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  const captionOut = interpolate(
    frame,
    [SHOTS.workflow.duration - 11, SHOTS.workflow.duration - 2],
    [1, 0],
    clamp,
  );

  let ripple = 1;
  let rippleVisible = false;
  for (const [, landing] of WINDOWS) {
    if (frame >= landing && frame <= landing + 11) {
      ripple = interpolate(frame, [landing, landing + 11], [0, 1], {
        ...clamp,
        easing: Easing.out(Easing.cubic),
      });
      rippleVisible = true;
    }
  }

  const cursorFlash = rippleVisible && ripple < 0.38;

  return (
    <AbsoluteFill
      style={{
        background: BRAND.deep,
        color: BRAND.text,
        fontFamily: BRAND.font,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: 1920,
          height: PAGE_H,
          opacity: focusIn,
          transformOrigin: '0 0',
          transform: `translate(${960 - camera.x * camera.scale}px, ${
            540 - camera.y * camera.scale
          }px) scale(${camera.scale})`,
        }}
      >
        <Img
          src={staticFile('textures/live/workflow-full.png')}
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: 1920,
            height: PAGE_H,
            display: 'block',
            filter: `blur(${(1 - focusIn) * 5}px)`,
          }}
        />

        {rippleVisible ? (
          <div
            style={{
              position: 'absolute',
              left: camera.cursorX,
              top: camera.cursorY,
              width: 34,
              height: 34,
              border: `3px solid ${BRAND.primaryHi}`,
              borderRadius: 999,
              opacity: (1 - ripple) * 0.92,
              transformOrigin: '50% 50%',
              transform: `translate(-50%, -50%) scale(${
                (0.3 + ripple * 1.65) / camera.scale
              })`,
              boxSizing: 'border-box',
              pointerEvents: 'none',
              zIndex: 4,
            }}
          />
        ) : null}

        <svg
          viewBox="0 0 24 24"
          style={{
            position: 'absolute',
            left: camera.cursorX,
            top: camera.cursorY,
            width: 30,
            height: 30,
            filter: 'drop-shadow(0 4px 7px rgba(15,28,24,.28))',
            pointerEvents: 'none',
            transformOrigin: '0 0',
            transform: `scale(${1 / camera.scale})`,
            zIndex: 5,
          }}
        >
          <path
            d="M4 2 L4 19 L9 14.4 L12.2 21.5 L15.4 20 L12.2 13 L19 12.6 Z"
            fill={cursorFlash ? BRAND.primaryHi : BRAND.text}
            stroke={BRAND.deep}
            strokeWidth={1.25}
          />
        </svg>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: 260,
          background:
            'linear-gradient(0deg, rgba(243,245,244,.99) 0%, rgba(243,245,244,.86) 48%, rgba(243,245,244,0) 100%)',
          pointerEvents: 'none',
          zIndex: 6,
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 104,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 22,
          color: BRAND.text,
          fontSize: 64,
          fontWeight: 640,
          letterSpacing: '-0.025em',
          lineHeight: 1.14,
          opacity: captionIn * captionOut,
          textShadow: '0 3px 22px rgba(243,245,244,.98)',
          pointerEvents: 'none',
          zIndex: 7,
        }}
      >
        <span
          style={{
            width: 11,
            height: 11,
            borderRadius: 999,
            background: BRAND.primary,
            boxShadow: '0 0 20px rgba(29,111,95,.30)',
          }}
        />
        自动推进多阶段研究工作流
      </div>
    </AbsoluteFill>
  );
};
