"""Bundled prompts: the YAML files shipped in the image, as Langfuse templates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from infrastructure.llm.prompt_repositories.bundled_prompts import (
    DEFAULT_PROMPTS_DIR,
    bundled_prompts,
    load_bundled_prompts,
)
from infrastructure.llm.prompt_repositories.langfuse_prompt_repository import (
    LangfusePromptRepository,
)


def test_load_converts_placeholders_and_strips_trailing_whitespace(tmp_path):
    (tmp_path / "p.yaml").write_text('name: p\ntemplate: |\n  Q: {question}\n  {{"a": 1}}\n\n')

    assert load_bundled_prompts(tmp_path) == {"p": 'Q: {{question}}\n{{"a": 1}}'}


def test_every_bundled_file_loads():
    prompts = bundled_prompts()

    assert set(prompts) == {p.stem for p in DEFAULT_PROMPTS_DIR.glob("*.yaml")}
    assert "{{question}}" in prompts["chat_query_planning"]


class _StubClient:
    """Records what the repository asks the Langfuse SDK for."""

    def __init__(self) -> None:
        self.kwargs: dict = {}

    def get_prompt(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(compile=lambda **_: "ok", version=1)


@pytest.fixture
def repo_and_stub():
    repo = LangfusePromptRepository(host="http://unused", public_key="pk", secret_key="sk")
    stub = _StubClient()
    repo._client = stub  # noqa: SLF001 - the SDK client is built lazily
    return repo, stub


async def test_render_passes_bundled_template_as_fallback(repo_and_stub):
    repo, stub = repo_and_stub

    assert await repo.render_prompt("chat_query_planning", question="q") == "ok"

    assert stub.kwargs["fallback"] == bundled_prompts()["chat_query_planning"]
    assert stub.kwargs["label"] == "latest"


async def test_render_without_bundled_prompt_passes_no_fallback(repo_and_stub):
    repo, stub = repo_and_stub

    await repo.render_prompt("not_a_bundled_prompt")

    assert stub.kwargs["fallback"] is None


async def test_yaml_repository_reads_the_bundled_prompts_by_default():
    from infrastructure.llm.prompt_repositories.yaml_prompt_repository import (
        YamlPromptRepository,
    )

    rendered = await YamlPromptRepository().render_prompt(
        "chat_query_planning",
        question="What is the IC50?",
        conversation_context="",
        enable_sub_queries="true",
        enable_hyde="true",
    )

    assert "What is the IC50?" in rendered
