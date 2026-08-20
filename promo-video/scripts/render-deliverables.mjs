#!/usr/bin/env node

import {spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, unlinkSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const out = path.join(root, 'out');
const remotion = path.join(root, 'node_modules/.bin/remotion');

const browserCandidates = [
  process.env.REMOTION_BROWSER_EXECUTABLE,
  path.join(
    os.homedir(),
    'Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell',
  ),
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean);

const browser = browserCandidates.find((candidate) => existsSync(candidate));
if (process.env.REMOTION_BROWSER_EXECUTABLE && !browser) {
  throw new Error(
    `REMOTION_BROWSER_EXECUTABLE does not exist: ${process.env.REMOTION_BROWSER_EXECUTABLE}`,
  );
}

const run = (command, args) => {
  const result = spawnSync(command, args, {cwd: root, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} exited with status ${result.status}`);
  }
};

const render = (output, props) => {
  const args = [
    'render',
    'src/index.ts',
    'DeepResearchPromo',
    output,
    '--codec=h264',
    '--crf=18',
    '--audio-codec=aac',
    '--audio-bitrate=192k',
  ];
  if (props) args.push(`--props=${props}`);
  if (browser) args.push(`--browser-executable=${browser}`);
  run(remotion, args);
};

mkdirSync(out, {recursive: true});

const bgmRaw = path.join(out, 'deepresearch-promo-bgm.raw.mp4');
const noBgmRaw = path.join(out, 'deepresearch-promo-no-bgm.raw.mp4');
const bgmFinal = path.join(out, 'deepresearch-promo-bgm.mp4');
const noBgmFinal = path.join(out, 'deepresearch-promo-no-bgm.mp4');

render(bgmRaw);
render(noBgmRaw, 'props-nobgm.json');

const exactAudio = ['-c:a', 'aac', '-b:a', '192k', '-af', 'atrim=duration=30,asetpts=N/SR/TB'];
run('ffmpeg', [
  '-hide_banner',
  '-loglevel',
  'error',
  '-i',
  bgmRaw,
  '-map',
  '0:v:0',
  '-map',
  '0:a:0',
  '-c:v',
  'copy',
  ...exactAudio,
  '-t',
  '30',
  '-movflags',
  '+faststart',
  '-y',
  bgmFinal,
]);
run('ffmpeg', [
  '-hide_banner',
  '-loglevel',
  'error',
  '-i',
  bgmRaw,
  '-i',
  noBgmRaw,
  '-map',
  '0:v:0',
  '-map',
  '1:a:0',
  '-c:v',
  'copy',
  ...exactAudio,
  '-t',
  '30',
  '-movflags',
  '+faststart',
  '-y',
  noBgmFinal,
]);

unlinkSync(bgmRaw);
unlinkSync(noBgmRaw);

