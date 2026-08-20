# DeepResearch 最新 App 宣传片独立交付审计

审计对象：`promo-video/`

审计时间：2026-08-13 10:38–10:46（Asia/Shanghai）

审计口径：对下列冻结 MP4 重新读取、重新解码和重新计算，不使用旧 manifest 或旧 QA 图片作结论；只写本报告，并按审计要求更新 `analysis/rendered-music/` 的 BGM 隔离与同步验证产物。

## 结论

**PASS。当前冻结双版本满足本次强制媒体、音频、切点、数据安全和交付条件，可交付。**

- 当前 blocker：**0**
- 建议优化项：**0**
- 无法验证项：**0**
- 审计深度：deep / fresh decode

最终冻结文件：

| 文件 | 大小 | mtime | SHA-256 |
|---|---:|---|---|
| `out/deepresearch-promo-bgm.mp4` | 9,225,968 B | 2026-08-13 10:37:35 | `1af85bf5b4a7d854edfe2c41c2c78b57a03b5ece9873f070dd9ed537cdfe658e` |
| `out/deepresearch-promo-no-bgm.mp4` | 8,894,795 B | 2026-08-13 10:37:36 | `3e28c9ebae9e8e76ecd87336ba938e671311b651d07c79fd2c4ccae628b36bad` |

## 强制验收结果

| 验收项 | 结果 | Fresh 证据 |
|---|---|---|
| 规格 | PASS | 两版 container、video、audio 均为 `30.000000s`；H.264 High、`1920×1080`、`30/1 fps`、`900` 个可读视频帧；AAC LC、48 kHz、stereo |
| 完整解码 | PASS | 两版分别以 `ffmpeg -xerror` 同时映射视频与音频完整解码，均 exit 0，错误/损坏诊断 0 |
| 两版画面一致 | PASS | H.264 elementary stream SHA-256 均为 `77b55f7e1b61463de0361b39335a163c528edf41de383fb5e21e2d78cc2fc608`；decoded 900-frame `framemd5` manifest SHA-256 均为 `7478e0a2b77a6079b33836b0ef11919ccd1e9eda99364f4d766f9b31369bcccc`；`cmp` 均通过 |
| BGM / no-BGM 音频不同 | PASS | 解码 stereo/48k/s24le PCM SHA-256：BGM `adba597227d320d5447c9de31f41f677d944c31da8b287936f68adae19843f09`；no-BGM `13ea64b9cea666af30617c92ff321d2d4ae3518fa929645fcb28899f62cb1a83` |
| no-BGM 保留 SFX | PASS | `AudioLayer.tsx` 只条件挂载 BGM，15 条 SFX cue 始终挂载；no-BGM 音轨非静音，`-50 dB / 150 ms` 检测到 11 个非静音声簇，且 true peak `-7.1 dBFS` |
| 黑帧 / 空帧 | PASS | 900 帧 `signalstats + entropy` 全量扫描：严格纯色 `0`、RGB 各通道 span≤2 的 near-flat `0`、YAVG≤16/32 的黑/近黑 `0/0`、Y entropy<0.05 为 `0`；`blackdetect=pix_th=.10:pic_th=.98:d=0` 区间 `0` |
| 全部指定切点 | PASS | f0/118/265/383/531/590/738 均有非空内容，详见下表；八个抽样帧 `cropdetect` 均为 `1920:1080:0:0` |
| 首帧品牌可见 | PASS | f0 已清楚显示正式 `research-mark.svg` 与完整 `DeepResearch` 字标；Y range `37–255`，不是淡网格或空底 |
| f590 报告首帧 | PASS | f590 已清楚显示 `Orion-7 推理引擎：架构取舍与生态风险`、`DEMO DATA · FICTIONAL`，以及“以下实体、资料与结论全部为虚构数据”的中文演示说明；Y range `33–255` |
| 最终定帧稳定 | PASS | 源码从 outro local f130 冻结所有 motion；全片 f868–899 的最大逐帧 Y/U/V 差分别仅 `0.00715 / 0.000274 / 0.00210`，为 H.264 帧间量化波动；抽看 f870/f888/f899 构图稳定、无跳变 |
| 音频响度 / 峰值 / 削波 | PASS | BGM：I `-22.8 LUFS`、LRA `4.1 LU`、true/sample peak `-5.8 dBFS`；no-BGM：I `-26.5 LUFS`、LRA `14.8 LU`、true/sample peak `-7.1 dBFS`；解码浮点样本达到/超过 1.0 的数量均为 `0`，NaN/Inf/denormal 均为 `0` |
| Rendered BGM 同步 | PASS | 由当前冻结双版实时作 `BGM - no-BGM` 重生隔离轨；expected source offset `0.0666667s`、measured `0.0243333s`、绝对误差 `0.0423333s = 1.27f`，低于 video-shotcraft 强节奏片 `≤3f` 门槛；correlation `0.999447` |
| 数据虚构 / 脱敏 | PASS | 成片固定使用虚构 `Orion-7`、虚构来源和 `.example.invalid` 引用；搜索、工作流、报告采集页均有 `DEMO DATA · FICTIONAL`；报告首帧另有中文虚构说明 |
| 无外部数据泄露 | PASS | capture manifest 证明三页 `unexpectedLinks=[]`、网络策略为 loopback harness + in-process model fixture，模型 fixture 2 次；15 个资产 hash 与磁盘完全一致，14 个采集源 hash 自采集后无变化；凭据、邮箱、手机号、身份证模式扫描无命中 |
| 品牌与当前 App | PASS | capture page proof 三页均为当前浅色主题：background `#f3f5f4`、primary `#1d6f5f`、`colorScheme=light`，正式图标 32×32；f0 与 f590 抽帧复核一致 |
| 真实组件边界 | PASS | 产品页由当前 `WelcomeScreen`、`InputForm`、`ActivityTimeline`、`ChatMessagesView` 渲染；未虚构 BI dashboard 或 workflow builder；12 个采集框全部在 1920×1080 内 |
| 音频授权 / 资产完整性 | PASS | 使用的 1 个 BGM + 10 个唯一 SFX 共 11 项，磁盘存在 11/11、可解码 11/11、归因表覆盖 11/11、与 video-shotcraft 源 catalog 逐文件 SHA 匹配 11/11 |
| 工程类型门禁 | PASS | `npm run typecheck` 同时执行 video 与 capture harness TypeScript 检查，exit 0；旧版 capture 未纳入 typecheck 的缺口已消除 |

