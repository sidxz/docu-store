"""Step 4: Verify that the generated answer is grounded in source documents."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from infrastructure.chat.models import GroundingResult
from infrastructure.config import settings

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from application.ports.prompt_repository import PromptRepositoryPort

log = structlog.get_logger(__name__)


class GroundingVerificationNode:
    """Check each claim in the answer against source text."""

    def __init__(
        self,
        llm_client: LLMClientPort,
        prompt_repository: PromptRepositoryPort,
    ) -> None:
        self._llm = llm_client
        self._prompts = prompt_repository

    async def run(
        self,
        answer: str,
        sources_text: str,
    ) -> GroundingResult:
        prompt = await self._prompts.render_prompt(
            "chat_grounding_verification",
            answer=answer,
            sources=sources_text,
        )

        log.debug("chat.grounding.start", answer_len=len(answer))

        if settings.chat_debug:
            log.info(
                "chat.debug.grounding.prompt",
                prompt_len=len(prompt),
                answer_preview=answer[:300],
                sources_len=len(sources_text),
            )

        try:
            raw = await self._llm.complete(prompt)

            if settings.chat_debug:
                log.info("chat.debug.grounding.raw_response", raw_len=len(raw), raw=raw[:1000])

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            result = GroundingResult(**data)
            log.info(
                "chat.grounding.done",
                is_grounded=result.is_grounded,
                confidence=result.confidence,
                supported=len(result.supported_claims),
                unsupported=len(result.unsupported_claims),
            )

            if settings.chat_debug:
                log.info(
                    "chat.debug.grounding.result",
                    supported_claims=result.supported_claims[:5],
                    unsupported_claims=result.unsupported_claims[:5],
                    summary=result.verification_summary,
                )

            return result

        except (json.JSONDecodeError, Exception) as exc:
            log.warning("chat.grounding.fallback", error=str(exc))
            return GroundingResult(
                is_grounded=True,
                confidence=0.5,
                supported_claims=[],
                unsupported_claims=[],
                verification_summary=f"Verification failed: {exc!s}",
            )
