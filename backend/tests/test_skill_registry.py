import unittest
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.skills import registry as builtin_registry
from app.skills.registry import SkillNotFoundError, SkillRegistry


class SampleArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


class SkillRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.registry = SkillRegistry()

    async def test_registers_and_invokes_a_validated_sync_skill(self) -> None:
        @self.registry.skill(
            name="uppercase_text",
            description="Convert text to uppercase.",
            arguments_model=SampleArguments,
        )
        def uppercase(arguments: SampleArguments) -> dict[str, str]:
            return {"result": arguments.value.upper()}

        result = await self.registry.invoke(
            "uppercase_text",
            {"value": "hello"},
        )

        self.assertEqual(result, {"result": "HELLO"})
        self.assertIs(uppercase, self.registry.get("uppercase_text").handler)

    async def test_invokes_async_skills(self) -> None:
        @self.registry.skill(
            name="async_text",
            description="Return text asynchronously.",
            arguments_model=SampleArguments,
        )
        async def async_text(arguments: SampleArguments) -> dict[str, str]:
            return {"result": arguments.value}

        result = await self.registry.invoke("async_text", {"value": "ready"})

        self.assertEqual(result, {"result": "ready"})

    async def test_rejects_invalid_arguments_and_unknown_skills(self) -> None:
        @self.registry.skill(
            name="validated_text",
            description="Accept a validated text argument.",
            arguments_model=SampleArguments,
        )
        def validated_text(arguments: SampleArguments) -> str:
            return arguments.value

        with self.assertRaises(ValidationError):
            await self.registry.invoke(
                "validated_text",
                {"value": "", "unexpected": True},
            )
        with self.assertRaises(SkillNotFoundError):
            await self.registry.invoke("not_registered", {})

    def test_rejects_duplicate_and_invalid_skill_names(self) -> None:
        @self.registry.skill(
            name="sample",
            description="First registration.",
            arguments_model=SampleArguments,
        )
        def first(arguments: SampleArguments) -> str:
            return arguments.value

        with self.assertRaisesRegex(ValueError, "already registered"):

            @self.registry.skill(
                name="sample",
                description="Duplicate registration.",
                arguments_model=SampleArguments,
            )
            def duplicate(arguments: SampleArguments) -> str:
                return arguments.value

        with self.assertRaisesRegex(ValueError, "Skill names"):

            @self.registry.skill(
                name="Uppercase",
                description="Invalid name.",
                arguments_model=SampleArguments,
            )
            def invalid(arguments: SampleArguments) -> str:
                return arguments.value

        self.assertEqual(first(SampleArguments(value="ok")), "ok")

    def test_exposes_function_call_schema_for_registered_skills(self) -> None:
        @self.registry.skill(
            name="schema_sample",
            description="Demonstrate a JSON Schema.",
            arguments_model=SampleArguments,
        )
        def schema_sample(arguments: SampleArguments) -> str:
            return arguments.value

        tools = self.registry.tool_definitions()

        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["function"]["name"], "schema_sample")
        self.assertEqual(
            tools[0]["function"]["parameters"]["properties"]["value"]["type"],
            "string",
        )

    async def test_builtin_text_stats_skill_is_registered(self) -> None:
        result: Any = await builtin_registry.invoke(
            "text_stats",
            {"text": "alpha beta\ngamma"},
        )

        self.assertEqual(
            result,
            {"characters": 16, "words": 3, "lines": 2},
        )


if __name__ == "__main__":
    unittest.main()
