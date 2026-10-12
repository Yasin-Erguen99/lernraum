"""Text extraction helpers for uploaded Lernraum materials.

Original files are always kept intact. Extraction is a convenience for search and
AI context, and image OCR is deliberately left to a later integration.
"""

from __future__ import annotations

import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

MAX_UNPACKED_XML_BYTES = 20 * 1024 * 1024


def _archive_read(archive: zipfile.ZipFile, name: str, remaining: int) -> tuple[bytes, int]:
    info = archive.getinfo(name)
    if info.file_size > remaining:
        raise ValueError("Das Office-Dokument enthält zu viele entpackte XML-Daten.")
    with archive.open(info) as stream:
        data = stream.read(remaining + 1)
    if len(data) > remaining:
        raise ValueError("Das Office-Dokument enthält zu viele entpackte XML-Daten.")
    return data, remaining - len(data)


def _plain_text(path: Path) -> tuple[str, list[dict[str, Any]]]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    return text, [{"page": 1, "text": text}]


def _pdf(path: Path) -> tuple[str, list[dict[str, Any]]]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("PDF-Textextraktion benötigt das optionale Paket pypdf.") from exc

    reader = PdfReader(str(path))
    pages: list[dict[str, Any]] = []
    for number, page in enumerate(reader.pages, start=1):
        pages.append({"page": number, "text": page.extract_text() or ""})
    return "\n\n".join(page["text"] for page in pages), pages


def _xml_text(xml_bytes: bytes) -> str:
    root = ElementTree.fromstring(xml_bytes)
    chunks: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            chunks.append(node.text)
        elif node.tag.endswith("}tab"):
            chunks.append("\t")
        elif node.tag.endswith("}br"):
            chunks.append("\n")
        elif node.tag.endswith("}p"):
            chunks.append("\n")
    text = "".join(chunks)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _docx(path: Path) -> tuple[str, list[dict[str, Any]]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names:
            raise ValueError("Die DOCX-Datei enthält kein Word-Dokument.")
        remaining = MAX_UNPACKED_XML_BYTES
        document_xml, remaining = _archive_read(archive, "word/document.xml", remaining)
        text = _xml_text(document_xml)
        # Headers, footers and notes often contain useful course information.
        extra = []
        for name in sorted(names):
            if re.fullmatch(r"word/(?:header|footer)\d+\.xml", name):
                part_xml, remaining = _archive_read(archive, name, remaining)
                part_text = _xml_text(part_xml)
                if part_text:
                    extra.append(part_text)
        if extra:
            text = "\n\n".join([text, *extra]).strip()
    return text, [{"page": 1, "text": text}]


def _pptx(path: Path) -> tuple[str, list[dict[str, Any]]]:
    with zipfile.ZipFile(path) as archive:
        slide_names = [
            name for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        slide_names.sort(key=lambda value: int(re.search(r"slide(\d+)", value).group(1)))
        if not slide_names:
            raise ValueError("Die PPTX-Datei enthält keine Folien.")
        pages: list[dict[str, Any]] = []
        remaining = MAX_UNPACKED_XML_BYTES
        for number, name in enumerate(slide_names, start=1):
            slide_xml, remaining = _archive_read(archive, name, remaining)
            pages.append({"page": number, "text": _xml_text(slide_xml)})
    return "\n\n".join(page["text"] for page in pages), pages


def extract(path: Path, name: str, mime: str | None = None) -> dict[str, Any]:
    """Return extraction metadata and text without modifying the source file."""
    suffix = Path(name).suffix.lower()
    guessed_mime = (mime or mimetypes.guess_type(name)[0] or "").lower()
    base = {
        "extraction_status": "ready",
        "extraction_message": "",
        "text": "",
        "pages": [],
        "page_count": 0,
    }

    if guessed_mime.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}:
        base["extraction_status"] = "needs_ocr"
        base["extraction_message"] = "Bilddatei gespeichert; Texterkennung (OCR) ist noch nicht aktiviert."
        return base

    try:
        if suffix == ".pdf" or guessed_mime == "application/pdf":
            text, pages = _pdf(path)
        elif suffix == ".docx" or guessed_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text, pages = _docx(path)
        elif suffix == ".pptx" or guessed_mime == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            text, pages = _pptx(path)
        elif suffix in {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".log", ".py", ".js", ".css"} or guessed_mime.startswith("text/") or guessed_mime in {"application/json", "application/xml"}:
            text, pages = _plain_text(path)
        else:
            base["extraction_status"] = "unsupported"
            base["extraction_message"] = "Für dieses Dateiformat ist keine Textextraktion verfügbar."
            return base
    except RuntimeError as exc:
        base["extraction_status"] = "unsupported"
        base["extraction_message"] = str(exc)
        return base
    except Exception as exc:
        base["extraction_status"] = "error"
        base["extraction_message"] = f"Textextraktion fehlgeschlagen: {exc}"
        return base

    base.update(text=text, pages=pages, page_count=len(pages))
    return base
