import re
import json


class Post:
    @staticmethod
    def extract_pattern(text, pattern):
        # 匹配“```模式...```，允许在反引号后留空格
        regex = re.compile(r"```\s*" + re.escape(pattern) + r"\s(.*?)```", re.DOTALL)
        matches = regex.findall(text)
        if matches:
            return matches[0]

        # 备用方案：如果没有匹配的块，则尝试提取有效的 JSON
        if "json" in pattern:
            return _extract_json(text)

        return text


def _clean_json(text: str) -> str:
    """修复常见的 LLM JSON 格式错误（尾随逗号等）。"""
    # 删除 } 或 ] 前的逗号
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def _extract_json(text: str) -> str:
    """从可能缺少 JSON 分隔符的 LLM 输出中提取可靠的 JSON 对象。

    策略（按顺序）：
      1. 尝试将每个“{”作为候选开头——找到匹配的“}”，解析并保留
         最长的有效 JSON 对象。
      2. 如果失败，尝试将最长的候选对象包装在外部的 {{...}} 中。
    """
    best = ""
    candidates: list[tuple[int, int]] = []

    # 找出所有 { … } 对
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        for j, c2 in enumerate(text[i:], start=i):
            if c2 == "{":
                depth += 1
            elif c2 == "}":
                depth -= 1
                if depth == 0:
                    candidates.append((i, j + 1))
                    break

    # 尝试每个候选方案——保留最长的有效 JSON（清洗后）。
    for start, end in candidates:
        candidate = _clean_json(text[start:end])
        try:
            json.loads(candidate)
            if len(candidate) > len(best):
                best = candidate
        except json.JSONDecodeError:
            continue

    if best:
        return best

    # 策略 2：将最长的括号平衡候选词用 {{...}} 包裹起来
    if candidates:
        longest = max(candidates, key=lambda p: p[1] - p[0])
        wrapped = _clean_json("{" + text[longest[0]:longest[1]] + "}")
        try:
            json.loads(wrapped)
            return wrapped
        except json.JSONDecodeError:
            pass

    return text


if __name__ == "__main__":
    text = """```markdown
# 需求清晰度进度条: 60%

## 核心需求理解：
1. **核心目标**: 分析近一周（2025年6月10日-2025年6月17日）台湾媒体及国际舆论对第16届海峡论坛的报道观点，重点关注以下内容
- 台湾参加论坛的“热点人物”在岛内的舆论反应（如政治人物，团体代表）
- 民进党在舆论场中的斗争策略（如抹黑、限制、认知作战等）
- 论坛的潜在风险点（如两岸冲突、政治敏感性等）

2. **需求边界**
- **时间范围**：近一周（2025年6月10日-2025年6月17日）
- **主题范围**：台湾媒体（如TVBS、联合新闻网、中央社）及国际英文媒体（如Reuters、BBC）
- **分析重点**：舆论观点、政党观点、风险研判（非执行落地）。

## 待确认问题：
1. **时间范围**：是否严格限定为“近一周”，或可扩展至论坛前后两周（6月1日-6月17日）？
2. **热点人物**：是否有具体关注对象（如国民党代表团、民间团体领袖）？
3. **国际舆论**：需明确以英文为主，或包含其他语种（如日语、东南亚媒体）？
4. **风险点优先级**：需侧重政治风险、社会反应，还是舆情传播风险？

## 下一步：
请用户确认上述问题，或补充其他需求细节。若需求无调整，请基于当前理解开展分析。

（如需调整关键词或者范围，请直接告知），如需求清晰明了，请回复【需求确认】，我将进行报告生成任务，如果还存在问题，请直接说明。
```
"""
    output = Post.extract_pattern(text, "markdown")
    print(output)