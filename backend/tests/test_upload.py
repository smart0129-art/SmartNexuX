import io
import tempfile
import unittest
from pathlib import Path

from app.main import UploadTooLargeError, _copy_upload


class CopyUploadTests(unittest.TestCase):
    def test_copies_upload_in_bounded_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.txt"

            byte_count = _copy_upload(
                io.BytesIO(b"document"),
                destination,
                max_upload_bytes=32,
            )

            self.assertEqual(byte_count, 8)
            self.assertEqual(destination.read_bytes(), b"document")

    def test_rejects_upload_that_exceeds_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "sample.txt"

            with self.assertRaises(UploadTooLargeError):
                _copy_upload(
                    io.BytesIO(b"document"),
                    destination,
                    max_upload_bytes=4,
                )


if __name__ == "__main__":
    unittest.main()
