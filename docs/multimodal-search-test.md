# 多媒体检索测试

当前集成会保留 OmniSeek 搜索结果中的图片，以及服务声明为可转写的音频/视频句柄。最终报告会自动追加“多媒体证据”：图片直接展示，音视频提供原始媒体链接。

检索 adapter 会根据中英文图片、视频和音频意图选择不超过 16 个媒体源，并只把类型匹配的媒体资产放入报告候选；未声明类型且无法从 URL 判断的附件不会被默认当作图片。普通广域查询默认串行，窄媒体路由最多并发 4，超过 8 个源的宽路由最多并发 2。首轮未取得目标媒体时只做一次缓存回退，首轮和回退共享同一个端到端超时预算。

这里的能力边界是“检索并呈现多媒体证据”。它不会仅凭媒体 URL 推断画面或语音内容；自动调用 `omniseek_view` 做视觉理解、调用 `omniseek_transcribe` 做语音转写，属于后续的多模态深读阶段。

## 快速验收

先确认 OmniSeek、后端和前端已经启动，然后运行真实多媒体检索探针：

```bash
cd backend
../.venv/bin/python -m agent.multimodal_preflight
cd ..
```

成功输出示例：

```text
Multimodal preflight ok: documents=10 images=1 videos=1 audio=0
```

该命令会发起一次真实 OmniSeek 外部检索，不会调用 LLM，也不会输出查询正文、媒体 URL、Bearer Token 或上游异常详情。网络结果会变化，所以计数不保证固定；只要至少返回一个媒体资产即为通过。

## Web UI 示例

打开 [http://localhost:5173/app/](http://localhost:5173/app/)，选择“快速”，输入：

```text
调研 Qwen 3.8 27B 的视觉能力和实测反馈。优先检索带图片或视频的原始材料，并在最终报告保留多媒体证据。
```

计划生成后确认开始研究。验收点：

1. 研究过程正常完成，文本来源仍有可点击引用。
2. 最终报告出现“多媒体证据”章节。
3. 检索到图片时直接显示；检索到音视频句柄时显示“视频”或“音频”入口。
4. 媒体结果为空时，报告不生成空的多媒体章节，也不影响文本研究结果。

外部图片由原站托管。前端采用懒加载并设置 `referrerPolicy=no-referrer`；打开音视频链接仍会访问对应的第三方站点。

## 固定集评测

正式评测使用 `eval/multimodal_retrieval_set.json`：40 个冻结题目，中英文各 20 个，覆盖图片、视频、音频、混合媒体意图和纯文本负向对照。下面的命令会发起真实外部检索并调用付费 Judge，不属于 `make verify`：

```bash
cd backend
../.venv/bin/python -m eval.run_multimodal_benchmark \
  --dataset eval/multimodal_retrieval_set.json \
  --repeats 3 \
  --limit 10 \
  --concurrency 2 \
  --wait-seconds 5 \
  --timeout-seconds 30 \
  --judge-model deepseek-v4-pro \
  --output eval_runs/multimodal_retrieval_2026-08-21_r3.json
cd ..
```

结果同时记录检索成功率、媒体粗命中率、类型匹配覆盖率@3、严格元数据 Judge 覆盖率@3、Precision@3、P50/P95 延迟及 Judge token。元数据 Judge 不查看真实画面或音频内容，因此不能替代视觉模型、转写模型或人工抽检。

2026-08-21 的正式结果包含 40 题 × 3 次重复，共 120 次检索：

| 指标 | 结果 |
| --- | ---: |
| 请求成功率 | 100.0% |
| 目标媒体类型覆盖率@3 | 94.4% |
| 严格元数据 Judge 可用覆盖率@3 | 38.9% |
| 严格元数据 Judge Precision@3 | 25.9% |
| P50 / P95 延迟 | 1.64s / 5.45s |

分类型看，视频、音频和混合媒体的类型覆盖率均为 100%，图片为 83.3%；视频的元数据 Judge Precision@3 为 56.7%，图片仅为 5.6%。因此当前结果可以支持“类型路由和检索链路稳定”，不能支持“图片内容相关性已经充分解决”。OmniSeek 当前没有专用图片搜索适配器，图片主要来自网页附件，这是后续应单独补齐的能力。完整逐题结果见 `backend/eval_runs/multimodal_retrieval_2026-08-21_r3.json`。
