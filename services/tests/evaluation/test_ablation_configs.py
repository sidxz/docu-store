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
        assert cfg.clear_ner_filters_before_retrieval is True
        assert cfg.skip_bioactivity_tool is True
        assert cfg.overrides.get("reranker_enabled") is False

    def test_bm25_only_config(self):
        cfg = get_config_by_id(12)
        assert cfg.name == "bm25_only"
        assert cfg.overrides.get("sparse_encoding_enabled") is True
        assert cfg.overrides.get("retrieval_use_sparse_only") is True

    def test_no_retrieval_config(self):
        cfg = get_config_by_id(13)
        assert cfg.name == "no_retrieval"
        assert cfg.overrides.get("retrieval_enabled") is False
