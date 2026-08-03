"""
Provider-agnostic LLM client abstraction for POLARIS reasoners.

Messages use the neutral {"role": "system"|"user"|"assistant", "content": str}
schema. Two adapters are provided:

- GeminiClient: native google.genai (translates the neutral messages into
  Gemini's Content/Part chat-history format).
- OpenAICompatibleClient: any endpoint speaking the OpenAI chat-completions
  schema -- OpenAI itself, OpenRouter, or a self-hosted server (vLLM,
  llama.cpp-server, ...) -- selected purely via base_url/api_key/model.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class LLMClient(ABC):
    """A conversational LLM backend."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, int, int]:
        """Returns (response_text, input_tokens, output_tokens)."""
        ...


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str, max_retries: int = 3):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_retries = max_retries

    def _to_contents(self, messages: List[Dict[str, str]]):
        from google.genai import types

        contents = []
        for message in messages:
            role = message["role"]
            if role == "system":
                # Gemini has no separate system turn in this chat-history style;
                # prime it as a user turn followed by a canned acknowledgement,
                # matching the reasoner's original priming convention.
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=message["content"])])
                )
                contents.append(
                    types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text="Understood. I will analyze system contexts and make "
                                "adaptation decisions following the structured format with "
                                "tool usage when needed."
                            )
                        ],
                    )
                )
            elif role == "assistant":
                contents.append(
                    types.Content(role="model", parts=[types.Part(text=message["content"])])
                )
            else:
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=message["content"])])
                )
        return contents

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, int, int]:
        from google.genai import types

        contents = self._to_contents(messages)
        for attempt in range(self.max_retries):
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                if response and response.text:
                    return (
                        response.text.strip(),
                        response.usage_metadata.prompt_token_count,
                        response.usage_metadata.candidates_token_count,
                    )
                raise ValueError("Empty response from Gemini")
            except Exception as e:
                if attempt + 1 == self.max_retries:
                    raise
                import re as _re

                delay_match = _re.search(r"retryDelay.*?'(\d+)s'", str(e))
                delay = int(delay_match.group(1)) if delay_match else 2**attempt
                await asyncio.sleep(delay)

        raise RuntimeError("Gemini call failed after all retries")


class OpenAICompatibleClient(LLMClient):
    """Covers OpenAI, OpenRouter, and any self-hosted OpenAI-compatible
    server -- selection is purely config (base_url/api_key/model), no
    provider-specific code needed."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        max_retries: int = 3,
    ):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_retries = max_retries

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, int, int]:
        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = response.choices[0].message.content
                if text:
                    usage = response.usage
                    return (
                        text.strip(),
                        getattr(usage, "prompt_tokens", 0) or 0,
                        getattr(usage, "completion_tokens", 0) or 0,
                    )
                raise ValueError("Empty response from OpenAI-compatible endpoint")
            except Exception:
                if attempt + 1 == self.max_retries:
                    raise
                await asyncio.sleep(2**attempt)

        raise RuntimeError("LLM call failed after all retries")


def create_llm_client(
    provider: str,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
) -> LLMClient:
    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model)
    if provider == "openai_compatible":
        return OpenAICompatibleClient(api_key=api_key, model=model, base_url=base_url)
    raise ValueError(f"Unknown LLM provider: {provider!r} (expected 'gemini' or 'openai_compatible')")
