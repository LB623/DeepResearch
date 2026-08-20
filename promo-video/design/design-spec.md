# DeepResearch Developer Promo — Design Spec（2026-08-13 最新 App 重生成片）

## 0. 制作口径

- 模式：video-shotcraft / 自主自由创作。
- 目标项目：当前 DeepResearch 仓库。用户给出的 `/绝对路径/my-app` 是不存在的占位路径；当前仓库的产品定位与指定功能完全吻合，因此将其作为目标项目。
- 当前品牌基准：以 2026-08-13 工作区内 `frontend/src/` 与 `frontend/public/research-mark.svg` 为唯一视觉事实源；2026-08-12 凌晨冻结的深灰/蓝色截图、styleframe 与成片不再作为品牌基准。
- 片种：面向开发者的产品宣传片。
- 交付：30 秒，16:9，1920×1080，30fps；带 BGM 与无 BGM（保留 SFX）各一版。
- 语言：中文界面与中文短字幕；保留产品名和必要的开发者术语。
- 数据：只使用虚构演示数据。不得采集真实查询、客户、个人、内部、凭据、实时服务响应或未公开评测结果。
- 实现边界：视频工程完全隔离在 `promo-video/`；不修改业务前后端，不运行 `backend/eval/` 的付费评测。

## 1. 产品简报

DeepResearch 是基于 LangGraph 的多阶段深度研究 Agent。产品把一个开放问题转成可确认的研究计划，再执行查询生成、并行搜索、证据充分性检查与补充检索，并通过提纲、草稿、审稿和引用润色生成可追溯报告。宣传片面向熟悉 Agent、RAG、工作流与数据工程的开发者，不解释 AI 基础概念，重点证明“计划可确认、过程可见、研究链路自动推进、结果可核验”。它不是通用自动化或 BI 平台；片中“数据分析”严格落到证据比较、信息缺口识别和结构化报告。

### 必须展示

1. AI 搜索：从问题输入到多路检索与证据汇入。
2. 自动化工作流：计划确认、查询生成、搜索、证据审查、写作与引用润色形成连续链路。
3. 数据分析：把虚构资料压缩为可读结论、对比表与带来源的结构化报告。

### 不应暗示

- 不展示当前产品没有的拖拽式工作流编辑器或独立 BI 仪表盘。
- 不使用真实公司、人物、客户、内部研究主题或在线服务返回值。
- 不宣称未被仓库证据支持的准确率、速度、成本或商业成绩。

## 2. 需求到执行决策

| 用户要求 | 执行决策 | 验收证据 |
|---|---|---|
| 面向开发者 | 用计划确认、查询生成、并行搜索、证据缺口、审稿与引用润色等开发者可读语汇；避免消费级拟人包装 | 字幕与画面均能在静帧中读清 |
| AI 搜索 | 捕获当前 `InputForm` / `ActivityTimeline` 的真实组件样式，注入虚构问题、查询与来源 | 搜索镜头和证据镜头各自提供新信息 |
| 自动化工作流 | 用当前 `ActivityTimeline` 的真实视觉语言表达连续研究阶段，不伪造画布编辑器 | 节点口径与 `backend/src/agent/graph.py`、research/writer 子图一致 |
| 数据分析 | 用当前 `ChatMessagesView` 的 Markdown 报告、对比表、结论与引用表达，不伪造产品外的 BI 页面或内部质量分数 | 分析镜头标注“虚构演示数据” |
| 30 秒 1080p | 900 帧、1920×1080、30fps | ffprobe 检查时长、分辨率、帧率 |
| 沿用品牌 | 以当前 CSS tokens、正式 `research-mark.svg`、浅色页面和真实组件为准；旧深灰蓝方案全部退役 | styleframe 与 2026-08-13 前端截图并排核对 |
| 双音频版 | 同一 Composition 通过 `bgm` input prop 开关 BGM，SFX 始终保留 | 两版视频时长和画面哈希一致 |

## 3. 视觉方向

### 候选方向

1. **Misted Evidence Desk（选定）**：浅雾灰工作台、墨色正文、森林绿研究信号；以当前真实页面和编辑式报告排版为主，镜头克制推进。
2. Forest Console：加深森林绿表面、提高开发工具感；功能段对比强，但大面积深色会偏离当前 App 的默认浅色界面。
3. Editorial Paper：进一步强化白纸与报告版式；适合结论段，但会削弱搜索和过程状态的产品感。

选择 Misted Evidence Desk。成片保留原 30 秒镜头结构、节拍锚点和运动语法，但所有页面纹理、字幕配色、开场/片尾品牌锁定和抽象卡片统一换成最新 App 的浅雾灰、森林绿与墨色。电影感来自层次阴影、局部推近、清晰停留与音画节奏；不再使用旧方案的近黑舞台、蓝色信号光或假花括号标识。

