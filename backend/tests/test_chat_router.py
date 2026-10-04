import json
import unittest

import httpx

from app.services.chat_router import (
    ChatModelRouter,
    ChatModelSelectionError,
    ChatProviderConfigurationError,
)


def streaming_response(
    content: str,
    usage: dict[str, int] | None = None,
) -> httpx.Response:
    chunks = [
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        },
    ]
    if usage is not None:
        chunks.append(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "test-model",
                "choices": [],
                "usage": usage,
            }
        )
    body = "".join(
        f"data: {json.dumps(chunk)}\n\n"
        for chunk in chunks
    ) + "data: [DONE]\n\n"
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body.encode(),
    )


class ChatModelRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_tokens_and_provider_usage_from_ollama_route(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return streaming_response(
                "Hello!",
                {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        router = ChatModelRouter(
            ollama_base_url="http://ollama:11434",
            ollama_models="qwen2.5vl:3b",
            external_models="",
            http_client=client,
        )
        try:
            events = [
                event
                async for event in router.stream(
                    "Say hello.",
                    "ollama",
                    "qwen2.5vl:3b",
                )
            ]
        finally:
            await router.close()
            await client.aclose()

        self.assertEqual(requests[0].url.path, "/v1/chat/completions")
        request_payload = json.loads(requests[0].content)
        self.assertTrue(request_payload["stream"])
        self.assertTrue(request_payload["stream_options"]["include_usage"])
        self.assertEqual(
            [event.token for event in events if event.kind == "token"],
            ["Hello!"],
        )
        self.assertEqual(events[-1].usage.prompt_tokens, 8)
        self.assertEqual(events[-1].usage.source, "provider")

    async def test_estimates_usage_when_provider_does_not_return_it(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: streaming_response("Answer")
            )
        )
        router = ChatModelRouter(
            ollama_models="qwen2.5vl:3b",
            external_models="",
            http_client=client,
        )
        try:
            events = [
                event
                async for event in router.stream(
                    "Question",
                    "ollama",
                    "qwen2.5vl:3b",
                )
            ]
        finally:
            await router.close()
            await client.aclose()

        usage = events[-1].usage
        self.assertEqual(usage.source, "estimate")
        self.assertGreater(usage.total_tokens, 0)

    def test_lists_configured_models_and_rejects_unconfigured_routes(self) -> None:
        router = ChatModelRouter(
            ollama_models="qwen2.5vl:3b,qwen2.5vl:7b",
            external_models="gpt-4o-mini",
            external_api_key="test-key",
        )

        self.assertEqual(router.default_model, "qwen2.5vl:3b")
        self.assertEqual(
            router.resolve("openai_compatible", "gpt-4o-mini"),
            "gpt-4o-mini",
        )
        with self.assertRaises(ChatModelSelectionError):
            router.resolve("ollama", "unlisted-model")

    def test_requires_external_api_key_before_external_request(self) -> None:
        router = ChatModelRouter(
            ollama_models="qwen2.5vl:3b",
            external_models="gpt-4o-mini",
            external_api_key="",
        )

        with self.assertRaises(ChatProviderConfigurationError):
            router.resolve("openai_compatible", "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
