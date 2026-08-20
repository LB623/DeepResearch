import React from 'react';
import {Composition} from 'remotion';
import {DeepResearchPromo, type DeepResearchPromoProps} from './DeepResearchPromo';
import {DURATION_IN_FRAMES, FPS} from './timeline';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="DeepResearchPromo"
    component={DeepResearchPromo}
    durationInFrames={DURATION_IN_FRAMES}
    fps={FPS}
    width={1920}
    height={1080}
    defaultProps={{bgm: true} satisfies DeepResearchPromoProps}
  />
);
