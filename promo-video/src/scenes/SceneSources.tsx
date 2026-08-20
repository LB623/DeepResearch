import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {BRAND} from '../theme';

const SOURCES = [
  {
    source: 'Northstar Labs Docs',
    kind: 'DOC',
    title: 'Orion-7 Architecture Overview',
    note: '分层执行、缓存边界与工具路由的架构说明',
  },
  {
    source: 'Vector Systems Blog',
    kind: 'BLOG',
    title: 'Hierarchical Cache Design Notes',
    note: '缓存命中路径、失效策略与回退语义',
  },
  {
    source: 'Open Compute Notes',
    kind: 'NOTE',
    title: 'Runtime Dependency Map',
    note: '运行时依赖、兼容层与供应链边界',
  },
  {
    source: 'Atlas Benchmark',
    kind: 'TEST',
    title: 'Synthetic Reasoning Workload',
    note: '仅用于镜头叙事的虚构合成工作负载',
  },
  {
    source: 'Helix Runtime Brief',
    kind: 'BRIEF',
    title: 'Deployment Compatibility Matrix',
    note: '部署形态、资源约束与回滚路径',
  },
  {
    source: 'Cobalt Systems Review',
    kind: 'REVIEW',
    title: 'Ecosystem Risk Register',
    note: '生态成熟度、锁定风险与替代方案',
  },
  {
    source: 'Aurora Compute Memo',
    kind: 'MEMO',
    title: 'Tool Routing and Retry Semantics',
    note: '工具调用分支、超时处理与确定性重试',
  },
  {
    source: 'Meridian Agent Notes',
    kind: 'NOTE',
    title: 'Citation-ready Evidence Index',
    note: '结论片段、冲突标记与引用位置索引',
  },
] as const;

const FIRST_CUE = 8;
const PER_CARD = 11;
const ENTRY_FRAMES = 6;
const LAST_CUE = FIRST_CUE + (SOURCES.length - 1) * PER_CARD;
const GAP = 52;
const X_OFFSET = 16;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const outCubic = (progress: number) => 1 - Math.pow(1 - progress, 3);
const lerp = (progress: number, from: number, to: number) =>
  from + (to - from) * progress;

