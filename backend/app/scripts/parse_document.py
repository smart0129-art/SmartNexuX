import argparse
import asyncio
import json
from pathlib import Path

from app.services.document_parser import DocumentParser


async def _parse_and_print(source: Path) -> None:
    chunks = await DocumentParser().parse(source)
    for chunk in chunks:
        print(
            json.dumps(
                {
                    "chunk_index": chunk.chunk_index,
                    "metadata": chunk.metadata,
                    "content": chunk.content,
                },
                ensure_ascii=False,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a document into semantic chunks.")
    parser.add_argument("source", type=Path, help="Path to a supported local document")
    args = parser.parse_args()
    asyncio.run(_parse_and_print(args.source))


if __name__ == "__main__":
    main()
