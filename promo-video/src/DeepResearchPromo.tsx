import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {AudioLayer} from './AudioLayer';
import {SceneBreath} from './scenes/SceneBreath';
import {SceneOpen} from './scenes/SceneOpen';
import {SceneOutro} from './scenes/SceneOutro';
import {SceneReport} from './scenes/SceneReport';
import {SceneSearch} from './scenes/SceneSearch';
import {SceneSources} from './scenes/SceneSources';
import {SceneWorkflow} from './scenes/SceneWorkflow';
import {BRAND} from './theme';
import {SHOTS} from './timeline';

export type DeepResearchPromoProps = {
  bgm: boolean;
};

export const DeepResearchPromo: React.FC<DeepResearchPromoProps> = ({bgm}) => (
  <AbsoluteFill style={{background: BRAND.bg, fontFamily: BRAND.font}}>
    <AudioLayer bgm={bgm} />
    <Sequence from={SHOTS.open.from} durationInFrames={SHOTS.open.duration}><SceneOpen /></Sequence>
    <Sequence from={SHOTS.search.from} durationInFrames={SHOTS.search.duration}><SceneSearch /></Sequence>
    <Sequence from={SHOTS.sources.from} durationInFrames={SHOTS.sources.duration}><SceneSources /></Sequence>
    <Sequence from={SHOTS.workflow.from} durationInFrames={SHOTS.workflow.duration}><SceneWorkflow /></Sequence>
    <Sequence from={SHOTS.breath.from} durationInFrames={SHOTS.breath.duration}><SceneBreath /></Sequence>
    <Sequence from={SHOTS.report.from} durationInFrames={SHOTS.report.duration}><SceneReport /></Sequence>
    <Sequence from={SHOTS.outro.from} durationInFrames={SHOTS.outro.duration}><SceneOutro /></Sequence>
  </AbsoluteFill>
);
