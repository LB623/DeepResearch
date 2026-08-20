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

type Box = {x: number; y: number; w: number; h: number};
type FlyElement = {
  key: string;
  src: string;
  crop?: Box;
  w: number;
  h: number;
  cx: number;
  cy: number;
  scale: number;
  rotation: number;
  dx: number;
  dy: number;
  radius: number;
  cue: number;
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
const searchLayout: Record<string, unknown> = isRecord(root.search)
  ? root.search
  : {};
const workflowLayout: Record<string, unknown> = isRecord(root.workflow)
  ? root.workflow
  : {};
const reportLayout: Record<string, unknown> = isRecord(root.report)
  ? root.report
  : {};
const SEARCH_PAGE_H = Math.max(1080, finite(searchLayout.pageH, 1080));

const searchInput = asBox(searchLayout.input, {x: 505, y: 790, w: 910, h: 92});
const searchEvidence = asBox(
  searchLayout.evidence ?? searchLayout.sources ?? searchLayout.results,
  {x: 530, y: 272, w: 860, h: 310},
);
const workflowTimeline = asBox(workflowLayout.timeline, {
  x: 510,
  y: 180,
  w: 900,
  h: 690,
});
const workflowEvents = Array.from({length: 5}, (_, index) =>
  asBox(workflowLayout[`event${index + 1}`], {
    x: workflowTimeline.x + 32,
    y:
      workflowTimeline.y +
      82 +
      index * ((workflowTimeline.h - 150) / 4),
    w: workflowTimeline.w - 64,
    h: 82,
  }),
);
const reportDocument = asBox(reportLayout.document, {
  x: 510,
  y: 104,
  w: 900,
  h: 720,
});
const reportTable = asBox(reportLayout.table, {
  x: reportDocument.x + 18,
  y: reportDocument.y + 320,
  w: reportDocument.w - 36,
  h: 220,
});
const reportReferences = asBox(reportLayout.references, {
  x: reportDocument.x + 18,
  y: reportDocument.y + 565,
  w: reportDocument.w - 36,
  h: 130,
});

const ELEMENTS: FlyElement[] = [
  {
    key: 'search-input',
    src: 'textures/live/search-input.png',
    w: searchInput.w,
    h: searchInput.h,
    cx: 960,
    cy: 132,
    scale: 0.62,
    rotation: -0.8,
    dx: 0,
    dy: -310,
    radius: 24,
    cue: 4,
  },
  {
    key: 'search-evidence',
    src: 'textures/live/search-evidence.png',
    w: searchEvidence.w,
    h: searchEvidence.h,
    cx: 370,
    cy: 252,
    scale: 0.47,
    rotation: -3.5,
    dx: -560,
    dy: -120,
    radius: 14,
    cue: 10,
  },
  {
    key: 'workflow-timeline',
    src: 'textures/live/workflow-timeline.png',
    w: workflowTimeline.w,
    h: workflowTimeline.h,
    cx: 270,
    cy: 555,
    scale: 0.43,
    rotation: -4,
    dx: -560,
    dy: 0,
    radius: 16,
    cue: 16,
  },
  {
    key: 'workflow-plan',
    src: 'textures/live/workflow-event1.png',
    w: workflowEvents[0].w,
    h: workflowEvents[0].h,
    cx: 1540,
    cy: 270,
    scale: 0.53,
    rotation: 3,
    dx: 520,
    dy: -170,
    radius: 12,
    cue: 22,
  },
  {
    key: 'workflow-analysis',
    src: 'textures/live/workflow-event4.png',
    w: workflowEvents[3].w,
    h: workflowEvents[3].h,
    cx: 1610,
    cy: 510,
    scale: 0.55,
    rotation: 2.5,
    dx: 540,
    dy: 0,
    radius: 12,
    cue: 28,
  },
  {
    key: 'workflow-report',
    src: 'textures/live/workflow-event5.png',
    w: workflowEvents[4].w,
    h: workflowEvents[4].h,
    cx: 1515,
    cy: 735,
    scale: 0.54,
    rotation: -2.5,
    dx: 530,
    dy: 210,
    radius: 12,
    cue: 34,
  },
  {
    key: 'report-document',
    src: 'textures/live/report-document.png',
    w: reportDocument.w,
    h: reportDocument.h,
    cx: 500,
    cy: 870,
    scale: 0.38,
    rotation: 3.5,
    dx: -500,
    dy: 320,
    radius: 16,
    cue: 40,
  },
  {
    key: 'report-table',
    src: 'textures/live/report-table.png',
    w: reportTable.w,
    h: reportTable.h,
    cx: 960,
    cy: 920,
    scale: 0.5,
    rotation: 1,
    dx: 0,
    dy: 360,
    radius: 12,
    cue: 46,
  },
  {
    key: 'report-references',
    src: 'textures/live/report-references.png',
    w: reportReferences.w,
    h: reportReferences.h,
    cx: 1500,
    cy: 905,
    scale: 0.51,
    rotation: -3,
    dx: 520,
    dy: 300,
    radius: 12,
    cue: 52,
  },
];

const WORDMARK = 'DeepResearch'.split('');
const FLY_EASE = Easing.bezier(0.34, 1.4, 0.44, 1);
const CRANE_EASE = Easing.bezier(0.3, 0, 0.2, 1);
const HOLD_FROM = 130;

// Parameters are index-derived so the same frame renders identically in every
// process. Their low opacity preserves the clean sign-off while retaining the
// launch-card's faint atmosphere.
const SIGNAL_DUST = Array.from({length: 12}, (_, index) => ({
  x: (index * 439 + 137) % 1920,
  y0: (index * 613 + 271) % 1080,
  rise: 0.24 + (index % 4) * 0.09,
  sway: 7 + (index % 3) * 4,
  frequency: 0.02 + (index % 3) * 0.007,
  phase: (index * 0.83) % (Math.PI * 2),
  size: 2 + (index % 2) * 0.5,
  opacity: 0.07 + ((index * 7) % 4) * 0.025,
}));

const ElementVisual: React.FC<{element: FlyElement}> = ({element}) => {
  if (element.crop) {
    return (
      <div
        style={{
          position: 'absolute',
          inset: 0,
          overflow: 'hidden',
          background: BRAND.bg,
        }}
      >
        <Img
          src={staticFile(element.src)}
          style={{
            position: 'absolute',
            left: -element.crop.x,
            top: -element.crop.y,
            width: 1920,
            height: SEARCH_PAGE_H,
            display: 'block',
          }}
        />
      </div>
    );
  }

  return (
    <Img
      src={staticFile(element.src)}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        display: 'block',
      }}
    />
  );
};

