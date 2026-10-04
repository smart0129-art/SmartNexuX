import json
import unittest

import httpx

from app.services.ollama_embeddings import (
    EmbeddingServiceError,
    OllamaEmbeddingClient,
)


class OllamaEmbeddingClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_model_and_returns_validated_vectors(self) -> None:
        requests: list[dict[str, object]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"model": "nomic-embed-text", "embeddings": [[0.1, 0.2]]},
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        embedding_client = OllamaEmbeddingClient(
            base_url="http://ollama:11434",
            model="nomic-embed-text",
            dimension=2,
            client=http_client,
        )
        try:
            vectors = await embedding_client.embed_texts(["search_query: sample"])
        finally:
            await http_client.aclose()

        self.assertEqual(vectors, [[0.1, 0.2]])
        self.assertEqual(
            requests,
            [
                {
                    "model": "nomic-embed-text",
                    "input": ["search_query: sample"],
                    "truncate": False,
                }
            ],
        )

    async def test_rejects_embedding_dimension_mismatch(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"model": "nomic-embed-text", "embeddings": [[0.1]]},
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        embedding_client = OllamaEmbeddingClient(
            dimension=2,
            client=http_client,
        )
        try:
            with self.assertRaisesRegex(EmbeddingServiceError, "dimension"):
                await embedding_client.embed_texts(["sample"])
        finally:
            await http_client.aclose()


if __name__ == "__main__":
    unittest.main()
