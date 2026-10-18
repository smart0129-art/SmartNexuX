import math
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from openai import APIError, AsyncOpenAI
from pydantic import BaseModel


ChatProvider = Literal["ollama", "openai_compatible"]
SYSTEM_PROMPT = "You are a helpful assistant. Answer clearly and accurately."


class ChatProviderError(RuntimeError):
    pass


class ChatProviderConfigurationError(ChatProviderError):
    pass


class ChatModelSelectionError(ValueError):
    pass


class ChatUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    source: Literal["provider", "estimate"]


@dataclass(frozen=True)
class ChatStreamEvent:
    kind: Literal["token", "usage"]
    token: str | None = None
    usage: ChatUsage | None = None


class ChatModelRouter:
    def __init__(
        self,
        ollama_base_url: str | None = None,
        ollama_models: str | None = None,
        external_base_url: str | None = None,
        external_api_key: str | None = None,
        external_models: str | None = None,
        default_provider: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.ollama_base_url = (
            ollama_base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.external_base_url = (
            external_base_url
            or os.getenv(
                "OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            )
        ).rstrip("/")
        self.external_api_key = (
            external_api_key
            if external_api_key is not None
            else os.getenv("OPENAI_API_KEY", "")
        )
        self._models: dict[ChatProvider, tuple[str, ...]] = {
            "ollama": self._parse_models(
                ollama_models
                if ollama_models is not None
                else os.getenv("OLLAMA_CHAT_MODELS", "qwen2.5vl:3b"),
                "OLLAMA_CHAT_MODELS",
            ),
            "openai_compatible": self._parse_models(
                external_models
                if external_models is not None
                else os.getenv("OPENAI_CHAT_MODELS", "gpt-4o-mini"),
                "OPENAI_CHAT_MODELS",
                allow_empty=True,
            ),
        }
        configured_default = (
            default_provider
            if default_provider is not None
            else os.getenv("CHAT_DEFAULT_PROVIDER", "ollama")
        )
        if configured_default not in self._models:
            raise ValueError(
                "CHAT_DEFAULT_PROVIDER must be 'ollama' or 'openai_compatible'"
            )
        if not self._models[configured_default]:
            raise ValueError(
                f"No chat models are configured for {configured_default}"
            )
        if configured_default == "ollama":
            self.default_provider: ChatProvider = "ollama"
        else:
            self.default_provider = "openai_compatible"
        self._injected_http_client = http_client
        self._owns_clients = http_client is None
        self._ollama_client = AsyncOpenAI(
            api_key="ollama",
            base_url=f"{self.ollama_base_url}/v1",
            timeout=180.0,
            **({"http_client": http_client} if http_client is not None else {}),
        )
        self._external_client: AsyncOpenAI | None = None

    @staticmethod
    def _parse_models(
        value: str,
        setting_name: str,
        *,
        allow_empty: bool = False,
    ) -> tuple[str, ...]:
        models = tuple(
            dict.fromkeys(
                model.strip()
                for model in value.split(",")
                if model.strip()
            )
        )
        if not models and not allow_empty:
            raise ValueError(f"{setting_name} must contain at least one model")
        return models

    @property
    def default_model(self) -> str:
        return self._models[self.default_provider][0]

    def resolve(self, provider: ChatProvider, model: str | None) -> str:
        allowed_models = self._models[provider]
        selected_model = model or (allowed_models[0] if allowed_models else None)
        if selected_model is None:
            raise ChatModelSelectionError(
                f"No models are configured for provider '{provider}'"
            )
        if selected_model not in allowed_models:
            raise ChatModelSelectionError(
                f"Model '{selected_model}' is not configured for provider '{provider}'"
            )
        if provider == "openai_compatible" and not self.external_api_key.strip():
            raise ChatProviderConfigurationError(
                "OPENAI_API_KEY is required for the external model provider"
            )
        return selected_model

    def list_models(self) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for provider, models in self._models.items():
            for model in models:
                options.append(
                    {
                        "provider": provider,
                        "model": model,
                        "configured": (
                            provider == "ollama"
                            or bool(self.external_api_key.strip())
                        ),
                        "is_default": (
                            provider == self.default_provider
                            and model == self.default_model
                        ),
                    }
                )
        return options

    async def stream(
        self,
        prompt: str,
        provider: ChatProvider,
        model: str,
    ) -> AsyncIterator[ChatStreamEvent]:
        client = self._client_for(provider)
        response_stream = None
        answer_parts: list[str] = []
        provider_usage: ChatUsage | None = None
        try:
            response_stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in response_stream:
                if chunk.usage is not None:
                    provider_usage = ChatUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                        source="provider",
                    )
                for choice in chunk.choices:
                    content = choice.delta.content
                    if isinstance(content, str) and content:
                        answer_parts.append(content)
                        yield ChatStreamEvent(kind="token", token=content)
        except APIError as exc:
            message = exc.message or "The chat provider returned an error"
            raise ChatProviderError(
                f"{provider} chat request failed: {message}"
            ) from exc
        finally:
            if response_stream is not None:
                await response_stream.close()

        usage = provider_usage or self._estimate_usage(prompt, answer_parts)
        yield ChatStreamEvent(kind="usage", usage=usage)

    def _client_for(self, provider: ChatProvider) -> AsyncOpenAI:
        if provider == "ollama":
            return self._ollama_client
        if not self.external_api_key.strip():
            raise ChatProviderConfigurationError(
                "OPENAI_API_KEY is required for the external model provider"
            )
        if self._external_client is None:
            self._external_client = AsyncOpenAI(
                api_key=self.external_api_key,
                base_url=self.external_base_url,
                timeout=180.0,
                **(
                    {"http_client": self._injected_http_client}
                    if self._injected_http_client is not None
                    else {}
                ),
            )
        return self._external_client

    @staticmethod
    def _estimate_usage(prompt: str, answer_parts: list[str]) -> ChatUsage:
        prompt_tokens = ChatModelRouter._estimate_tokens(
            f"{SYSTEM_PROMPT}\n{prompt}"
        )
        completion_tokens = ChatModelRouter._estimate_tokens(
            "".join(answer_parts)
        )
        return ChatUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            source="estimate",
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return math.ceil(len(text.encode("utf-8")) / 4)

    async def close(self) -> None:
        if self._owns_clients:
            await self._ollama_client.close()
            if self._external_client is not None:
                await self._external_client.close()
