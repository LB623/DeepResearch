"""Tests for Configuration model — default values, env var overrides, etc."""

import pytest

from agent.configuration import (
    Configuration,
    ModelConfig,
    get_default_model_id,
    load_available_models_from_env,
)


class TestModelConfig:
    def test_valid_model_config(self):
        mc = ModelConfig(model_id="qwen-max", display_name="Qwen-Max")
        assert mc.model_id == "qwen-max"
        assert mc.display_name == "Qwen-Max"
        assert mc.icon == "Zap"
        assert mc.icon_color == "yellow-400"

    def test_custom_icon(self):
        mc = ModelConfig(
            model_id="test", display_name="Test", icon="Cpu", icon_color="purple-400"
        )
        assert mc.icon == "Cpu"
        assert mc.icon_color == "purple-400"

    def test_missing_model_id_raises(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ModelConfig(display_name="NoId")


class TestLoadAvailableModelsFromEnv:
    def test_default_models_when_no_env(self, monkeypatch):
        monkeypatch.delenv("AVAILABLE_MODELS", raising=False)
        models = load_available_models_from_env()
        assert len(models) == 2
        assert models[0].model_id == "deepseek-v4-flash"
        assert models[-1].model_id == "deepseek-v4-pro"

    def test_load_from_env_json(self, monkeypatch):
        monkeypatch.setenv(
            "AVAILABLE_MODELS",
            '[{"model_id":"custom-1","display_name":"Custom 1","icon":"Zap","icon_color":"red-400"},'
            '{"model_id":"custom-2","display_name":"Custom 2","icon":"Cpu","icon_color":"blue-400"}]',
        )
        models = load_available_models_from_env()
        assert len(models) == 2
        assert models[0].model_id == "custom-1"
        assert models[1].model_id == "custom-2"

    def test_invalid_json_falls_back(self, monkeypatch):
        monkeypatch.setenv("AVAILABLE_MODELS", "not valid json")
        models = load_available_models_from_env()
        assert len(models) == 2  # fallback defaults


class TestGetDefaultModelId:
    def test_returns_last_model(self):
        default = get_default_model_id()
        assert default is not None
        assert isinstance(default, str)


class TestConfigurationDefaults:
    def test_default_values(self):
        cfg = Configuration()
        assert cfg.number_of_initial_queries == 2
        assert cfg.max_research_loops == 2
        assert cfg.max_writer_revisions == 3
        assert not hasattr(cfg, "omniseek_mode")
        assert cfg.max_omniseek_calls == 4
        assert cfg.omniseek_result_limit == 5
        assert cfg.search_provider_timeout_seconds == 30
        assert not hasattr(cfg, "omniseek_sources")
        assert isinstance(cfg.query_generator_model, str)
        assert isinstance(cfg.reflection_model, str)
        assert isinstance(cfg.answer_model, str)
        assert len(cfg.available_models) > 0

    def test_available_models_is_list_of_model_config(self):
        cfg = Configuration()
        assert all(isinstance(m, ModelConfig) for m in cfg.available_models)


class TestFromRunnableConfig:
    def test_empty_config_returns_defaults(self):
        cfg = Configuration.from_runnable_config(None)
        assert cfg.number_of_initial_queries == 2
        assert cfg.max_research_loops == 2

    def test_configurable_overrides(self):
        cfg = Configuration.from_runnable_config(
            {
                "configurable": {
                    "number_of_initial_queries": 1,
                    "max_research_loops": 1,
                    "max_writer_revisions": 1,
                }
            }
        )
        assert cfg.number_of_initial_queries == 1
        assert cfg.max_research_loops == 1
        assert cfg.max_writer_revisions == 1

    def test_env_var_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("NUMBER_OF_INITIAL_QUERIES", "8")
        cfg = Configuration.from_runnable_config(
            {"configurable": {"number_of_initial_queries": 3}}
        )
        assert cfg.number_of_initial_queries == 8

    def test_model_fields_from_configurable(self):
        cfg = Configuration.from_runnable_config(
            {
                "configurable": {
                    "query_generator_model": "model-a",
                    "reflection_model": "model-b",
                    "answer_model": "model-c",
                }
            }
        )
        assert cfg.query_generator_model == "model-a"
        assert cfg.reflection_model == "model-b"
        assert cfg.answer_model == "model-c"

    def test_partial_override(self):
        cfg = Configuration.from_runnable_config(
            {"configurable": {"max_research_loops": 1}}
        )
        assert cfg.max_research_loops == 1
        assert cfg.number_of_initial_queries == 2  # default

    def test_caller_cannot_raise_server_budget_defaults(self):
        cfg = Configuration.from_runnable_config(
            {
                "configurable": {
                    "number_of_initial_queries": 20,
                    "max_research_loops": 20,
                    "max_writer_revisions": 20,
                    "max_web_search_calls": 100,
                    "max_omniseek_calls": 20,
                    "omniseek_wait_seconds": 15,
                    "omniseek_request_timeout_seconds": 120,
                    "omniseek_result_limit": 50,
                    "search_provider_timeout_seconds": 120,
                    "max_elapsed_seconds": 86_400,
                    "max_no_progress_rounds": 20,
                    "max_total_tokens": 2_000_000,
                }
            }
        )

        assert cfg.number_of_initial_queries == 2
        assert cfg.max_research_loops == 2
        assert cfg.max_writer_revisions == 3
        assert cfg.max_web_search_calls == 20
        assert cfg.max_omniseek_calls == 4
        assert cfg.omniseek_wait_seconds == 3
        assert cfg.omniseek_request_timeout_seconds == 12
        assert cfg.omniseek_result_limit == 5
        assert cfg.search_provider_timeout_seconds == 30
        assert cfg.max_elapsed_seconds == 900
        assert cfg.max_no_progress_rounds == 2
        assert cfg.max_total_tokens == 120_000

    def test_available_models_not_overridable_by_configurable(self):
        """available_models should always come from env, not configurable."""
        cfg = Configuration.from_runnable_config(
            {"configurable": {"available_models": "malicious"}}
        )
        assert isinstance(cfg.available_models, list)
        assert len(cfg.available_models) > 0

    def test_omniseek_sources_are_not_accepted_from_runnable_config(self):
        cfg = Configuration.from_runnable_config(
            {"configurable": {"omniseek_sources": "walled_private_source"}}
        )

        assert not hasattr(cfg, "omniseek_sources")

    def test_omniseek_mode_is_not_accepted_from_runnable_config(self):
        cfg = Configuration.from_runnable_config(
            {"configurable": {"omniseek_mode": "only"}}
        )

        assert not hasattr(cfg, "omniseek_mode")

    def test_inconsistent_omniseek_timeouts_are_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="must be at least"):
            Configuration(
                omniseek_wait_seconds=15,
                omniseek_request_timeout_seconds=12,
            )