### 品牌 tokens

| 语义 | Token |
|---|---|
| 正式品牌图标 | `frontend/public/research-mark.svg`；32×32 画板、9px 图标圆角，墨绿底 `#174E44`，浅绿/白色折线与节点；禁止用 `{}` 或自绘替代 logo |
| UI 字体 | `"SF Pro Display", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif` |
| 数据字体 | `"SFMono-Regular", "Cascadia Code", "Roboto Mono", "PingFang SC", monospace` |
| 页面背景 / 浅雾灰 | `#F3F5F4` |
| 主文字 / 墨色 | `#151A19` |
| 卡片 | `#FAFBFA`；popover 为 `#FFFFFF` |
| 主操作 / 森林绿 | `#1D6F5F`；其前景文字 `#F7FBFA` |
| 深绿强调 | `#174E44`；仅用于图标底、强调文字和克制的暗部延展 |
| 次级表面 | `#E9EDEB`，次级文字 `#202725` |
| muted 表面 | `#E4E9E7`，muted 文字 `#68736F` |
| accent 表面 | `#E3ECE8`，accent 文字 `#174E44` |
| 边框 / 输入边 | `#D8DEDB` / `#CCD5D1` |
| 错误状态 | `#B4443C`；不作为装饰色 |
| 基础圆角 | `--radius: 12px`；常规卡片/输入按当前 `rounded-2xl`（16px）与 `rounded-lg`（8px）组合；胶囊 999px |
| 栅格 | 8px 基准；App header / welcome 最大宽度 1080px，研究记录 1040px，输入 dock 960px，中心对齐 |
| 材质 | 浅色哑光表面、1px 实色边、柔和低扩散阴影；header / composer dock 只使用当前 18px backdrop blur，不新增玻璃霓虹 |

### 动效性格 tokens

- 能量轴：中低 → 中高；调性轴：专业、理性、可信。
- 主入场：18–24f，`cubic-bezier(0, 0, 0.2, 1)`，不弹。
- 实体落位：只在有明确物理归位时使用低过冲 spring，最大视觉 overshoot 1.03。
- 相机：单向、缓进缓出；默认无 shake；大动作全片不超过两次。
- 落定 hold：关键信息至少 30f；批量动作后至少 15f。
- 光效：只允许森林绿低透明度聚光、边缘明度和片尾一次细微余辉；禁止蓝色霓虹与批量 glint。
- 形容词：克制、锐利、可核验。

## 4. 数据安全清单

- 虚构研究主题：`Orion-7 推理引擎的架构取舍与生态风险`。
- 虚构来源：`Northstar Labs Docs`、`Vector Systems Blog`、`Open Compute Notes`、`Atlas Benchmark`。
- 虚构过程数据：本轮汇集 28 条资料、拆出 6 条查询分支；只用于画面叙事，不代表产品实测。
- 所有分析画面常驻小字：`DEMO DATA · FICTIONAL`。
- 页面素材由当前 `WelcomeScreen`、`InputForm`、`ActivityTimeline`、`ChatMessagesView` 真实组件渲染；只向组件注入固定 Orion-7 fixture，不手搓一套相似 UI。
- App chrome 与开场/片尾均复用正式 `frontend/public/research-mark.svg`；捕获壳不得再展示旧 `{}` 标识或“LangGraph research agent”假副品牌。
- 采集脚本只启动隔离的本地 Vite harness；不启动后端，不读取 `.env`，阻断外部 API，并为模型列表使用本地虚构响应。

## 5. Styleframe

`styleframes.html` 包含三张已按最新 tokens 与正式图标重渲的 1920×1080 静态关键画面：品牌开场、AI 搜索主镜、工作流与分析结果。旧深灰/蓝色版本已被替换，不用于本轮品牌一致性验收。

## 6. BGM 与声音口径

- 候选只从 Skill 已记录 Mixkit Stock Music Free License 且可反查 URL 的曲目中选；不使用来源无法逐曲反查的 `bgm-tech-house.mp3`。
- BGM 音量约 0.26–0.34，给 SFX 留出余量；首尾做短淡入淡出。
- SFX 只钉独有动作：输入、证据卡归位、工作流节点完成、分析结果落定、片尾字标。
- 结尾使用 riser → impact → light sparkle 句式，素材必须来自有逐文件授权记录的条目。

## 7. 制作放行

阶段 0–1 已按 2026-08-13 最新 App 重新核对并由自主模式放行。原片的 30 秒结构、BGM 相位、镜头边界和核心运动语法保持不变；页面素材、颜色、品牌标识和文案口径按最新产品重采与适配。以下镜头映射与分镜均以真实产品边界为前提，不为了镜头效果虚构能力。

## 8. 镜头卡映射

