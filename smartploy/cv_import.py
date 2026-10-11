"""Bounded, local, text-only CV import. Uploaded CVs are never sent to ObumAI."""
from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

from pypdf import PdfReader


MAX_CV_BYTES = 5 * 1024 * 1024
MAX_CV_TEXT = 60_000
MAX_ZIP_EXPANDED_BYTES = 20 * 1024 * 1024


class CVImportError(ValueError):
    pass


def _clean_filename(filename: str) -> str:
    if not isinstance(filename, str) or not (1 <= len(filename) <= 160):
        raise CVImportError("Choose a PDF or DOCX file with a shorter filename.")
    if (
        "/" in filename or "\\" in filename or
        any(ord(char) < 32 or ord(char) == 127 for char in filename) or
        filename in {".", ".."} or filename.startswith(".")
    ):
        raise CVImportError("The CV filename is invalid.")
    if PurePath(filename).suffix.lower() not in {".pdf", ".docx"}:
        raise CVImportError("Only PDF and DOCX CV files are supported.")
    return filename


def _pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise CVImportError("Password-protected PDFs cannot be imported.")
        if len(reader.pages) > 30:
            raise CVImportError("Please upload a CV with 30 pages or fewer.")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except CVImportError:
        raise
    except Exception as exc:
        raise CVImportError("Unable to extract text from this PDF. Please export a text-based CV.") from exc
    return text


def _docx_text(content: bytes) -> str:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) > 300 or sum(info.file_size for info in archive.infolist()) > MAX_ZIP_EXPANDED_BYTES:
                raise CVImportError("The DOCX file exceeds safe document limits.")
            if (
                "[Content_Types].xml" not in names or
                "word/document.xml" not in names or
                any(name.lower().endswith("vbaproject.bin") for name in names)
            ):
                raise CVImportError("This file is not a supported DOCX document.")
            if archive.getinfo("word/document.xml").file_size > 5 * 1024 * 1024:
                raise CVImportError("The DOCX text section is too large.")
            document = archive.read("word/document.xml")
        if b"<!DOCTYPE" in document.upper() or b"<!ENTITY" in document.upper():
            raise CVImportError("Unsupported XML entity found in the DOCX.")
        root = ET.fromstring(document)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        lines = []
        for paragraph in root.iter(ns + "p"):
            line = "".join(element.text or "" for element in paragraph.iter(ns + "t"))
            if line.strip():
                lines.append(line)
        return "\n".join(lines)
    except CVImportError:
        raise
    except (BadZipFile, KeyError, ET.ParseError, ValueError, RuntimeError) as exc:
        raise CVImportError("Unable to read this DOCX document.") from exc


def parse_cv(filename: str, encoded: str) -> tuple[str, str, bytes, str]:
    safe_filename = _clean_filename(filename)
    if not isinstance(encoded, str) or len(encoded) > 7_000_000:
        raise CVImportError("The CV exceeds the 5 MB upload limit.")
    try:
        content = b64decode(encoded, validate=True)
    except (ValueError, Base64Error) as exc:
        raise CVImportError("The CV content is not valid base64.") from exc
    if not (20 <= len(content) <= MAX_CV_BYTES):
        raise CVImportError("The CV must be a nonempty PDF or DOCX smaller than 5 MB.")
    ext = PurePath(safe_filename).suffix.lower()
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise CVImportError("This file does not have a valid PDF signature.")
        text = _pdf_text(content)
        media_type = "application/pdf"
    else:
        if not content.startswith(bytes((0x50, 0x4B, 0x03, 0x04))):
            raise CVImportError("This file does not have a valid DOCX signature.")
        text = _docx_text(content)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    text = text.replace("\x00", "").strip()
    if len(text) < 20:
        raise CVImportError("No readable CV text was found. Upload a text-based PDF or DOCX.")
    if len(text) > MAX_CV_TEXT:
        text = text[:MAX_CV_TEXT]
    return safe_filename, media_type, content, text
