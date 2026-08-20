# 多媒体检索测试

当前集成会保留 OmniSeek 搜索结果中的图片，以及服务声明为可转写的音频/视频句柄。最终报告会自动追加“多媒体证据”：图片直接展示，音视频提供原始媒体链接。

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
