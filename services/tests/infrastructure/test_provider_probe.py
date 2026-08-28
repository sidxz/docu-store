"""probe_user_llm_config: one tiny completion per distinct lane model, key-free details."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from application.ports.user_llm_config import UserLLMConfig
from domain.exceptions import LLMAuthError, LLMBadRequestError, LLMRateLimitedError
from infrastructure.llm import openrouter_catalog, provider_probe


class _FakeLLM:
    def __init__(self, fail: Exception | None) -> None:
        self._fail = fail

    async def ainvoke(self, messages):
        if self._fail:
            raise self._fail
        return "OK"


def _patch(monkeypatch: pytest.MonkeyPatch, failures: dict[str, Exception | None]) -> list[dict]:
    calls: list[dict] = []

    def fake_build(**kwargs):
        calls.append(kwargs)
        return _FakeLLM(failures.get(kwargs["model_name"]))

    monkeypatch.setattr(provider_probe, "build_chat_model", fake_build)
    return calls


def _patch_ner(monkeypatch: pytest.MonkeyPatch, fail: Exception | None, compounds=("Gefitinib",)):
    """Stub the extractor so probing never leaves the machine."""

    class _FakeExtractor:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            built.append(kwargs)

        def extract(self, text):
            if fail:
                raise fail
            return SimpleNamespace(compounds=list(compounds))

    built: list[dict] = []
    module = types.ModuleType("structflo.ner")
    module.NERExtractor = _FakeExtractor
    profiles = types.ModuleType("structflo.ner.profiles")
    profiles.CHEMISTRY = object()
    monkeypatch.setitem(sys.modules, "structflo.ner", module)
    monkeypatch.setitem(sys.modules, "structflo.ner.profiles", profiles)
    return built


@pytest.fixture(autouse=True)
def _no_live_ner(monkeypatch: pytest.MonkeyPatch):
    """Nothing in this file may reach a provider or the catalog; tests re-stub as needed."""
    _patch_ner(monkeypatch, None)
    _patch_catalog(monkeypatch, None)


def _patch_catalog(monkeypatch: pytest.MonkeyPatch, verdict: bool | None) -> list[str]:
    asked: list[str] = []

    async def fake(model_id):
        asked.append(model_id)
        return verdict

    monkeypatch.setattr(openrouter_catalog, "supports_structured_outputs", fake)
    return asked


async def test_same_model_for_both_lanes_is_probed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, {})
    _patch_ner(monkeypatch, None)
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="gpt-5-mini", chat_model=None)
    out = await provider_probe.probe_user_llm_config(cfg, allow_cloud=True)
    assert out == {"batch": (True, None), "chat": (True, None), "ner": (True, None)}
    assert len(calls) == 1
    assert calls[0]["api_key"] == "key-x" and calls[0]["allow_cloud"] is True


async def test_per_lane_results_and_auth_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {"gpt-5": LLMAuthError("The provider rejected the key (401).")})
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="gpt-5-mini", chat_model="gpt-5")
    out = await provider_probe.probe_user_llm_config(cfg, allow_cloud=True)
    assert out["batch"] == (True, None)
    assert out["chat"] == (False, "The provider rejected the key (401).")


async def test_unknown_exception_is_reported_by_type_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {"m": RuntimeError("Authorization: Bearer key-x leaked")})
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="m", chat_model="m")
    out = await provider_probe.probe_user_llm_config(cfg, allow_cloud=True)
    assert out["batch"] == (False, "Unexpected RuntimeError")
    assert "key-x" not in str(out)


async def test_missing_model_is_a_soft_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, {})
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model=None, chat_model=None)
    out = await provider_probe.probe_user_llm_config(cfg, allow_cloud=True)
    assert out["batch"] == (False, "No model configured.")
    assert calls == []


# ── NER lane: entity extraction is not optional, so it gets its own verdict ──


async def test_ner_lane_probes_the_real_extractor_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {})
    built = _patch_ner(monkeypatch, None)
    cfg = UserLLMConfig(
        provider="openai", api_key="key-x", base_url="https://openrouter.ai/api/v1", model="m",
    )
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=True)

    assert probe.ok and not probe.refused
    # The OpenRouter base URL has to reach the extractor or NER silently hits OpenAI.
    assert built[0]["model_url"] == "https://openrouter.ai/api/v1"
    assert built[0]["provider"] == "openai"


async def test_a_model_that_rejects_the_schema_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plain completion fine, structured call 4xx → the schema is the difference."""
    _patch(monkeypatch, {})
    _patch_ner(monkeypatch, LLMBadRequestError("response_format json_schema is not supported"))
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="m")
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=True)

    assert not probe.ok
    assert probe.refused