export const SceneSources: React.FC = () => {
  // Freeze the card clock at the eighth landing; the remaining 32 frames are true hold.
  const frame = useCurrentFrame();
  const streamFrame = Math.min(frame, LAST_CUE);
  const focus = Math.max(
    0,
    Math.min(
      SOURCES.length - 1,
      Math.floor((streamFrame - FIRST_CUE) / PER_CARD),
    ),
  );
  const processed = Math.max(
    0,
    Math.min(
      SOURCES.length,
      Math.floor((streamFrame - FIRST_CUE) / PER_CARD) + 1,
    ),
  );
  const captionIn = outCubic(clamp01((frame - 4) / 12));
  const gridOffset =
    ((((Math.max(0, streamFrame - FIRST_CUE) / PER_CARD) * GAP) % 44) + 44) %
    44;

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
          inset: -52,
          backgroundImage:
            'linear-gradient(rgba(21,26,25,.055) 1px, transparent 1px)',
          backgroundSize: '100% 44px',
          opacity: 0.55,
          transform: `translateY(${gridOffset}px)`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(90deg, rgba(233,237,235,.94) 0%, rgba(243,245,244,.12) 28%, rgba(243,245,244,.12) 72%, rgba(233,237,235,.94) 100%)',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 126,
          top: 92,
          display: 'flex',
          alignItems: 'flex-end',
          gap: 22,
        }}
      >
        <div>
          <div
            style={{
              color: BRAND.primaryHi,
              fontFamily: BRAND.mono,
              fontSize: 20,
              letterSpacing: '.13em',
            }}
          >
            SOURCE INGEST
          </div>
          <div
            style={{
              marginTop: 8,
              color: BRAND.textSoft,
              fontSize: 24,
              fontWeight: 560,
            }}
          >
            Orion-7 · 虚构研究资料
          </div>
        </div>
        <div
          style={{
            color: BRAND.text,
            fontFamily: BRAND.mono,
            fontSize: 56,
            fontWeight: 680,
            fontVariantNumeric: 'tabular-nums',
            lineHeight: 0.95,
          }}
        >
          {String(processed).padStart(2, '0')}
          <span style={{color: BRAND.weak, fontSize: 30}}> / 08</span>
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 458,
          top: 220,
          width: 0,
          height: 0,
        }}
      >
        {SOURCES.map((source, index) => {
          const cue = FIRST_CUE + index * PER_CARD;
          const elapsed = streamFrame - cue;
          const entry = outCubic(
            clamp01((elapsed + ENTRY_FRAMES) / ENTRY_FRAMES),
          );
          const drift = (Math.max(0, elapsed) / PER_CARD) * GAP;
          const squash = elapsed >= 0 && elapsed < 1.6 ? 0.97 : 1;
          const x = (Math.max(0, elapsed) / PER_CARD) * X_OFFSET;
          const y = lerp(entry, -72, 0) + drift;
          const depth = Math.min(1, drift / (GAP * 3));
          const recycle = clamp01(
            1 - Math.max(0, (drift - GAP * 3.2) / (GAP * 1.6)),
          );
          const opacity =
            elapsed < -ENTRY_FRAMES
              ? 0
              : clamp01((elapsed + ENTRY_FRAMES) / 2) * recycle;
          const isFocus = index === focus;
          const scale = lerp(entry, 0.94, 1);

          return (
            <div
              key={source.title}
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: 1004,
                height: 270,
                overflow: 'hidden',
                background: BRAND.surface,
                border: `1px solid ${
                  isFocus ? 'rgba(29,111,95,.48)' : BRAND.border
                }`,
                borderRadius: 18,
                boxShadow: isFocus
                  ? '0 28px 64px rgba(15,28,24,.18), 0 0 28px rgba(29,111,95,.08)'
                  : '0 20px 48px rgba(15,28,24,.12)',
                boxSizing: 'border-box',
                filter: `blur(${(depth * 12).toFixed(2)}px) brightness(${(
                  1 -
                  depth * 0.24
                ).toFixed(3)})`,
                opacity,
                transform: `translate(${x}px, ${y}px) scale(${scale}, ${
                  scale * squash
                })`,
                transformOrigin: 'top center',
                zIndex: index,
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: 6,
                  background: index % 3 === 1 ? BRAND.primaryHi : BRAND.primary,
                  opacity: index % 3 === 1 ? 0.9 : 0.42,
                }}
              />
              <div
                style={{
                  height: 86,
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0 30px 0 34px',
                  borderBottom: `1px solid ${BRAND.border}`,
                }}
              >
                <div
                  style={{
                    padding: '7px 10px',
                    color: BRAND.primaryHi,
                    background: BRAND.primarySoft,
                    borderRadius: 8,
                    fontFamily: BRAND.mono,
                    fontSize: 15,
                    fontWeight: 650,
                  }}
                >
                  {source.kind}
                </div>
                <div
                  style={{
                    marginLeft: 16,
                    color: BRAND.text,
                    fontSize: 31,
                    fontWeight: 660,
                    letterSpacing: '-0.022em',
                  }}
                >
                  {source.title}
                </div>
                <div
                  style={{
                    marginLeft: 'auto',
                    color: BRAND.muted,
                    fontFamily: BRAND.mono,
                    fontSize: 15,
                  }}
                >
                  DEMO · {String(index + 1).padStart(2, '0')}
                </div>
              </div>

              <div
                style={{
                  padding: '23px 32px 0 34px',
                  opacity: isFocus ? 1 : 0,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    color: BRAND.primaryHi,
                    fontFamily: BRAND.mono,
                    fontSize: 17,
                  }}
                >
                  <span>{source.source}</span>
                  <span style={{color: BRAND.weak}}>·</span>
                  <span style={{color: BRAND.muted}}>FICTIONAL SOURCE</span>
                </div>
                <div
                  style={{
                    marginTop: 14,
                    color: BRAND.textSoft,
                    fontSize: 23,
                    lineHeight: 1.35,
                  }}
                >
                  {source.note}
                </div>
                <div style={{marginTop: 19, display: 'grid', gap: 8}}>
                  {[0, 1, 2].map((line) => {
                    const width = 91 - line * 9 - ((index * 13 + line * 17) % 12);
                    return (
                      <div
                        key={line}
                        style={{
                          width: `${width}%`,
                          height: 7,
                          background:
                            line === 0
                              ? 'rgba(42,139,120,.26)'
                              : 'rgba(21,26,25,.12)',
                          borderRadius: 999,
                        }}
                      />
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 104,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 18,
          color: BRAND.text,
          fontSize: 64,
          fontWeight: 670,
          letterSpacing: '-0.028em',
          lineHeight: 1.12,
          opacity: captionIn,
          transform: `translateY(${9 * (1 - captionIn)}px)`,
        }}
      >
        <span style={{color: BRAND.primaryHi}}>并行检索</span>
        <span style={{color: BRAND.weak}}>·</span>
        <span>持续补足证据</span>
      </div>
    </AbsoluteFill>
  );
};