## 切点逐帧证据

以下值来自当前 BGM 冻结版的解码帧；两版 decoded video manifest 完全相同，因此同时覆盖 no-BGM 版。

| Frame | 时间 | 场景 | YMIN–YMAX | YAVG | normalized Y entropy | 与前帧 YDIF | 结论 |
|---:|---:|---|---:|---:|---:|---:|---|
| 0 | 0.000s | 正式品牌锁定 | 37–255 | 240.698 | 0.508941 | 0 | logo + 字标首帧可见 |
| 118 | 3.933s | AI 搜索 | 211–240 | 232.243 | 0.423032 | 18.6749 | 页面面板与字幕起始可见 |
| 265 | 8.833s | 来源吞吐 | 0–255 | 236.239 | 0.171275 | 16.3941 | `SOURCE INGEST` / `00 / 08` 与虚构主题可见 |
| 383 | 12.767s | 自动化工作流 | 38–255 | 240.988 | 0.419143 | 14.2391 | 真实 workflow 页面首帧可见 |
| 531 | 17.700s | 呼吸字卡 | 150–255 | 242.442 | 0.054548 | 9.98886 | 淡入中的字卡轮廓可见，非纯色 |
| 590 | 19.667s | 数据分析报告 | 33–255 | 245.395 | 0.194121 | 9.58391 | 标题、虚构标签与演示说明即时可见 |
| 738 | 24.600s | 功能合影收尾 | 214–247 | 237.823 | 0.342493 | 10.3298 | 多个真实组件卡片已在首帧可见 |
| 899 | 29.967s | 最终 sign-off | 0–255 | 227.404 | 0.542420 | 0.000479 | 正式 logo/字标/绿线与功能合影稳定 |

`cropdetect=limit=24` 对 f0、118、265、383、531、590、738、899 均返回 `1920:1080:0:0`。这证明没有黑边；关键内容是否裁断另以 1920×1080 原始抽帧人工复核，未见非预期裁断。

## 音频与同步证据

### 双版与 SFX

- 两版均含 30.000 秒 AAC LC、48 kHz、stereo 音轨。
- 两版 PCM hash 不同，排除“误交同一音轨”。
- no-BGM 在开场、搜索、资料汇入、四次工作流点击、报告写入和 outro 均出现非静音事件；与 `AudioLayer.tsx` 的 cue sheet 一致。
- BGM 版没有 `-50 dB / 150 ms` 静音区间；no-BGM 的间歇静音符合“只保留动作 SFX”的交付定义，不是全静音或丢轨。

### BGM render-sync

本轮已由当前冻结 MP4 重生：

