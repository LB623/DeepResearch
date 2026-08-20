import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import {BRAND, clamp} from '../theme';

const ROW_CUES = [42, 53, 63, 72, 80, 87, 93, 98] as const;
const ROWS = [
  {title: 'Northstar Labs Docs', detail: '架构说明 · 3 段证据'},
  {title: 'Vector Systems Blog', detail: '缓存策略 · 2 段证据'},
  {title: 'Open Compute Notes', detail: '运行时依赖 · 4 段证据'},
  {title: 'Atlas Benchmark', detail: '合成基准 · 5 段证据'},
  {title: 'Helix Runtime Brief', detail: '部署约束 · 2 段证据'},
  {title: 'Cobalt Systems Review', detail: '生态风险 · 3 段证据'},
  {title: '交叉来源一致性', detail: '冲突 1 项 · 已标记'},
  {title: '引用覆盖检查', detail: '结论均已绑定来源'},
] as const;

const ease = Easing.bezier(0.2, 0.75, 0.25, 1);

const CheckIcon: React.FC<{progress: number}> = ({progress}) => {
  const ringOpacity = interpolate(
    progress,
    [0, 0.45, 0.75],
    [0.34, 1, 0],
    clamp,
  );
  const checkOpacity = interpolate(progress, [0.62, 1], [0, 1], clamp);
  const checkScale = interpolate(progress, [0.62, 1], [0.72, 1], {
    ...clamp,
    easing: ease,
  });

  return (
    <div style={{position: 'relative', width: 28, height: 28, flex: '0 0 auto'}}>
      <div
        style={{
          position: 'absolute',
          inset: 2,
          border: `2px solid rgba(42,139,120,${ringOpacity})`,
          borderTopColor: BRAND.primaryHi,
          borderRadius: 999,
          opacity: ringOpacity,
          transform: `rotate(${progress * 100}deg)`,
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: 1,
          display: 'grid',
          placeItems: 'center',
          background: BRAND.primary,
          borderRadius: 999,
          boxShadow: '0 0 17px rgba(29,111,95,.18)',
          opacity: checkOpacity,
          transform: `scale(${checkScale})`,
        }}
      >
        <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
          <path
            d="M3.4 8.3 6.6 11l6-6"
            stroke={BRAND.primaryForeground}
            strokeWidth="2.1"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
};

const EvidenceRow: React.FC<{
  cue: number;
  title: string;
  detail: string;
  index: number;
}> = ({cue, title, detail, index}) => {
  // This inherits the enclosing SceneSearch Sequence's local frame context.
  const frame = useCurrentFrame();
  const body = interpolate(frame, [cue, cue + 12], [0, 1], {
    ...clamp,
    easing: ease,
  });
  const status = interpolate(frame, [cue + 3, cue + 11], [0, 1], {
    ...clamp,
    easing: ease,
  });

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: index * 56,
        height: 49,
        display: 'flex',
        alignItems: 'center',
        gap: 15,
        padding: '0 18px',
        border: `1px solid ${BRAND.border}`,
        borderRadius: 10,
        background: 'rgba(255,255,255,.72)',
        boxSizing: 'border-box',
        filter: `blur(${6 * (1 - body)}px)`,
        opacity: body,
        transform: `translateY(${18 * (1 - body)}px)`,
      }}
    >
      <CheckIcon progress={status} />
      <div
        style={{
          flex: 1,
          color: BRAND.text,
          fontSize: 22,
          fontWeight: 560,
          letterSpacing: '-0.01em',
        }}
      >
        {title}
      </div>
      <div
        style={{
          color: status > 0.78 ? BRAND.primaryHi : BRAND.weak,
          fontFamily: BRAND.mono,
          fontSize: 17,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {detail}
      </div>
    </div>
  );
};

