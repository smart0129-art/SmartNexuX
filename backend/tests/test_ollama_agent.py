import json
import unittest
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.services.ollama_agent import (
    AgentProtocolError,
    AgentStepLimitError,
    OllamaAgentService,
)
from app.skills.registry import SkillRegistry


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


def create_registry() -> SkillRegistry:
    registry = SkillRegistry()

    @registry.skill(
        name="echo_text",
        description="Return the supplied text.",
        arguments_model=EchoArguments,
    )
    def echo_text(arguments: EchoArguments) -> dict[str, str]:
        return {"text": arguments.text}

    return registry


class OllamaAgentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_a_valid_final_answer(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "qwen2.5vl:3b")
            self.assertEqual(payload["stream"], False)
            self.assertIn("properties", payload["format"])
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "action": "final_answer",
                                "skill_name": "",
                                "arguments": {},
                                "answer": "The answer is 42.",
                            }
                        ),
                    }
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = OllamaAgentService(
            create_registry(),
            model="qwen2.5vl:3b",
            client=client,
        )
        try:
            result = await service.run("What is the answer?")
        finally:
            await client.aclose()

        self.assertEqual(result.answer, "The answer is 42.")
        self.assertEqual(result.tool_calls, [])

    async def test_executes_skill_and_passes_observation_back_to_model(self) -> None:
        requests: list[dict[str, Any]] = []
        decisions = [
            {
                "action": "call_skill",
                "skill_name": "echo_text",
                "arguments": {"text": "hello"},
                "answer": "",
            },
            {
                "action": "final_answer",
                "skill_name": "",
                "arguments": {},
                "answer": "The skill returned hello.",
            },
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            requests.append(payload)
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(decisions[len(requests) - 1]),
                    }
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = OllamaAgentService(create_registry(), client=client)
        try:
            result = await service.run("Use the echo skill for hello.")
        finally:
            await client.aclose()

        self.assertEqual(result.answer, "The skill returned hello.")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].result, {"text": "hello"})
        self.assertIsNone(result.tool_calls[0].error)
        self.assertIn("Skill observation", requests[1]["messages"][-1]["content"])
        self.assertIn('"result": {"text": "hello"}', requests[1]["messages"][-1]["content"])

    async def test_rejects_responses_outside_the_decision_schema(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": '{"action":"unknown"}',
                    }
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = OllamaAgentService(create_registry(), client=client)
        try:
            with self.assertRaises(AgentProtocolError):
                await service.run("Do something.")
        finally:
            await client.aclose()

    async def test_stops_when_the_model_exceeds_the_skill_call_limit(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "action": "call_skill",
                                "skill_name": "echo_text",
                                "arguments": {"text": "hello"},
                                "answer": "",
                            }
                        ),
                    }
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = OllamaAgentService(
            create_registry(),
            max_tool_calls=0,
            client=client,
        )
        try:
            with self.assertRaises(AgentStepLimitError):
                await service.run("Keep calling tools.")
        finally:
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
