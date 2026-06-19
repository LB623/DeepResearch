"""从网络搜索摘要中提取事实。

使用LLM从搜索结果摘要中提取离散的、

可验证的事实。每个事实都带有
置信度评分，并链接到其来源 URL。

提取的事实随后存储在知识库（FactStore）中，可供未来的研究请求检索。
"""

from __future__ import annotations

import json
import os

from loguru import logger

from agent.base_agent import Agent
from agent.post import Post

# ── extraction prompt ─────────────────────────────────────────────────

EXTRACTION_INSTRUCTIONS = """# 任务说明
你是一个知识提取专家。从给定的搜索摘要中提取出离散的、可验证的事实陈述。

# Instruction
1. 每条 fact 必须是一个独立的、可验证的陈述（一句话），避免复合句
2. 每条 fact 标注来源 URL（从摘要中的 [来源名](url) 格式提取）
3. 每条 fact 标注 confidence（0.0-1.0）：
   - 0.9-1.0：摘要明确引用具体数据/事件
   - 0.7-0.8：摘要中有较明确的表述
   - 0.5-0.6：摘要中隐含但未直接说明
4. 标注每条 fact 的 fact_category（事实时效性类别）：
   - market_data: 市场份额、价格、排名、增长率、营收数据
   - product_info: 产品功能、规格、版本、发布信息
   - strategy: 公司战略、投资方向、合作、收购
   - technology: 技术原理、架构定义、标准、协议
   - historical: 历史事件、里程碑、已发生的事实
5. 不要提取过于泛泛的陈述（如"这是一个重要市场"）
6. 每条 fact 控制在 80 字以内
7. 最多提取 10 条 fact

# 输出格式
```json
[
  {
    "fact": "2025年Q1全球AI编程助手市场规模达到15亿美元",
    "source_url": "https://xxxx.com/xxxx",
    "confidence": 0.9,
    "fact_category": "market_data"
  },
  {
    "fact": "GitHub Copilot 占据AI编程助手市场约35%的份额",
    "source_url": "https://xxxx.com/xxxx",
    "confidence": 0.8,
    "fact_category": "market_data"
  }
]
```

# 研究主题（用于上下文理解）
{research_topic}

# 搜索摘要
{summary}

# 输出"""


# ── extractor ─────────────────────────────────────────────────────────

class FactExtractor:
    """从搜索结果摘要中提取结构化事实。"""

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv(
            "FACT_EXTRACTOR_MODEL",
            "deepseek-v4-flash",
        )

    def extract(self, summary: str, research_topic: str = "") -> list[dict]:
        """从单个搜索结果摘要中提取事实。

        Args:
            summary: 网页搜索结果文本（已由 LLM 进行摘要）
            research_topic: 用于提供上下文的整体研究主题

        Returns:
            List of {fact, source_url, confidence} dicts.
        """
        if not summary or len(summary) < 50:
            logger.debug("[KB-extractor] 摘要过短，省略提取")
            return []

        agent = Agent(model_id=self.model_id) if self.model_id else Agent()
        agent.set_step_prompt(EXTRACTION_INSTRUCTIONS)

        raw = agent.step(
            research_topic=research_topic or "(extracting facts)",
            summary=summary[:8000],  # truncate for safety
        )

        try:
            json_str = Post.extract_pattern(raw, pattern="json")
            facts = json.loads(json_str)
            if isinstance(facts, list):
                facts = self._validate(facts)
                logger.info(
                    f"[KB-extractor] extracted {len(facts)} facts "
                    f"from summary ({len(summary)} chars)"
                )
                return facts
        except json.JSONDecodeError as exc:
            logger.warning(
                f"[KB-extractor] JSON parse failed — LLM returned malformed JSON: {exc}"
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"[KB-extractor] data validation failed ({type(exc).__name__}): {exc}"
            )
        except Exception as exc:
            logger.warning(
                f"[KB-extractor] failed to parse facts ({type(exc).__name__}): {exc}"
            )

        return []

    @staticmethod
    def _validate(facts: list) -> list[dict]:
        """过滤和规整提取的facts."""
        valid = []
        for f in facts:
            if not isinstance(f, dict):
                continue
            fact_text = f.get("fact", "").strip()
            if not fact_text or len(fact_text) < 10:
                continue
            valid.append({
                "fact": fact_text,
                "source_url": f.get("source_url", ""),
                "confidence": min(1.0, max(0.0, float(f.get("confidence", 0.7)))),
                "fact_category": f.get("fact_category", "strategy"),
            })
            if len(valid) >= 10:
                break
        return valid
