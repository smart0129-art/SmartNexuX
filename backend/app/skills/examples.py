from pydantic import BaseModel, ConfigDict, Field

from app.skills.registry import skill


class TextStatsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20000)


@skill(
    name="text_stats",
    description="Count characters, words, and lines in supplied text.",
    arguments_model=TextStatsArguments,
)
def text_stats(arguments: TextStatsArguments) -> dict[str, int]:
    return {
        "characters": len(arguments.text),
        "words": len(arguments.text.split()),
        "lines": len(arguments.text.splitlines()),
    }
