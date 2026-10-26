import asyncio
import math
import os

import httpx
from pydantic import BaseModel, ValidationError


class EmbeddingServiceError(RuntimeError):
    pass


class _EmbedResponse(BaseModel):
    embeddings: list[list[float]]


class OllamaEmbeddingClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.model = model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.dimension = (
            dimension
            if dimension is not None
            else int(os.getenv("EMBEDDING_DIMENSION", "768"))
        )
        if self.dimension <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be greater than zero")

        self._owns_client = client is None
        self._client = (
            client if client is not None else httpx.AsyncClient(timeout=120.0)
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding inputs must not be empty")

        response: httpx.Response | None = None
        for attempt in range(3):
            try:
                response = await self._client.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": self.model,
                        "input": texts,
                        "truncate": False,
                    },
                )
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise EmbeddingServiceError(
                        f"Could not connect to Ollama at {self.base_url}"
                    ) from exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or attempt == 2:
                    raise EmbeddingServiceError(
                        f"Ollama embedding request failed with HTTP "
                        f"{exc.response.status_code}"
                    ) from exc

            await asyncio.sleep(0.5 * (2**attempt))

        if response is None:
            raise EmbeddingServiceError("Ollama returned no embedding response")
        try:
            embeddings = _EmbedResponse.model_validate(response.json()).embeddings
        except (ValueError, ValidationError) as exc:
            raise EmbeddingServiceError(
                "Ollama returned an invalid embedding response"
            ) from exc

        if len(embeddings) != len(texts):
            raise EmbeddingServiceError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        for vector in embeddings:
            if len(vector) != self.dimension:
                raise EmbeddingServiceError(
                    f"Embedding dimension {len(vector)} does not match configured "
                    f"dimension {self.dimension}"
                )
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingServiceError("Embedding contains a non-finite value")
        return embeddings

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
