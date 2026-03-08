"""Unified LLM client abstraction supporting OpenAI and Anthropic."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from aime.config import settings


@dataclass
class LLMResponse:
    text: str


class LLMClient:
    """Unified interface for LLM calls."""

    def __init__(self):
        self.provider = settings.llm_provider

        if self.provider == "openai":
            from openai import AsyncOpenAI
            kwargs = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._openai = AsyncOpenAI(**kwargs)
            self._model = settings.openai_model
        else:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key
            )
            self._model = settings.claude_model

    async def generate(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1000,
    ) -> str:
        """Non-streaming generation. Returns full text."""
        if self.provider == "openai":
            oai_messages = [{"role": "system", "content": system}]
            for m in messages:
                oai_messages.append({"role": m["role"], "content": m["content"]})
            response = await self._openai.chat.completions.create(
                model=self._model,
                messages=oai_messages,
                max_completion_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        else:
            response = await self._anthropic.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text

    async def stream(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Streaming generation. Yields text tokens."""
        if self.provider == "openai":
            oai_messages = [{"role": "system", "content": system}]
            for m in messages:
                oai_messages.append({"role": m["role"], "content": m["content"]})
            stream = await self._openai.chat.completions.create(
                model=self._model,
                messages=oai_messages,
                max_completion_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        else:
            async with self._anthropic.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text


# Singleton
_llm_client = None


def get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
