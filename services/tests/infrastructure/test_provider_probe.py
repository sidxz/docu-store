"""probe_user_llm_config: one tiny completion per distinct lane model, key-free details."""

from __future__ import annotations

import pytest

from application.ports.user_llm_config import UserLLMConfig
from domain.exceptions import LLMAuthError
from infrastructure.llm import provider_probe


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


async def test_same_model_for_both_lanes_is_probed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch(monkeypatch, {})
    cfg = UserLLMConfig(provider="openai", api_key="key-x", model="gpt-5-mini", chat_model=None)
    out = await provider_probe.probe_user_llm_config(cfg, allow_cloud=True)
    assert out == {"batch": (True, None), "chat": (True, None)}
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