async def test_a_bad_key_is_not_mistaken_for_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini answers a malformed key with a 400 too — blocking the save on that
    would lock the user out of the settings page they need to fix it."""
    _patch(monkeypatch, {"m": LLMAuthError("The provider rejected the key (401).")})
    _patch_ner(monkeypatch, LLMBadRequestError("API key not valid"))
    cfg = UserLLMConfig(provider="gemini", api_key="bad", model="m")
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=True)

    assert not probe.ok
    assert not probe.refused


async def test_transient_failures_never_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, {})
    _patch_ner(monkeypatch, LLMRateLimitedError("rate limited"))
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="m")

    assert not (await provider_probe.probe_ner_support(cfg, allow_cloud=True)).refused


async def test_a_model_that_answers_but_extracts_nothing_fails_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, {})
    _patch_ner(monkeypatch, None, compounds=())
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="m")
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=True)

    assert not probe.ok
    assert not probe.refused


async def test_a_provider_langextract_cannot_route_is_a_refusal() -> None:
    cfg = UserLLMConfig(provider="anthropic", api_key="key-x", model="m")
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=True)

    assert not probe.ok
    assert probe.refused


async def test_ner_probe_does_not_reach_a_cloud_provider_when_cloud_is_off() -> None:
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="m")
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=False)

    assert not probe.ok
    assert not probe.refused


# ── OpenRouter publishes the answer; no need to spend a call to learn it ──

_OPENROUTER = "https://openrouter.ai/api/v1"


async def test_a_model_openrouter_lists_as_incapable_is_refused_without_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case the live probe cannot catch: OpenRouter drops the unsupported
    parameter instead of erroring, so such a model answers in prose."""
    built = _patch_ner(monkeypatch, None)
    asked = _patch_catalog(monkeypatch, False)
    cfg = UserLLMConfig(
        provider="openai", api_key="key-x", base_url=_OPENROUTER, model="z-ai/glm-5.3",
    )
    probe = await provider_probe.probe_ner_support(cfg, allow_cloud=True)

    assert not probe.ok
    assert probe.refused
    assert "structured_outputs" in (probe.detail or "")
    assert asked == ["z-ai/glm-5.3"]
    assert built == []  # nothing was spent


async def test_a_listed_capability_is_still_proven_by_the_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """supported_parameters is a union across upstream routes, so yes is not proof."""
    built = _patch_ner(monkeypatch, None)
    _patch_catalog(monkeypatch, True)
    cfg = UserLLMConfig(
        provider="openai", api_key="key-x", base_url=_OPENROUTER, model="openai/gpt-5-mini",
    )

    assert (await provider_probe.probe_ner_support(cfg, allow_cloud=True)).ok
    assert len(built) == 1


async def test_an_unreachable_catalog_falls_through_to_the_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _patch_ner(monkeypatch, None)
    _patch_catalog(monkeypatch, None)
    cfg = UserLLMConfig(
        provider="openai", api_key="key-x", base_url=_OPENROUTER, model="openai/gpt-5-mini",
    )

    assert (await provider_probe.probe_ner_support(cfg, allow_cloud=True)).ok
    assert len(built) == 1


async def test_a_direct_openai_config_never_consults_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ner(monkeypatch, None)
    asked = _patch_catalog(monkeypatch, False)
    cfg = UserLLMConfig(provider="openai", api_key="key-x", base_url=None, model="gpt-5-mini")

    assert (await provider_probe.probe_ner_support(cfg, allow_cloud=True)).ok
    assert asked == []
