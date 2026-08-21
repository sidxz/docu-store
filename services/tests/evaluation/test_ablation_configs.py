"""Tests for evaluation.ablation_configs module."""

import pytest

from evaluation.ablation_configs import (
    ABLATION_CONFIGS,
    get_config_by_id,
    get_config_by_name,
)


class TestAblationConfigs:
    def test_all_configs_have_unique_ids(self):
        ids = [c.config_id for c in ABLATION_CONFIGS]
        assert len(ids) == len(set(ids))

    def test_all_configs_have_unique_names(self):
        names = [c.name for c in ABLATION_CONFIGS]
        assert len(names) == len(set(names))

    def test_fourteen_configs(self):
        assert len(ABLATION_CONFIGS) == 14

    def test_config_ids_0_to_13(self):
        ids = sorted(c.config_id for c in ABLATION_CONFIGS)
        assert ids == list(range(14))

    def test_get_config_by_id(self):
        cfg = get_config_by_id(0)
        assert cfg.name == "full_system"

    def test_get_config_by_id_invalid(self):
        with pytest.raises(ValueError, match="No ablation config"):
            get_config_by_id(99)

    def test_get_config_by_name(self):
        cfg = get_config_by_name("no_reranking")
        assert cfg.config_id == 2

    def test_get_config_by_name_invalid(self):
        with pytest.raises(ValueError, match="No ablation config"):
            get_config_by_name("nonexistent")

    def test_baseline_has_thinking_mode(self):
        cfg = get_config_by_id(0)
        assert cfg.overrides.get("chat_default_mode") == "thinking"

    def test_quick_mode_config(self):
        cfg = get_config_by_id(7)
        assert cfg.overrides.get("chat_default_mode") == "quick"

    def test_hybrid_config_enables_sparse(self):
        cfg = get_config_by_id(10)
        assert cfg.overrides.get("sparse_encoding_enabled") is True

    # --- Baseline configs (publication) ---

    def test_vanilla_rag_config(self):
        cfg = get_config_by_id(11)
        assert cfg.name == "vanilla_rag"
        assert cfg.overrides.get("chat_clear_ner_filters") is True
        assert cfg.overrides.get("chat_enable_bioactivity_tool") is False
        assert cfg.overrides.get("reranker_enabled") is False

    def test_no_structure_search_config(self):
        cfg = get_config_by_id(12)
        assert cfg.name == "no_structure_search"
        assert cfg.overrides.get("chat_enable_structure_tool") is False

    def test_no_retrieval_config(self):
        cfg = get_config_by_id(13)
        assert cfg.name == "no_retrieval"
        assert cfg.overrides.get("chat_enable_retrieval") is False


class TestAblationsReachProductionCode:
    """Guards against ablations that silently do nothing.

    An override naming a field that no Settings object has, or a setting that no
    production code reads, produces a run identical to the baseline — the
    ablation looks like it worked and reports "no effect".
    """

    def test_every_override_is_a_real_settings_field(self):
        from infrastructure.config import settings

        unknown = [
            (cfg.name, key)
            for cfg in ABLATION_CONFIGS
            for key in cfg.overrides
            if not hasattr(settings, key)
        ]
        assert unknown == []

    def test_every_toggled_setting_is_read_outside_the_evaluation_package(self):
        """Each ablation setting must be consumed by the pipeline itself."""
        from pathlib import Path

        services_root = Path(__file__).parents[2]
        searched = [
            services_root / "application",
            services_root / "infrastructure",
            services_root / "domain",
            services_root / "interfaces",
        ]
        sources = [
            path.read_text()
            for root in searched
            for path in root.rglob("*.py")
            if "config.py" not in path.name
        ]

        toggles = {key for cfg in ABLATION_CONFIGS for key in cfg.overrides}
        unread = sorted(
            key for key in toggles if not any(key in source for source in sources)
        )
        assert unread == [], f"ablation settings never read by production code: {unread}"

    def test_harness_rejects_an_unknown_override(self):
        from evaluation.ablation_configs import AblationConfig
        from evaluation.eval_harness import _apply_config_overrides

        bogus = AblationConfig(
            config_id=99, name="bogus", description="", overrides={"not_a_setting": True}
        )
        with pytest.raises(ValueError, match="unknown Settings field"):
            _apply_config_overrides(bogus)
