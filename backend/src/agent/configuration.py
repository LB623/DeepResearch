import json
import os
from typing import Any, List

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

_SERVER_CAPPED_FIELDS = {
    "number_of_initial_queries",
    "max_research_loops",
    "max_writer_revisions",
    "max_web_search_calls",
    "max_elapsed_seconds",
    "max_no_progress_rounds",
    "max_total_tokens",
}

# 模型ID常量
MODEL_ID_FLASH = "deepseek-v4-flash"
MODEL_ID_PLUS = "deepseek-v4-flash"
MODEL_ID_MAX = "deepseek-v4-pro"
MODEL_ID_JUDEG = "deepseek-v4-pro"

class ModelConfig(BaseModel):
    """模型配置项"""
    model_id: str = Field(..., description="模型ID")
    display_name: str = Field(..., description="显示名称")
    icon: str = Field(default="Zap", description="图标类型(Zap/Cpu)")
    icon_color: str = Field(default="yellow-400", description="图标颜色")


def load_available_models_from_env() -> List[ModelConfig]:
    """从环境变量加载可用模型列表"""
    default_models = [
        ModelConfig(model_id=MODEL_ID_FLASH, display_name="DS4-Flash", icon="Zap", icon_color="yellow-400"),
        ModelConfig(model_id=MODEL_ID_MAX, display_name="DS4-Pro", icon="Cpu", icon_color="purple-400"),
    ]
    models_json = os.getenv("AVAILABLE_MODELS")

    if not models_json:
        # 默认模型列表
        return default_models

    try:
        models_data = json.loads(models_json)
        return [ModelConfig(**model) for model in models_data]
    except Exception as e:
        print(f"警告: 解析AVAILABLE_MODELS失败，使用默认模型列表。错误: {e}")
        return default_models


def get_default_model_id() -> str:
    """获取默认模型ID"""
    models = load_available_models_from_env()
    if models:
        return models[0].model_id
    return MODEL_ID_MAX  # 兜底默认值

def get_flash_model_id() -> str:
    """获取第一个icon为Zap的模型ID"""
    models = load_available_models_from_env()
    for model in models:
        if model.icon == "Zap":
            return model.model_id
    return models[0].model_id if models else MODEL_ID_FLASH  # 兜底默认值


def get_plus_model_id() -> str:
    """获取居中的模型ID"""
    models = load_available_models_from_env()
    if models:
        middle_index = len(models) // 2
        return models[middle_index].model_id
    return MODEL_ID_PLUS  # 兜底默认值

def get_judge_model_id() -> str:
    return MODEL_ID_JUDEG  # 兜底默认值

class Configuration(BaseModel):
    """agent的配置."""

    # 可用模型列表配置（从环境变量加载）
    available_models: List[ModelConfig] = Field(
        default_factory=load_available_models_from_env,
        description="可用的LLM模型列表",
    )

    query_generator_model: str = Field(
        default_factory=get_flash_model_id,
        description="用于Agent查询生成的LLM的名称.",
    )

    reflection_model: str = Field(
        default_factory=get_plus_model_id,
        description="用于Agent反思的LLM的名称.",
    )

    answer_model: str = Field(
        default_factory=get_default_model_id,
        description="用于Agent生成答案的LLM模型名称.",
    )

    number_of_initial_queries: int = Field(
        default=2,
        ge=0,
        le=20,
        description="要生成的初始搜索查询数量.",
    )

    max_research_loops: int = Field(
        default=2,
        ge=0,
        le=20,
        description="要执行的最大research循环次数.",
    )

    max_writer_revisions: int = Field(
        default=3,
        ge=0,
        le=20,
        description="报告初稿通过评论员评审后允许的最大修订次数.",
    )

    max_web_search_calls: int = Field(
        default=20,
        ge=0,
        le=100,
        description="单个研究任务允许的最大网页搜索次数.",
    )

    max_elapsed_seconds: float = Field(
        default=900,
        ge=0,
        le=86_400,
        description="单个研究任务允许的最大墙钟时间（秒）.",
    )

    max_no_progress_rounds: int = Field(
        default=2,
        ge=0,
        le=20,
        description="连续无新增证据时允许继续的最大研究轮数.",
    )

    max_total_tokens: int = Field(
        default=120_000,
        ge=0,
        le=2_000_000,
        description="单个研究任务允许累计消耗的最大 LLM token 数.",
    )

    @classmethod
    def from_runnable_config(
        cls, config: RunnableConfig | None = None
    ) -> "Configuration":
        """从RunnableConfig创建配置实例."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )

        raw_values: dict[str, Any] = {}
        for name in cls.model_fields.keys():
            # 跳过 available_models，它应该从环境变量直接加载
            if name == "available_models":
                continue
            env_value = os.environ.get(name.upper())
            config_value = configurable.get(name)
            raw_values[name] = env_value if env_value is not None else config_value

        values = {k: v for k, v in raw_values.items() if v is not None}

        parsed = cls(**values)
        defaults = cls()
        for name in _SERVER_CAPPED_FIELDS:
            if os.environ.get(name.upper()) is None:
                setattr(parsed, name, min(getattr(parsed, name), getattr(defaults, name)))
        return parsed
