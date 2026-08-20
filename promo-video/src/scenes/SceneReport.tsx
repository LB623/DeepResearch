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
type RevealBlock = Box & {cue: number};
type CameraKey = {frame: number; x: number; y: number; zoom: number};

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
const reportLayout: Record<string, unknown> = isRecord(root.report)
  ? root.report
  : {};
const PAGE_H = Math.max(1080, finite(reportLayout.pageH, 1080));
const documentBox = asBox(reportLayout.document, {
  x: 510,
  y: 104,
  w: 900,
  h: 720,
});
const tableBox = asBox(reportLayout.table, {
  x: documentBox.x + 18,
  y: documentBox.y + documentBox.h * 0.46,
  w: documentBox.w - 36,
  h: documentBox.h * 0.26,
});
const referencesBox = asBox(reportLayout.references, {
  x: documentBox.x + 18,
  y: documentBox.y + documentBox.h * 0.78,
  w: documentBox.w - 36,
  h: documentBox.h * 0.19,
});

const splitRegion = (
  region: Box,
  count: number,
  cueFor: (index: number) => number,
): RevealBlock[] => {
  if (region.h < 4 || count < 1) return [];
  const slice = region.h / count;
  return Array.from({length: count}, (_, index) => ({
    x: region.x - 5,
    y: region.y + index * slice - 2,
    w: region.w + 10,
    h: slice + 4,
    cue: cueFor(index),
  }));
};

const introBottom = Math.max(
  documentBox.y + 100,
  Math.min(tableBox.y, documentBox.y + documentBox.h),
);
const betweenTop = tableBox.y + tableBox.h + 5;
const betweenBottom = Math.max(
  betweenTop,
  Math.min(referencesBox.y - 6, documentBox.y + documentBox.h),
);

// The masks only cover pixels from the captured native report. They do not
// redraw any report UI. Body blocks enter in pairs, then real table rows and
// real citation rows follow on their own slower cadence.
const BLOCKS: RevealBlock[] = [
  ...splitRegion(
    {
      x: documentBox.x,
      y: documentBox.y,
      w: documentBox.w,
      h: introBottom - documentBox.y,
    },
    8,
    // Keep the report title visible on the cut, then reveal the analytical
    // body in paired strips. This avoids an empty-looking document at frame 0.
    (index) =>
      index < 3 ? -12 : 6 + Math.floor((index - 3) / 2) * 5,
  ),
  ...splitRegion(tableBox, 4, (index) => 38 + index * 5),
  ...splitRegion(
    {
      x: documentBox.x,
      y: betweenTop,
      w: documentBox.w,
      h: betweenBottom - betweenTop,
    },
    2,
    (index) => 54 + index * 5,
  ),
  ...splitRegion(referencesBox, 4, (index) => 61 + index * 5),
];

const WIPE = 10;
const REVEAL_EASE = Easing.bezier(0.4, 0, 0.6, 1);
const cameraKeys: CameraKey[] = [
  {
    frame: 0,
    x: documentBox.x + documentBox.w / 2,
    y: documentBox.y + Math.min(250, documentBox.h * 0.32),
    zoom: 1.23,
  },
  {
    frame: 28,
    x: documentBox.x + documentBox.w / 2,
    y: documentBox.y + Math.min(275, documentBox.h * 0.36),
    zoom: 1.25,
  },
  {frame: 90, x: 960, y: PAGE_H / 2, zoom: 0.97},
  {frame: 111, x: 960, y: PAGE_H / 2, zoom: 0.978},
  {frame: 147, x: 960, y: PAGE_H / 2, zoom: 0.97},
];

const cameraAt = (frame: number) => {
  let left = cameraKeys[0];
  let right = cameraKeys[cameraKeys.length - 1];
  for (let index = 0; index < cameraKeys.length - 1; index++) {
    if (frame <= cameraKeys[index + 1].frame) {
      left = cameraKeys[index];
      right = cameraKeys[index + 1];
      break;
    }
  }
  const progress = interpolate(frame, [left.frame, right.frame], [0, 1], {
    ...clamp,
    easing: Easing.bezier(0.33, 0, 0.15, 1),
  });
  return {
    x: left.x + (right.x - left.x) * progress,
    y: left.y + (right.y - left.y) * progress,
    zoom: left.zoom + (right.zoom - left.zoom) * progress,
  };
};

export const SceneReport: React.FC = () => {
  const frame = useCurrentFrame();
  const camera = cameraAt(frame);
  // Establish the real report on the cut; only the last 15% eases in.
  const pageIn = interpolate(frame, [0, 14], [0.85, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  const captionIn = interpolate(frame, [8, 20], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });
  // The caption clears before the full-page hold so the native input area is
  // unobstructed and the complete captured product remains visible.
  const captionOut = interpolate(frame, [98, 112], [1, 0], clamp);

  let caretIndex = -1;
  BLOCKS.forEach((block, index) => {
    if (frame >= block.cue && frame <= block.cue + WIPE + 2) {
      caretIndex = index;
    }
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
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: 1920,
          height: PAGE_H,
          opacity: pageIn,
          transformOrigin: '0 0',
          transform: `translate(${960 - camera.x * camera.zoom}px, ${
            540 - camera.y * camera.zoom
          }px) scale(${camera.zoom})`,
        }}
      >
        <Img
          src={staticFile('textures/live/report-full.png')}
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: 1920,
            height: PAGE_H,
            display: 'block',
          }}
        />

        {BLOCKS.map((block, index) => {
          const cover = interpolate(
            frame,
            [block.cue, block.cue + WIPE],
            [1, 0],
            {...clamp, easing: REVEAL_EASE},
          );
          const caretX = block.x + block.w * (1 - cover);
          const coverX = block.x + block.w * (1 - cover);
          const caretOpacity =
            cover > 0
              ? 1
              : interpolate(
                  frame,
                  [block.cue + WIPE, block.cue + WIPE + 2],
                  [1, 0],
                  clamp,
                );

          return (
            <React.Fragment key={`${block.x}-${block.y}-${index}`}>
              {cover > 0 ? (
                <div
                  style={{
                    position: 'absolute',
                    left: coverX,
                    top: block.y,
                    width: block.w * cover,
                    height: block.h,
                    overflow: 'hidden',
                    pointerEvents: 'none',
                  }}
                >
                  <Img
                    src={staticFile('textures/live/report-blank-full.png')}
                    style={{
                      position: 'absolute',
                      left: -coverX,
                      top: -block.y,
                      width: 1920,
                      height: PAGE_H,
                      maxWidth: 'none',
                    }}
                  />
                </div>
              ) : null}

              {index === caretIndex ? (
                <div
                  style={{
                    position: 'absolute',
                    left: caretX,
                    top: block.y + 3,
                    width: 3,
                    height: Math.max(14, block.h - 6),
                    borderRadius: 2,
                    background: BRAND.primary,
                    boxShadow: '0 0 12px rgba(29,111,95,.38)',
                    opacity: caretOpacity,
                    pointerEvents: 'none',
                  }}
                />
              ) : null}
            </React.Fragment>
          );
        })}
      </div>

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: 250,
          background:
            'linear-gradient(0deg, rgba(243,245,244,.99) 0%, rgba(243,245,244,.84) 48%, rgba(243,245,244,0) 100%)',
          opacity: captionIn * captionOut,
          pointerEvents: 'none',
          zIndex: 1,
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
          zIndex: 2,
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
        数据分析 · 把资料压成结构化洞察
      </div>
    </AbsoluteFill>
  );
};
