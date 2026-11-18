"""Bundled prompts: the YAML files shipped in the image, as Langfuse templates."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
import yaml

from infrastructure.llm.prompt_repositories.bundled_prompts import (
    DEFAULT_PROMPTS_DIR,
    bundled_prompts,
    load_bundled_prompts,
)
from infrastructure.llm.prompt_repositories.langfuse_prompt_repository import (
    LangfusePromptRepository,
)


def test_load_converts_placeholders_and_strips_trailing_whitespace(tmp_path):
    (tmp_path / "p.yaml").write_text('name: p\ntemplate: |\n  Q: {question}\n  {{"a": {{}}}}\n\n')

    assert load_bundled_prompts(tmp_path) == {"p": 'Q: {{question}}\n{"a": {}}'}


def test_every_bundled_file_loads():
    prompts = bundled_prompts()

    assert set(prompts) == {p.stem for p in DEFAULT_PROMPTS_DIR.glob("*.yaml")}
    assert "{{question}}" in prompts["chat_query_planning"]


def test_langfuse_compiles_each_bundled_prompt_like_the_yaml_repository():
    """Python's ``{{`` escapes must reach the model as ``{``, on both paths."""
    from langfuse.model import TemplateParser

    for path in DEFAULT_PROMPTS_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        variables = {v: f"<{v}>" for v in data.get("input_variables", [])}

        expected = data["template"].rstrip().format_map(variables)
        compiled = TemplateParser.compile_template(bundled_prompts()[data["name"]], variables)

        assert compiled == expected, data["name"]


class _StubClient:
    """Records what the repository asks the Langfuse SDK for."""

    def __init__(self) -> None:
        self.kwargs: dict = {}
        self.delay = 0.0  # how long Langfuse takes to answer

    def get_prompt(self, **kwargs):
        time.sleep(self.delay)
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


async def test_render_does_not_retry_the_fetch_when_it_can_fall_back(repo_and_stub):
    repo, stub = repo_and_stub

    await repo.render_prompt("chat_query_planning", question="q")
    assert stub.kwargs["max_retries"] == 0

    await repo.render_prompt("not_a_bundled_prompt")
    assert "max_retries" not in stub.kwargs  # nothing to fall back to: keep the SDK's retries


async def test_render_leaves_the_event_loop_free_while_langfuse_is_slow(repo_and_stub):
    repo, stub = repo_and_stub
    stub.delay = 0.2
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker = asyncio.create_task(tick())
    await repo.render_prompt("chat_query_planning", question="q")
    ticker.cancel()

    assert ticks >= 5


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
