import asyncio
import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Generic, Mapping, TypeVar

from pydantic import BaseModel


ArgumentsT = TypeVar("ArgumentsT", bound=BaseModel)
_SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SkillNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class SkillDefinition(Generic[ArgumentsT]):
    name: str
    description: str
    arguments_model: type[ArgumentsT]
    handler: Callable[[ArgumentsT], Any]

    def to_tool_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_model.model_json_schema(),
            },
        }

    async def invoke(self, arguments: Mapping[str, Any]) -> Any:
        validated_arguments = self.arguments_model.model_validate(arguments)
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(validated_arguments)

        result = await asyncio.to_thread(self.handler, validated_arguments)
        if inspect.isawaitable(result):
            return await result
        return result


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition[Any]] = {}

    def skill(
        self,
        *,
        name: str,
        description: str,
        arguments_model: type[ArgumentsT],
    ) -> Callable[[Callable[[ArgumentsT], Any]], Callable[[ArgumentsT], Any]]:
        def decorator(
            handler: Callable[[ArgumentsT], Any],
        ) -> Callable[[ArgumentsT], Any]:
            self.register(
                SkillDefinition(
                    name=name,
                    description=description,
                    arguments_model=arguments_model,
                    handler=handler,
                )
            )
            return handler

        return decorator

    def register(self, definition: SkillDefinition[Any]) -> None:
        if not _SKILL_NAME_PATTERN.fullmatch(definition.name):
            raise ValueError(
                "Skill names must start with a lowercase letter and contain "
                "only lowercase letters, digits, and underscores"
            )
        if not definition.description.strip():
            raise ValueError("Skill descriptions must not be empty")
        if definition.name in self._skills:
            raise ValueError(f"Skill '{definition.name}' is already registered")
        self._skills[definition.name] = definition

    def get(self, name: str) -> SkillDefinition[Any]:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(f"Skill '{name}' is not registered") from exc

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.arguments_model.model_json_schema(),
            }
            for definition in self._skills.values()
        ]

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            definition.to_tool_definition()
            for definition in self._skills.values()
        ]

    async def invoke(self, name: str, arguments: Mapping[str, Any]) -> Any:
        return await self.get(name).invoke(arguments)


registry = SkillRegistry()


def skill(
    *,
    name: str,
    description: str,
    arguments_model: type[ArgumentsT],
) -> Callable[[Callable[[ArgumentsT], Any]], Callable[[ArgumentsT], Any]]:
    return registry.skill(
        name=name,
        description=description,
        arguments_model=arguments_model,
    )
