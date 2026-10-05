import io
import logging
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import pymupdf
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRESENTATION_NS = (
    "http://schemas.openxmlformats.org/presentationml/2006/main"
)
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
SHEET_DRAWING_NS = (
    "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
)
IMAGE_OCR_MARKER = "[Image OCR]"


@dataclass(frozen=True)
class DocumentImage:
    image_id: str
    data: bytes
    location_type: str
    location_value: str
    ocr_index: int | None = None


def extract_document_images(source: Path) -> list[DocumentImage]:
    extension = source.suffix.lower()
    if extension == ".pdf":
        return _extract_pdf_pages(source)
    if extension == ".docx":
        return _extract_docx_images(source)
    if extension == ".pptx":
        return _extract_pptx_images(source)
    if extension == ".xlsx":
        return _extract_xlsx_images(source)
    return []


def associate_images_with_chunks(
    chunks: list[Any],
    images: list[DocumentImage],
    extension: str,
) -> None:
    if not chunks or not images:
        return

    by_location: dict[tuple[str, str], list[str]] = {}
    for image in images:
        by_location.setdefault(
            (image.location_type, image.location_value), []
        ).append(image.image_id)

    if extension == ".pdf":
        for chunk in chunks:
            page_number = chunk.metadata.get("page_number")
            if isinstance(page_number, int):
                _add_image_ids(
                    chunk,
                    by_location.get(("page", str(page_number)), []),
                )
        return

    if extension == ".pptx":
        for chunk in chunks:
            slide_number = chunk.metadata.get("slide_number")
            if isinstance(slide_number, int):
                _add_image_ids(
                    chunk,
                    by_location.get(("slide", str(slide_number)), []),
                )
        return

    if extension == ".docx":
        ocr_images = [image for image in images if image.ocr_index is not None]
        ocr_count = sum(chunk.content.count(IMAGE_OCR_MARKER) for chunk in chunks)
        if ocr_count != len(ocr_images):
            return
        image_by_index = {
            image.ocr_index: image.image_id for image in ocr_images
        }
        image_index = 0
        for chunk in chunks:
            for _ in range(chunk.content.count(IMAGE_OCR_MARKER)):
                image_id = image_by_index.get(image_index)
                if image_id is not None:
                    _add_image_ids(chunk, [image_id])
                image_index += 1
        return

    if extension == ".xlsx":
        chunks_by_sheet: dict[str, list[Any]] = {}
        for chunk in chunks:
            sheet_name = chunk.metadata.get("sheet_name")
            if isinstance(sheet_name, str):
                chunks_by_sheet.setdefault(sheet_name, []).append(chunk)
        for sheet_name, sheet_chunks in chunks_by_sheet.items():
            sheet_images = by_location.get(("sheet", sheet_name), [])
            ocr_chunks = [
                chunk
                for chunk in sheet_chunks
                for _ in range(chunk.content.count(IMAGE_OCR_MARKER))
            ]
            if len(ocr_chunks) != len(sheet_images):
                continue
            for chunk, image_id in zip(ocr_chunks, sheet_images, strict=True):
                _add_image_ids(chunk, [image_id])


def _add_image_ids(chunk: Any, image_ids: list[str]) -> None:
    if not image_ids:
        return
    chunk.metadata["image_asset_ids"] = list(
        dict.fromkeys(
            [*chunk.metadata.get("image_asset_ids", []), *image_ids]
        )
    )


def _extract_pdf_pages(source: Path) -> list[DocumentImage]:
    images: list[DocumentImage] = []
    with pymupdf.open(source) as document:
        for page_number, page in enumerate(document, start=1):
            if not page.get_images(full=True) and not page.get_drawings():
                continue
            scale = min(1.5, 1600 / max(page.rect.width, page.rect.height))
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            images.append(
                DocumentImage(
                    image_id=uuid4().hex,
                    data=pixmap.tobytes(output="jpeg", jpg_quality=82),
                    location_type="page",
                    location_value=str(page_number),
                )
            )
    return images


def _extract_docx_images(source: Path) -> list[DocumentImage]:
    document_part = "word/document.xml"
    relationships_part = "word/_rels/document.xml.rels"
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        if document_part not in names or relationships_part not in names:
            return []
        relationships = _relationship_targets(
            archive,
            document_part,
            relationships_part,
        )
        root = ElementTree.fromstring(archive.read(document_part))
        images: list[DocumentImage] = []
        for blip in root.iter(f"{{{DRAWING_NS}}}blip"):
            relationship_id = blip.get(f"{{{REL_NS}}}embed")
            target = relationships.get(relationship_id or "")
            if target is None or target not in names:
                continue
            data = _normalized_image(archive.read(target), target)
            if data is not None:
                images.append(
                    DocumentImage(
                        image_id=uuid4().hex,
                        data=data,
                        location_type="document",
                        location_value="",
                        ocr_index=len(images),
                    )
                )
    return images


