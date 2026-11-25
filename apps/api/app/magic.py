"""File-type truth from bytes, not from URLs.

Imported from:
  * h2non/filetype.py — signature tables (PDF, ZIP/OOXML, OLE2, RAR, 7z, gzip, SQLite…)
  * pymupdf/PyMuPDF   — first-page text as a title fallback when the filename lies
  * Apache Tika       — the "trust magic over extension" principle

`/download?id=42` is a PDF with no extension; `/report.pdf` is sometimes an HTML login page.
Both are common reasons a search engine never shows the file. This module fixes the label.
"""
from __future__ import annotations

import io
import re

ZIP_FAMILY = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "epub": "application/epub+zip",
}

MAGIC = [
    (b"%PDF-", "pdf", "application/pdf"),
    (b"PK\x03\x04", "zip", "application/zip"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "doc", "application/msword"),
    (b"Rar!\x1a\x07", "rar", "application/vnd.rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z", "application/x-7z-compressed"),
    (b"\x1f\x8b", "gz", "application/gzip"),
    (b"SQLite format 3\x00", "sqlite", "application/vnd.sqlite3"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF8", "gif", "image/gif"),
    (b"RIFF", "wav", "audio/wav"),
    (b"ID3", "mp3", "audio/mpeg"),
    (b"OggS", "ogg", "audio/ogg"),
    (b"\x00\x00\x00", None, None),  # placeholder, resolved by ftyp check below
]


def sniff(data: bytes) -> tuple[str | None, str | None]:
    """Return (extension, mime) from magic bytes, or (None, None)."""
    if not data:
        return None, None
    head = data[:4096]
    if b"ftyp" in head[:16]:
        return "mp4", "video/mp4"
    for signature, ext, mime in MAGIC:
        if ext is None:
            continue
        if head.startswith(signature):
            if ext == "zip":
                return _zip_kind(data), ZIP_FAMILY.get(_zip_kind(data) or "", "application/zip")
            return ext, mime
    # OLE2: distinguish doc/xls/ppt by stream names when possible
    if head.startswith(MAGIC[2][0]):
        if b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k" in data[:8192]:
            return "xls", "application/vnd.ms-excel"
        if b"P\x00o\x00w\x00e\x00r\x00P\x00o\x00i\x00n\x00t" in data[:8192]:
            return "ppt", "application/vnd.ms-powerpoint"
        return "doc", "application/msword"
    if head[:512].lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        return "html", "text/html"
    return None, None


def _zip_kind(data: bytes) -> str:
    try:
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        if "ppt/presentation.xml" in names:
            return "pptx"
        if any(n.startswith("OEBPS/") or n == "mimetype" for n in names):
            return "epub"
        return "zip"
    except Exception:
        return "zip"


def pdf_title(data: bytes) -> str:
    """First meaningful line of a PDF, used when the filename is opaque."""
    try:
        import pymupdf  # type: ignore

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.metadata and doc.metadata.get("title"):
                title = (doc.metadata["title"] or "").strip()
                if 4 < len(title) < 180:
                    return title
            text = (doc[0].get_text() or "").strip()
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if 8 < len(line) < 180 and sum(ch.isalpha() for ch in line) > 6:
                return line
    except Exception:
        pass
    return ""


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"