| 功能/段落 | 选定卡与 style-key | 准确参考实现 | 采用理由与适配 |
|---|---|---|---|
| 开场 | 自定义正式品牌锁定（保留原 b0–b8 动作弧） | `frontend/public/research-mark.svg` + 当前 App header lockup | 正式图标与 `DeepResearch` 字标从首帧可识别，共同缩放落位；替代 `{ DeepResearch }` 假标识。动作仍在 b4 前完成，b4 后长 hold。 |
| AI 搜索 | `ai-stream-response · ai-stream-response` | `demos/interaction/ai-stream-response/StreamResponse.tsx` + 当前真实 composer/timeline 捕获 | 真实表达“问题输入→查询与来源持续汇入→完成收束”；使用浅雾灰页面、森林绿状态和虚构来源，保持行体先落、图标晚 3f。 |
| 搜索吞吐 | `research-card-stack-scroll · research-card-stack-scroll` | `demos/ui-entrance/research-card-stack-scroll/ResearchCardStackScroll.tsx` | 独立抽象镜头表达大量资料被持续读取；使用 8 张虚构资料卡，0.75 beat/张，最后留足静止。它不是产品页面复刻。 |
| 自动化研究工作流 | `cursor-flyover · cursor-flyover` | `demos/camera/cursor-flyover/CursorFlyover.tsx` + 当前 `ActivityTimeline` 捕获 | 产品是单页工作台而非节点画布；连续相机沿真实研究路径巡览“计划确认→查询/搜索→证据审查→写作/引用”，比伪造 DAG 编辑器更准确。 |
| 呼吸字卡 | 自定义静态品牌字卡 | 本项目 `SceneBreath.tsx` | 使用浅雾灰底、墨色文字与一条森林绿细规则，一次短淡入和 4-beat 静止；不引入纸张纹理或近黑舞台。 |
| 数据/证据分析 | `document-typewriter-reveal · document-typewriter-reveal` | `template/src/aifl/live/SceneWbr.tsx` + 当前 `ChatMessagesView` 捕获 | 用真实浅色 Markdown 报告版式、虚构对比表和引用体现分析；以 `#FAFBFA` 卡片底遮罩揭示，完整报告与输入 dock 都入镜。 |
| 收尾 | `outro-group-photo-launch · outro-group-photo-launch` | `template/src/aifl/live/SceneOutroLive.tsx` + `frontend/public/research-mark.svg` | 输入框、证据卡、时间线、报告表各抽一个代表元素回场，围住正式图标与 `DeepResearch` 字标；不再使用纯文字假定版或 `{}` 标记。 |

### 有意识拒绝的高风险卡

- `text-as-mask`：产品已有正式图标，但没有对应的超粗字标资产；把产品名当遮罩仍会裁切并迫使另造标识。
- `diagram-cascade`：产品没有节点画布或 workflow builder；使用会把“自动推进研究链路”错误宣传成“可视化工作流编辑器”。
- `unit-dot-swarm-regroup`：产品没有图表/点群分析 UI；会把结构化报告误导成 BI 看板。
- `ui-strip-away-outro`：产品没有 Publish/Ship 这类终结按钮，不具备让整屏蒸发的真实因果。

## 9. 音乐网格

选定 `house-vibez.mp3`（House Vibez · Lily J · Mixkit Stock Music Free License，约 122 BPM；授权 URL 记录在交付清单）。选择依据是开发者产品片所需的稳定 house 鼓组、授权链完整，以及较低的过度戏剧化风险。

分析产物：`analysis/music/beat_data.json` 与 `analysis/music/grid_drift.json`。

| 指标 | 结果 | 门槛 |
|---|---:|---:|
| 最小二乘 BPM | 121.9924 | — |
| 网格周期 T | 0.491834s | — |
| 原曲首拍 t0 | 0.060269s | 必须落真实瞬态 |
| fit 最大残差 | 14.54ms | ≤15ms |
| 瞬态命中率 | 100% | ≥98% |
| 平均绝对误差 | 8.52ms | <10ms |
| 全段漂移 | 0.56ms | <5ms |

Remotion 从源曲第 2 帧开始播放，使合成时间的 `BEAT0 = -0.006397s`，第 61 拍落在 29.995s；所有镜头边界使用 `beatF(n)`，不写裸绝对帧。最强 kick 候选包括 b4、b12、b23、b30；开场展开、AI 摘要/证据、资料吞吐和工作流点击分别围绕这些真实瞬态布置。结尾字标在 b56–b58 区间用授权完整的 impact 补足峰值，b58 后保留超过 1 秒 sign-off。

### 前 30 秒音乐结构

