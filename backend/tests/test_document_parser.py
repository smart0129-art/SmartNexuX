import unittest

from app.services.document_parser import chunk_markdown


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


if __name__ == "__main__":
    unittest.main()
