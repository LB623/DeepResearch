import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import {BRAND, clamp} from '../theme';

export const SceneBreath: React.FC = () => {
  const frame = useCurrentFrame();
  // A non-zero first frame prevents a pure background flash at the cut.
  const reveal = interpolate(frame, [0, 12], [0.35, 1], {
    ...clamp,
    easing: Easing.out(Easing.cubic),
  });

  return (
    <AbsoluteFill
      style={{
        background: BRAND.bg,
        color: BRAND.text,
        fontFamily: BRAND.font,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          width: 1460,
          textAlign: 'center',
          opacity: reveal,
        }}
      >
        <div
          style={{
            fontSize: 98,
            fontWeight: 730,
            letterSpacing: '-0.045em',
            lineHeight: 1.04,
          }}
        >
          搜到，只是开始。
        </div>
        <div
          style={{
            marginTop: 34,
            color: BRAND.textSoft,
            fontSize: 58,
            fontWeight: 530,
            letterSpacing: '-0.025em',
            lineHeight: 1.18,
          }}
        >
          分析、审查、引用校验，接着完成。
        </div>
      </div>
    </AbsoluteFill>
  );
};