export const SceneOutro: React.FC = () => {
  const frame = useCurrentFrame();
  // Everything, including the subtle motes, freezes for the final 32 frames.
  const motionFrame = Math.min(frame, HOLD_FROM);
  const backgroundBlur = interpolate(motionFrame, [0, 34], [1, 17], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  const recede = interpolate(motionFrame, [84, 96], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  const crane = interpolate(motionFrame, [0, 56], [0, 1], {
    ...clamp,
    easing: CRANE_EASE,
  });
  const push = interpolate(motionFrame, [56, 118], [0, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  const cameraScale = 1.055 - crane * 0.055 + push * 0.026;
  const cameraTilt = 4 * (1 - crane);

  const sweepX = interpolate(motionFrame, [2, 18], [-720, 2040], {
    ...clamp,
    easing: Easing.inOut(Easing.cubic),
  });
  const sweepOpacity = interpolate(
    motionFrame,
    [2, 6, 14, 18],
    [0, 0.1, 0.1, 0],
    clamp,
  );
  const stageLight = interpolate(
    motionFrame,
    [86, 101, 116],
    [0, 0.44, 0.2],
    clamp,
  );
  const vignette = interpolate(motionFrame, [84, 104], [0, 0.12], clamp);
  const rule = interpolate(motionFrame, [118, 128], [0, 1], {
    ...clamp,
    easing: CRANE_EASE,
  });
  const ruleExtension = interpolate(motionFrame, [118, 124], [0, 1], {
    ...clamp,
    easing: CRANE_EASE,
  });
  const ruleExtensionOpacity = interpolate(
    motionFrame,
    [124, 130],
    [1, 0],
    clamp,
  );
  const wordSpacing = interpolate(motionFrame, [114, 123], [-0.018, 0.005], {
    ...clamp,
    easing: CRANE_EASE,
  });
  const markProgress = interpolate(motionFrame, [82, 98], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.2, 0.75, 0.3, 1),
  });

  return (
    <AbsoluteFill
      style={{
        background: BRAND.deep,
        color: BRAND.text,
        fontFamily: BRAND.font,
        overflow: 'hidden',
      }}
    >
      <AbsoluteFill
        style={{
          transform: `perspective(1400px) rotateX(${cameraTilt}deg) scale(${cameraScale})`,
          transformOrigin: '50% 45%',
        }}
      >
        <Img
          src={staticFile('textures/live/report-full.png')}
          style={{
            position: 'absolute',
            inset: 0,
            width: 1920,
            height: 1080,
            display: 'block',
            opacity: 0.36,
            filter: `blur(${backgroundBlur}px) saturate(.72) brightness(.98)`,
            transform: 'scale(1.04)',
          }}
        />
        <AbsoluteFill
          style={{
            background:
              'radial-gradient(1040px 700px at 50% 49%, rgba(250,251,250,.52), rgba(233,237,235,.93) 74%)',
          }}
        />

        <AbsoluteFill style={{pointerEvents: 'none'}}>
          {ELEMENTS.map((element) => {
            if (motionFrame < element.cue) return null;
            const flight = interpolate(
              motionFrame,
              [element.cue, element.cue + 18],
              [0, 1],
              {...clamp, easing: FLY_EASE},
            );
            const linearFlight = interpolate(
              motionFrame,
              [element.cue, element.cue + 18],
              [0, 1],
              clamp,
            );
            const opacity = interpolate(
              motionFrame,
              [element.cue, element.cue + 4],
              [0, 1],
              clamp,
            );
            const x = element.dx * (1 - flight);
            const y = element.dy * (1 - flight);
            const rotation = element.rotation * (2 - flight);
            const scale = element.scale * (1.12 - flight * 0.12);
            const air = Math.max(0, 1 - flight);
            const ghostVisible = linearFlight > 0.05 && linearFlight < 0.95;
            const settledOpacity = opacity * (1 - recede * 0.22);
            const glow =
              motionFrame >= element.cue + 18
                ? interpolate(
                    motionFrame,
                    [element.cue + 18, element.cue + 25],
                    [0.3, 0],
                    clamp,
                  )
                : 0;
            const glowRadius = Math.min(
              270,
              Math.max(element.w, element.h) * element.scale * 0.72,
            );

            const baseStyle: React.CSSProperties = {
              position: 'absolute',
              left: element.cx - element.w / 2,
              top: element.cy - element.h / 2,
              width: element.w,
              height: element.h,
              overflow: 'hidden',
              borderRadius: element.radius,
              transformOrigin: 'center center',
            };

            return (
              <React.Fragment key={element.key}>
                {ghostVisible ? (
                  <div
                    style={{
                      ...baseStyle,
                      opacity: 0.17 * (1 - linearFlight),
                      filter: 'blur(8px)',
                      transform: `translate(${x + element.dx * 0.08}px, ${
                        y + element.dy * 0.08
                      }px) rotate(${rotation}deg) scale(${scale})`,
                    }}
                  >
                    <ElementVisual element={element} />
                  </div>
                ) : null}

                <div
                  style={{
                    ...baseStyle,
                    opacity: settledOpacity,
                    filter: `saturate(${1 - recede * 0.1}) brightness(${
                      1 - recede * 0.04
                    })`,
                    boxShadow:
                      air > 0.01
                        ? `0 ${12 + air * 30}px ${28 + air * 52}px rgba(15,28,24,${
                            0.12 + air * 0.08
                          })`
                        : '0 18px 42px rgba(15,28,24,.16), 0 2px 8px rgba(15,28,24,.10)',
                    transform: `translate(${x}px, ${y}px) rotate(${rotation}deg) scale(${scale})`,
                  }}
                >
                  <ElementVisual element={element} />
                </div>

                {glow > 0 ? (
                  <div
                    style={{
                      position: 'absolute',
                      left: element.cx - glowRadius,
                      top: element.cy - glowRadius,
                      width: glowRadius * 2,
                      height: glowRadius * 2,
                      borderRadius: 999,
                      background:
                        'radial-gradient(circle, rgba(139,198,183,.72), rgba(29,111,95,0) 70%)',
                      opacity: glow,
                      mixBlendMode: 'multiply',
                    }}
                  />
                ) : null}
              </React.Fragment>
            );
          })}
        </AbsoluteFill>
      </AbsoluteFill>

      {sweepOpacity > 0 ? (
        <div
          style={{
            position: 'absolute',
            left: sweepX - 320,
            top: 0,
            width: 640,
            height: 1080,
            background:
              'linear-gradient(90deg, rgba(139,198,183,0), rgba(139,198,183,.72) 50%, rgba(139,198,183,0))',
            opacity: sweepOpacity,
            mixBlendMode: 'multiply',
            pointerEvents: 'none',
          }}
        />
      ) : null}

      <AbsoluteFill style={{pointerEvents: 'none'}}>
        {SIGNAL_DUST.map((dust, index) => {
          const y = (((dust.y0 - motionFrame * dust.rise) % 1080) + 1080) % 1080;
          const x =
            dust.x +
            Math.sin(motionFrame * dust.frequency + dust.phase) * dust.sway;
          return (
            <div
              key={index}
              style={{
                position: 'absolute',
                left: x,
                top: y,
                width: dust.size,
                height: dust.size,
                borderRadius: 999,
                background: BRAND.primaryHi,
                opacity: dust.opacity,
              }}
            />
          );
        })}
      </AbsoluteFill>

      {stageLight > 0 ? (
        <AbsoluteFill
          style={{
            background:
              'radial-gradient(720px 370px at 50% 48%, rgba(29,111,95,.20), rgba(29,111,95,.07) 52%, rgba(29,111,95,0) 76%)',
            opacity: stageLight,
            pointerEvents: 'none',
          }}
        />
      ) : null}
      {vignette > 0 ? (
        <AbsoluteFill
          style={{
            background:
              'radial-gradient(1380px 870px at 50% 50%, rgba(23,78,68,0) 56%, rgba(23,78,68,.58) 100%)',
            opacity: vignette,
            pointerEvents: 'none',
          }}
        />
      ) : null}

      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
        }}
      >
        <div style={{textAlign: 'center'}}>
          <Img
            src={staticFile('brand/research-mark.svg')}
            style={{
              width: 116,
              height: 116,
              display: 'block',
              margin: '0 auto 30px',
              opacity: markProgress,
              filter: `blur(${(1 - markProgress) * 8}px) drop-shadow(0 20px 28px rgba(23,78,68,.18))`,
              transform: `translateY(${(1 - markProgress) * 28}px) scale(${
                1.26 - markProgress * 0.26
              })`,
            }}
          />
          <div
            style={{
              display: 'flex',
              color: BRAND.text,
              fontSize: 148,
              fontWeight: 760,
              letterSpacing: `${wordSpacing}em`,
              lineHeight: 1,
              textShadow: '0 10px 34px rgba(15,28,24,.18)',
            }}
          >
            {WORDMARK.map((letter, index) => {
              const cue = Math.round(88 + index * 1.6);
              const progress = interpolate(
                motionFrame,
                [cue, cue + 10],
                [0, 1],
                {
                  ...clamp,
                  easing: Easing.bezier(0.2, 0.75, 0.3, 1),
                },
              );
              return (
                <span
                  key={`${letter}-${index}`}
                  style={{
                    display: 'inline-block',
                    opacity: progress,
                    transform: `translateY(${(1 - progress) * 30}px) scale(${
                      1.34 - progress * 0.34
                    })`,
                    filter: `blur(${(1 - progress) * 8}px)`,
                  }}
                >
                  {letter}
                </span>
              );
            })}
          </div>

          <div
            style={{
              position: 'relative',
              width: 280,
              height: 6,
              margin: '38px auto 0',
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: 999,
                background: BRAND.primary,
                boxShadow: '0 0 20px rgba(29,111,95,.24)',
                transform: `scaleX(${rule})`,
              }}
            />
            {ruleExtension > 0 && ruleExtensionOpacity > 0 ? (
              <>
                <div
                  style={{
                    position: 'absolute',
                    top: 2.5,
                    right: '100%',
                    width: 190 * ruleExtension,
                    height: 1,
                    background: BRAND.primaryHi,
                    opacity: ruleExtensionOpacity,
                  }}
                />
                <div
                  style={{
                    position: 'absolute',
                    top: 2.5,
                    left: '100%',
                    width: 190 * ruleExtension,
                    height: 1,
                    background: BRAND.primaryHi,
                    opacity: ruleExtensionOpacity,
                  }}
                />
              </>
            ) : null}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