| 拍号 | 能量/鼓组 | 画面职责 |
|---|---|---|
| b0–b8 | kick 清晰、能量稳定，b4 为全段最强 kick | 正式品牌图标线条露出、锁定字标并长 hold |
| b8–b18 | 稳定四拍，b12 强 kick | AI 摘要与证据行汇入 |
| b18–b26 | snare / hihat 渐密，b23–b24 有强瞬态 | 资料卡吞吐密度段 |
| b26–b36 | b30 kick，b32 后 RMS 抬升 | 工作流巡览逐节点推进 |
| b36–b40 | 从 b32–b36 的能量高点回落 | 4-beat 文案呼吸位 |
| b40–b50 | 稳定中高能量 | 报告写入与完整页面阅读 |
| b50–b61 | hihat 密度维持推进，天然大 kick 较弱 | 合影组装；用授权完整的 buildup / impact / shimmer 建立片尾峰值 |

## 10. 最终分镜

| # | 时间 | 镜头 | 关键动效 |
|---:|---|---|---|
| 1 | b0–b8 · 0–118f | 浅雾灰场中正式 `research-mark.svg` + `DeepResearch`；副句“从一个问题，到可追溯的证据链” | 正式图标与字标从首帧可识别，b0–b3 共同扩展并锁定；副句随后进入，b4 后真静止。SFX：克制的锁定质感。 |
| 2 | b8–b18 · 118–265f | 当前浅色研究输入与搜索路径；虚构问题、查询与 6 条来源/校验项 | 页面轻退镜；问题输入后查询/证据行按 11→5f 收紧汇入，状态图标晚 3f；末尾一次森林绿完成脉冲。字幕：“AI 搜索 · 问题拆开，证据汇入”。 |
| 3 | b18–b26 · 265–383f | 8 张浅色虚构资料卡被持续读取并沉入栈 | 0.75 beat/张沿右下轴线落位、1–2f 压缩、深度 blur/降明度；第 8 张落定后 ≥15f 静止。字幕：“并行检索，持续补足证据”。 |
| 4 | b26–b36 · 383–531f | 当前真实研究路径：计划确认、查询/检索、证据审查、写作/引用 | 整页俯瞰后相机与光标同系统巡览四个落点；每个落点只出现一次森林绿涟漪；信息密集时正视、无 shake。字幕：“自动推进多阶段研究工作流”。 |
| 5 | b36–b40 · 531–590f | 浅雾灰品牌呼吸字卡：“搜到，只是开始。” / “分析、审查、引用校验，接着完成。” | 墨色文字与森林绿细规则 12f 淡入后静置，不重复片头与片尾标语。 |
| 6 | b40–b50 · 590–738f | 当前浅色报告页面；虚构对比表与 3 条引用 | 内容块成对揭示，唯一森林绿 caret 跟随；表格行与引用随后落入；b46 起拉到完整页面并静止。字幕：“数据分析 · 把资料压成结构化洞察”。 |
| 7 | b50–b61 · 738–900f | 输入框、证据卡、时间线、报告表从四方回场，围住正式图标与 `DeepResearch` | 9 个代表元素 b50–b54 组装；crane 落机位；正式图标/字标 b56 入场，森林绿 rule b58 点亮；最后 ≥1s 纯净定版。SFX：b50 buildup → b56/57 impact → b58 shimmer。 |

## 11. 帧级时间轴与验收帧

| shot | from | duration | 内容 | 验收帧 |
|---|---:|---:|---|---|
| `open` | `beatF(0)` = 0 | 118 | 正式品牌图标、字标与品牌承诺 | 59（锁定落位）、104（hold） |
| `search` | `beatF(8)` = 118 | 147 | AI 摘要 + 证据流 | 177（首轮证据）、250（完成态） |
| `sources` | `beatF(18)` = 265 | 118 | 资料卡吞吐 | 339（高密度）、375（静止） |
| `workflow` | `beatF(26)` = 383 | 148 | 时间线连续巡览 | 442（中段落点）、518（最终落点） |
| `breath` | `beatF(36)` = 531 | 59 | 呼吸字卡 | 552、580 |
| `report` | `beatF(40)` = 590 | 148 | 结构化报告与引用 | 649（写入中）、722（全页 hold） |
| `outro` | `beatF(50)` = 738 | 162 | 功能合影 + 文字字标 | 797（组装）、856（字标落定）、888（sign-off） |

一致性检查：三项用户要求均有独立镜头；每个镜头只用一种主运动语法；开场和收尾正式图标/字标 hold 达标；没有重复 tagline；页面素材均由 2026-08-13 当前真实组件渲染，抽象卡与全部内容数据明确标记为虚构。原镜头结构与音乐节拍保持不变，旧深灰/蓝色纹理与假 `{}` 标识不得进入新成片。最新真实组件素材、styleframe 与双版成片均已完成重采/重渲，进入最终媒体与视觉验收。
