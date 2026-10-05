import asyncio
import io
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pymupdf
from markitdown import MarkItDown, StreamInfo
from openai import OpenAI

from app.services.document_images import split_pptx_slides, split_xlsx_sheets

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentChunk:
    chunk_index: int
    content: str
    metadata: dict[str, str | int]


class _CompletionRecorder:
    def __init__(self, completions: Any, errors: list[Exception]) -> None:
        self._completions = completions
        self._errors = errors

    def create(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._completions.create(*args, **kwargs)
        except Exception as exc:
            self._errors.append(exc)
            raise


class _VisionClientRecorder:
    def __init__(self, client: OpenAI) -> None:
        self.errors: list[Exception] = []
        self.chat = SimpleNamespace(
            completions=_CompletionRecorder(client.chat.completions, self.errors)
        )


class DocumentParser:
    SUPPORTED_EXTENSIONS = frozenset({
        ".bmp",
        ".csv",
        ".docx",
        ".gif",
        ".htm",
        ".html",
        ".jpeg",
        ".jpg",
        ".md",
        ".pdf",
        ".png",
        ".pptx",
        ".tif",
        ".tiff",
        ".txt",
        ".webp",
        ".xls",
        ".xlsx",
    })

    def __init__(
        self,
        chunk_max_chars: int | None = None,
        chunk_overlap_chars: int | None = None,
        ollama_base_url: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        self.chunk_max_chars = (
            chunk_max_chars
            if chunk_max_chars is not None
            else int(os.getenv("CHUNK_MAX_CHARS", "4000"))
        )
        self.chunk_overlap_chars = (
            chunk_overlap_chars
            if chunk_overlap_chars is not None
            else int(os.getenv("CHUNK_OVERLAP_CHARS", "300"))
        )
        if self.chunk_max_chars <= 0:
            raise ValueError("CHUNK_MAX_CHARS must be greater than zero")
        if not 0 <= self.chunk_overlap_chars < self.chunk_max_chars:
            raise ValueError(
                "CHUNK_OVERLAP_CHARS must be non-negative and smaller than "
                "CHUNK_MAX_CHARS"
            )

        self.ollama_base_url = (
            ollama_base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.vision_model = vision_model or os.getenv(
            "VISION_MODEL", "qwen2.5vl:3b"
        )

    async def parse(self, source: str | Path) -> list[DocumentChunk]:
        return await asyncio.to_thread(self._parse_sync, Path(source))

    def _parse_sync(self, source: Path) -> list[DocumentChunk]:
        if not source.is_file():
            raise FileNotFoundError(f"Document does not exist: {source}")

        extension = source.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported document extension: {extension or '(none)'}")

        client = OpenAI(
            base_url=f"{self.ollama_base_url}/v1",
            api_key="ollama",
            timeout=120.0,
            max_retries=2,
        )
        recorder = _VisionClientRecorder(client)
        try:
            converter = MarkItDown(
                enable_plugins=True,
                llm_client=recorder,
                llm_model=self.vision_model,
            )
            if extension == ".pdf":
                page_contents = self._convert_pdf_pages(source, converter, recorder)
            else:
                result = converter.convert_local(source)
                self._log_vision_errors(source, recorder)
                if extension == ".pptx":
                    page_contents = split_pptx_slides(result.text_content)
                elif extension == ".xlsx":
                    page_contents = split_xlsx_sheets(result.text_content)
                else:
                    page_contents = [(None, result.text_content)]

            chunks: list[DocumentChunk] = []
            for location, markdown in page_contents:
                metadata: dict[str, str | int] = {
                    "source_name": source.name,
                    "source_type": extension.lstrip("."),
                }
                if isinstance(location, int):
                    metadata[
                        "page_number" if extension == ".pdf" else "slide_number"
                    ] = location
                elif isinstance(location, str):
                    if extension == ".xlsx":
                        metadata["sheet_name"] = location
                for content in chunk_markdown(
                    markdown,
                    max_chars=self.chunk_max_chars,
                    overlap_chars=self.chunk_overlap_chars,
                ):
                    chunks.append(
                        DocumentChunk(
                            chunk_index=len(chunks),
                            content=content,
                            metadata=metadata.copy(),
                        )
                    )

            if not chunks:
                raise ValueError(f"No text could be extracted from document: {source}")
            return chunks
        finally:
            client.close()

    def _convert_pdf_pages(
        self,
        source: Path,
        converter: MarkItDown,
        recorder: _VisionClientRecorder,
    ) -> Iterator[tuple[int, str]]:
        with pymupdf.open(source) as document:
            for page_index in range(document.page_count):
                single_page = pymupdf.open()
                try:
                    single_page.insert_pdf(
                        document,
                        from_page=page_index,
                        to_page=page_index,
                    )
                    page_bytes = single_page.tobytes()
                finally:
                    single_page.close()

                page_number = page_index + 1
                result = converter.convert_stream(
                    io.BytesIO(page_bytes),
                    stream_info=StreamInfo(
                        extension=".pdf",
                        filename=f"{source.name}#page={page_number}",
                    ),
                )
                self._log_vision_errors(source, recorder, page_number)
                page_markdown = result.text_content.strip()
                if page_markdown:
                    yield page_number, page_markdown

    @staticmethod
    def _log_vision_errors(
        source: Path,
        recorder: _VisionClientRecorder,
        page_number: int | None = None,
    ) -> None:
        location = source.name
        if page_number is not None:
            location = f"{location} (page {page_number})"

        errors = recorder.errors[:]
        recorder.errors.clear()
        for error in errors:
            logger.warning(
                "Ollama vision OCR failed while parsing '%s'; continuing with "
                "native document content where available: %s",
                location,
                error,
            )


def chunk_markdown(
    markdown: str,
    max_chars: int = 4000,
    overlap_chars: int = 300,
) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if not 0 <= overlap_chars < max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")

    blocks = _split_semantic_blocks(markdown)
    chunks: list[str] = []
    current_blocks: list[str] = []
    current_length = 0

    def flush() -> None:
        nonlocal current_length
        if current_blocks:
            chunks.append("\n\n".join(current_blocks))
            current_blocks.clear()
            current_length = 0

    for block in blocks:
        if len(block) > max_chars:
            flush()
            chunks.extend(_split_long_block(block, max_chars, overlap_chars))
            continue

        added_length = len(block) + (2 if current_blocks else 0)
        if current_blocks and current_length + added_length > max_chars:
            flush()
            added_length = len(block)
        current_blocks.append(block)
        current_length += added_length

    flush()
    return chunks


def _split_semantic_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    current_lines: list[str] = []
    in_image_ocr = False

    def flush() -> None:
        if current_lines:
            block = "\n".join(current_lines).strip()
            if block:
                blocks.append(block)
            current_lines.clear()

    for line in markdown.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        is_heading = re.match(r"^#{1,6}\s", stripped) is not None
        is_image = stripped.startswith("*[Image OCR]") or stripped.startswith("![")

        if (is_heading or is_image) and current_lines and not in_image_ocr:
            flush()
        if not stripped and not in_image_ocr:
            flush()
            continue

        current_lines.append(line)
        if stripped.startswith("*[Image OCR]"):
            in_image_ocr = True
        if stripped.endswith("[End OCR]*"):
            in_image_ocr = False
            flush()
        elif stripped.startswith("![") and not in_image_ocr:
            flush()

    flush()
    return blocks


def _split_long_block(block: str, max_chars: int, overlap_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(block):
        end = min(start + max_chars, len(block))
        if end < len(block):
            boundaries = [
                block.rfind("\n", start, end),
                block.rfind(". ", start, end),
                block.rfind(" ", start, end),
            ]
            boundary = max(boundaries)
            if boundary > start + max_chars // 2:
                end = boundary + (1 if block[boundary] == "." else 0)

        chunk = block[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(block):
            break

        start = max(start + 1, end - overlap_chars)
        while start < len(block) and block[start].isspace():
            start += 1
    return chunks