def _extract_pptx_images(source: Path) -> list[DocumentImage]:
    images: list[DocumentImage] = []
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        presentation_part = "ppt/presentation.xml"
        presentation_rels = _rels_path(presentation_part)
        if presentation_part not in names or presentation_rels not in names:
            return []
        slide_targets = _relationship_targets(
            archive,
            presentation_part,
            presentation_rels,
        )
        presentation = ElementTree.fromstring(archive.read(presentation_part))
        slide_parts = [
            slide_targets[relationship_id]
            for slide in presentation.iter(f"{{{PRESENTATION_NS}}}sldId")
            if (relationship_id := slide.get(f"{{{REL_NS}}}id"))
            in slide_targets
        ]
        for slide_number, slide_part in enumerate(slide_parts, start=1):
            relationships_part = _rels_path(slide_part)
            if slide_part not in names or relationships_part not in names:
                continue
            relationships = _relationship_targets(
                archive,
                slide_part,
                relationships_part,
            )
            root = ElementTree.fromstring(archive.read(slide_part))
            for blip in root.iter(f"{{{DRAWING_NS}}}blip"):
                target = relationships.get(
                    blip.get(f"{{{REL_NS}}}embed") or ""
                )
                if target is None or target not in names:
                    continue
                data = _normalized_image(archive.read(target), target)
                if data is not None:
                    images.append(
                        DocumentImage(
                            image_id=uuid4().hex,
                            data=data,
                            location_type="slide",
                            location_value=str(slide_number),
                        )
                    )
    return images


def _extract_xlsx_images(source: Path) -> list[DocumentImage]:
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        workbook_part = "xl/workbook.xml"
        workbook_rels = "xl/_rels/workbook.xml.rels"
        if workbook_part not in names or workbook_rels not in names:
            return []

        workbook_root = ElementTree.fromstring(archive.read(workbook_part))
        workbook_targets = _relationship_targets(
            archive,
            workbook_part,
            workbook_rels,
        )
        images: list[DocumentImage] = []
        for sheet in workbook_root.iter(f"{{{SHEET_NS}}}sheet"):
            sheet_name = sheet.get("name")
            relationship_id = sheet.get(f"{{{REL_NS}}}id")
            sheet_part = workbook_targets.get(relationship_id or "")
            if not sheet_name or sheet_part is None or sheet_part not in names:
                continue

            sheet_rels_part = _rels_path(sheet_part)
            if sheet_rels_part not in names:
                continue
            sheet_root = ElementTree.fromstring(archive.read(sheet_part))
            sheet_targets = _relationship_targets(
                archive,
                sheet_part,
                sheet_rels_part,
            )
            for drawing in sheet_root.iter(f"{{{SHEET_NS}}}drawing"):
                drawing_part = sheet_targets.get(
                    drawing.get(f"{{{REL_NS}}}id") or ""
                )
                if drawing_part is None or drawing_part not in names:
                    continue
                drawing_rels_part = _rels_path(drawing_part)
                if drawing_rels_part not in names:
                    continue
                drawing_targets = _relationship_targets(
                    archive,
                    drawing_part,
                    drawing_rels_part,
                )
                drawing_root = ElementTree.fromstring(
                    archive.read(drawing_part)
                )
                anchors = [
                    anchor
                    for anchor_name in ("absoluteAnchor", "oneCellAnchor", "twoCellAnchor")
                    for anchor in drawing_root.iter(
                        f"{{{SHEET_DRAWING_NS}}}{anchor_name}"
                    )
                ]
                for anchor in anchors:
                    for blip in anchor.iter(f"{{{DRAWING_NS}}}blip"):
                        target = drawing_targets.get(
                            blip.get(f"{{{REL_NS}}}embed") or ""
                        )
                        if target is None or target not in names:
                            continue
                        data = _normalized_image(archive.read(target), target)
                        if data is not None:
                            images.append(
                                DocumentImage(
                                    image_id=uuid4().hex,
                                    data=data,
                                    location_type="sheet",
                                    location_value=sheet_name,
                                )
                            )
    return images


def _relationship_targets(
    archive: zipfile.ZipFile,
    source_part: str,
    relationships_part: str,
) -> dict[str, str]:
    source_directory = posixpath.dirname(source_part)
    root = ElementTree.fromstring(archive.read(relationships_part))
    return {
        relationship.get("Id", ""): posixpath.normpath(
            posixpath.join(
                source_directory,
                relationship.get("Target", ""),
            )
        ).lstrip("/")
        for relationship in root
        if relationship.get("TargetMode") != "External"
        and relationship.get("Id")
    }


def _rels_path(part: str) -> str:
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", filename + ".rels")


def _normalized_image(data: bytes, filename: str) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
            return output.getvalue()
    except (OSError, ValueError) as exc:
        logger.warning("Skipping unsupported embedded image '%s': %s", filename, exc)
        return None


def split_pptx_slides(markdown: str) -> list[tuple[int, str]]:
    parts = re.split(
        r"<!--\s*Slide number:\s*(\d+)\s*-->",
        markdown,
        flags=re.IGNORECASE,
    )
    slides: list[tuple[int, str]] = []
    for index in range(1, len(parts), 2):
        content = parts[index + 1].strip()
        if content:
            slides.append((int(parts[index]), content))
    if slides:
        return slides
    return [(1, markdown)]


def split_xlsx_sheets(markdown: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^## (.+?)\s*$", markdown)
    sheets = [
        (parts[index].strip(), parts[index + 1].strip())
        for index in range(1, len(parts), 2)
        if parts[index + 1].strip()
    ]
    if sheets:
        return sheets
    return [("", markdown)]