- `analysis/rendered-music/rendered-bgm-isolated.wav`：30.000 秒、stereo、48 kHz、PCM s24le；文件 SHA-256 `27b15d119339e58adf01a55d1a2ddc13befadeac70504df51a0eb922a03ac2da`。
- 隔离轨解码 PCM SHA-256 `6ec5d4b3b3f85b32987b17416accb4550a4a8d99d07765d39aa3e70d3b7b04aa`，与对当前 MP4 重新执行同一 float mix `BGM - no-BGM` 的结果一致。
- `analysis/rendered-music/render-sync.json`：SHA-256 `80ecb93e4701db870c02d838ce41dfd7e44ea6763c2998d528e46302e4598fd8`；error `1.27f`、correlation `0.999447`。
- `source-bgm.wav` 与当前 `public/audio/bgm/house-vibez.mp3` 的 mono/48k/s24le PCM SHA-256 均为 `fc881f5152a7bec00d6381585118af4ecd881cbdfe6ea26b764cf7276da2f05e`。

## 数据与网络安全证据

当前 capture manifest（`src/live-layout.json`）记录：

```text
fixture: fictional-orion-7
frontendTheme: light-gray-green
networkPolicy: loopback-harness-and-in-process-model-fixture-only
modelFixtureRequests: 2
search/workflow/report demoMarker: true / true / true
search/workflow/report fictionalCopy: true / true / true
search/workflow/report unexpectedLinks: [] / [] / []
captured assets: 15，manifest mismatch: 0
captured source files: 14，changed since capture: 0
layout boxes: 12，out of bounds: 0
```

采集代码只放行 `127.0.0.1:4179` 本地 harness，并在浏览器拦截器中对 `localhost:2024/api/models` 直接返回固定虚构响应；其余请求全部 `abort("blockedbyclient")`。报告内三条 URL 使用保留域 `.example.invalid`，没有真实公司域名或在线请求。固定数据只有虚构产品名、来源名、查询数和资料数，不包含客户、个人、凭据、内网地址或实时结果。

## 审计产物时效说明

- 本报告只认上述 `1af85b…` / `3e28c9…` 两个冻结 hash。
- `/tmp/latest2-*` 为本轮临时 fresh decode / metrics / frame evidence，不是交付依赖。
- `out/qa/bgm.framemd5`、`out/qa/no-bgm.framemd5` 和部分旧 contact sheet 的 mtime 为 2026-08-12，属于上版 QA 遗留；本报告没有使用它们。当前结论来自直接解码冻结 MP4 得到的 `/tmp/latest2-*.framemd5`、全量 metrics 和原始 f0/f590/f899 抽帧。
- `analysis/rendered-music/rendered-bgm-isolated.wav` 与 `render-sync.json` 已于 2026-08-13 10:39:57–10:39:58 按当前冻结重生，可作为当前同步证据。

## 命令级复核摘要

```bash
sha256sum out/deepresearch-promo-{bgm,no-bgm}.mp4

ffprobe -v error -show_format -show_streams -count_frames -of json <mp4>

ffmpeg -v info -xerror -i <mp4> -map 0:v:0 -map 0:a:0 -f null -

ffmpeg -v error -i <mp4> -map 0:v:0 -an -f framemd5 /tmp/current.framemd5

ffmpeg -v error -i out/deepresearch-promo-bgm.mp4 \
  -vf 'signalstats,entropy,metadata=print:file=/tmp/current-metrics.txt' \
  -an -f null -

ffmpeg -v info -i out/deepresearch-promo-bgm.mp4 \
  -vf 'blackdetect=d=0:pic_th=0.98:pix_th=0.10' -an -f null -

ffmpeg -v info -i <mp4> -af 'ebur128=peak=true' -f null -
ffmpeg -v info -i <mp4> -af 'astats=metadata=1:reset=0' -f null -

python3 scripts/verify_rendered_bgm.py \
  analysis/rendered-music/source-bgm.wav \
  analysis/rendered-music/rendered-bgm-isolated.wav \
  --expected-offset 0.06666666666666667 --fps 30 \
  --output analysis/rendered-music/render-sync.json

npm run typecheck
```

## 最终交付状态

```text
status:             PASS，可交付
current blockers:   0
frozen hashes:      1af85bf5… / 3e28c9eb…
video spec:         1920x1080 / 30fps / 30.000s / 900f
video parity:       packet stream PASS / decoded framemd5 PASS
blank-black scan:   flat 0 / near-flat 0 / black 0
f0 brand:           PASS
f590 report intro:  PASS（标题 + DEMO 标签 + 中文虚构说明）
audio:              双版有声、no-BGM 保留 SFX、无削波
render-sync:        1.27f <= 3f PASS
privacy/network:    fictional fixture + isolated capture PASS
```