export const SceneSearch: React.FC = () => {
  // SceneSearch is mounted in SHOTS.search's Sequence; frame 0 is this shot's cut.
  const frame = useCurrentFrame();
  const panelIn = interpolate(frame, [0, 16], [0, 1], {
    ...clamp,
    easing: ease,
  });
  const summaryIn = interpolate(frame, [18, 30], [0, 1], {
    ...clamp,
    easing: ease,
  });
  const camera = interpolate(frame, [0, 100], [1.025, 1], {
    ...clamp,
    easing: Easing.inOut(Easing.quad),
  });
  const pulse = interpolate(frame, [115, 120, 125], [0, 1, 0], clamp);
  const complete = interpolate(frame, [111, 121], [0, 1], {
    ...clamp,
    easing: ease,
  });
  const captionIn = interpolate(frame, [8, 18], [0, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
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
          backgroundImage:
            'radial-gradient(circle at 50% 42%, rgba(29,111,95,.10), transparent 58%), linear-gradient(rgba(21,26,25,.028) 1px, transparent 1px), linear-gradient(90deg, rgba(21,26,25,.028) 1px, transparent 1px)',
          backgroundSize: 'auto, 72px 72px, 72px 72px',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: 232,
          top: 54,
          width: 1456,
          height: 864,
          overflow: 'hidden',
          background: 'rgba(250,251,250,.985)',
          border: `1px solid rgba(29,111,95,${0.18 + pulse * 0.45})`,
          borderRadius: 24,
          boxShadow: `0 44px 100px rgba(15,28,24,.16), 0 0 ${42 * pulse}px rgba(29,111,95,${0.13 * pulse})`,
          boxSizing: 'border-box',
          opacity: panelIn,
          transform: `translateY(${12 * (1 - panelIn)}px) scale(${(
            (0.985 + 0.015 * panelIn) *
            camera
          ).toFixed(5)})`,
          transformOrigin: 'center',
        }}
      >
        <div
          style={{
            height: 74,
            display: 'flex',
            alignItems: 'center',
            padding: '0 30px',
            borderBottom: `1px solid ${BRAND.border}`,
          }}
        >
          <Img
            src={staticFile('brand/research-mark.svg')}
            style={{
              width: 32,
              height: 32,
              borderRadius: 9,
            }}
          />
          <div style={{marginLeft: 13, fontSize: 23, fontWeight: 650}}>
            DeepResearch
          </div>
          <div
            style={{
              marginLeft: 13,
              padding: '5px 10px',
              color: BRAND.primaryHi,
              background: BRAND.primarySoft,
              borderRadius: 999,
              fontFamily: BRAND.mono,
              fontSize: 15,
            }}
          >
            AI SEARCH
          </div>
          <div
            style={{
              marginLeft: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: 9,
              color: BRAND.muted,
              fontFamily: BRAND.mono,
              fontSize: 15,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                background: BRAND.primary,
                borderRadius: 999,
              }}
            />
            DEMO DATA · FICTIONAL
          </div>
        </div>

        <div style={{padding: '22px 32px 30px'}}>
          <div
            style={{
              height: 58,
              display: 'flex',
              alignItems: 'center',
              padding: '0 18px',
              color: BRAND.textSoft,
              background: BRAND.surface,
              border: `1px solid ${BRAND.border}`,
              borderRadius: 18,
              fontSize: 21,
            }}
          >
            <span style={{color: BRAND.primaryHi, fontFamily: BRAND.mono, marginRight: 13}}>
              &gt;
            </span>
            研究 Orion-7 推理引擎的架构取舍与生态风险
          </div>

          <div
            style={{
              position: 'relative',
              height: 116,
              marginTop: 18,
              overflow: 'hidden',
              borderBottom: `1px solid ${BRAND.border}`,
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                clipPath: `inset(0 ${100 * (1 - summaryIn)}% 0 0)`,
                opacity: summaryIn,
                transform: `translateY(${10 * (1 - summaryIn)}px)`,
              }}
            >
              <div
                style={{
                  marginBottom: 9,
                  color: BRAND.primaryHi,
                  fontFamily: BRAND.mono,
                  fontSize: 15,
                  letterSpacing: '.12em',
                }}
              >
                RESULT SUMMARY
              </div>
              <div
                style={{
                  color: BRAND.text,
                  fontSize: 27,
                  fontWeight: 570,
                  letterSpacing: '-0.022em',
                  lineHeight: 1.36,
                }}
              >
                分层缓存降低了工具调用开销；生态成熟度与依赖锁定仍需重点核验。
              </div>
            </div>
          </div>

          <div style={{position: 'relative', height: 441, marginTop: 14}}>
            {ROWS.map((row, index) => (
              <EvidenceRow
                key={row.title}
                cue={ROW_CUES[index]}
                title={row.title}
                detail={row.detail}
                index={index}
              />
            ))}
          </div>

          <div
            style={{
              height: 51,
              display: 'flex',
              alignItems: 'flex-end',
              borderTop: `1px solid ${BRAND.border}`,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 11,
                opacity: complete,
                transform: `translateY(${5 * (1 - complete)}px)`,
              }}
            >
              <div
                style={{
                  width: 25,
                  height: 25,
                  display: 'grid',
                  placeItems: 'center',
                  background: BRAND.primary,
                  borderRadius: 999,
                }}
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M3.4 8.3 6.6 11l6-6"
                    stroke={BRAND.primaryForeground}
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <span style={{color: BRAND.text, fontSize: 18, fontWeight: 620}}>
                搜索与校验完成
              </span>
              <span style={{color: BRAND.muted, fontSize: 16}}>
                6 个来源 · 2 项核验 · 引用已绑定
              </span>
            </div>
          </div>
        </div>
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
        <span style={{color: BRAND.primaryHi}}>AI 搜索</span>
        <span style={{color: BRAND.weak}}>·</span>
        <span>结论先到，证据随后</span>
      </div>
    </AbsoluteFill>
  );
};
