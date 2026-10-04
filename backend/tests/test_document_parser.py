import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.document_parser import DocumentParser, chunk_markdown


class ChunkMarkdownTests(unittest.TestCase):
    def test_splits_by_heading_paragraph_and_image_ocr_boundaries(self) -> None:
        markdown = (
            "# First section\n\n"
            "Intro paragraph.\n\n"
            "*[Image OCR]\nRecognized chart label\n[End OCR]*\n\n"
            "## Second section\n\n"
            "Closing paragraph."
        )

        chunks = chunk_markdown(markdown, max_chars=55, overlap_chars=10)

        self.assertEqual(len(chunks), 3)
        self.assertTrue(chunks[0].startswith("# First section"))
        self.assertIn("Intro paragraph.", chunks[0])
        self.assertIn("*[Image OCR]", chunks[1])
        self.assertIn("## Second section", chunks[2])

    def test_long_paragraph_is_bounded_and_overlapped(self) -> None:
        paragraph = " ".join(f"word{index}" for index in range(80))

        chunks = chunk_markdown(paragraph, max_chars=80, overlap_chars=16)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 80 for chunk in chunks))
        self.assertIn(chunks[0].split()[-1], chunks[1].split())

    def test_rejects_invalid_chunk_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_chars"):
            chunk_markdown("content", max_chars=0)
        with self.assertRaisesRegex(ValueError, "overlap_chars"):
            chunk_markdown("content", max_chars=10, overlap_chars=10)


class DocumentParserTests(unittest.TestCase):
    def test_vision_ocr_failure_keeps_native_document_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "presentation.pptx"
            source.write_bytes(b"pptx")
            client = Mock()
            client.chat.completions.create.side_effect = RuntimeError(
                "prediction aborted, token repeat limit reached"
            )

            with (
                patch("app.services.document_parser.OpenAI", return_value=client),
                patch("app.services.document_parser.MarkItDown") as markitdown,
                self.assertLogs(
                    "app.services.document_parser",
                    level="WARNING",
                ) as captured_logs,
            ):
                converter = markitdown.return_value

                def convert_local(_: Path) -> SimpleNamespace:
                    recorder = markitdown.call_args.kwargs["llm_client"]
                    with self.assertRaisesRegex(RuntimeError, "token repeat limit"):
                        recorder.chat.completions.create()
                    return SimpleNamespace(
                        text_content="# Slide 1\nNative slide text."
                    )

                converter.convert_local.side_effect = convert_local

                chunks = DocumentParser()._parse_sync(source)

            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].content, "# Slide 1\nNative slide text.")
            self.assertTrue(
                any(
                    "continuing with native document content" in message
                    and "token repeat limit reached" in message
                    for message in captured_logs.output
                )
            )
            client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
