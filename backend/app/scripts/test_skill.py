import asyncio
import json

from app.skills import registry


async def main() -> None:
    result = await registry.invoke(
        "text_stats",
        {"text": "Skill registry test\nTwo lines"},
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
