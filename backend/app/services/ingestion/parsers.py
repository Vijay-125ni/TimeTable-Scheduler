"""
parsers.py — Phase 2 & 5: Document Parsing + Cross-Page Intelligence

Detects document type, extracts text, tables, forms, images, and metadata.
Runs OCR only if document is scanned (no selectable text).
Merges information spread across multiple pages before returning.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ── Extracted document result ──────────────────────────────────────────────────


class ParsedDocument:
    """Holds all extracted content from a single file."""

    def __init__(self, file_id: str, original_name: str, extension: str):
        self.file_id = file_id
        self.original_name = original_name
        self.extension = extension
        self.full_text: str = ""
        self.tables: List[List[List[str]]] = (
            []
        )  # list of tables; each table = list of rows
        self.metadata: Dict[str, Any] = {}
        self.page_count: int = 0
        self.is_scanned: bool = False
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "original_name": self.original_name,
            "extension": self.extension,
            "full_text": self.full_text[:5000],  # truncated for API response
            "full_text_length": len(self.full_text),
            "table_count": len(self.tables),
            "page_count": self.page_count,
            "is_scanned": self.is_scanned,
            "metadata": self.metadata,
            "error": self.error,
        }


# ── Per-format parsers ─────────────────────────────────────────────────────────


def _parse_pdf(path: Path, doc: ParsedDocument) -> None:
    """
    Extract text and tables from PDF using PyMuPDF (primary) + pdfplumber (tables).
    Falls back to OCR if no selectable text is found.
    """
    try:
        import fitz  # PyMuPDF

        pdf = fitz.open(str(path))
        doc.page_count = len(pdf)
        pages_text: List[str] = []

        for page in pdf:
            text = page.get_text("text")
            pages_text.append(text)

        combined = "\n".join(pages_text)
        # Heuristic: if extracted text is < 50 chars per page, treat as scanned
        avg_chars = len(combined) / max(doc.page_count, 1)
        doc.is_scanned = avg_chars < 50
        doc.full_text = combined
        pdf.close()
    except ImportError:
        logger.warning("PyMuPDF not available, using pypdf fallback")
        _parse_pdf_pypdf(path, doc)
    except Exception as exc:
        logger.warning(f"PyMuPDF failed for {path.name}: {exc}")
        _parse_pdf_pypdf(path, doc)

    # Extract tables with pdfplumber
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf_pl:
            for page in pdf_pl.pages:
                tables = page.extract_tables()
                for table in tables or []:
                    if table:
                        cleaned = [
                            [str(cell or "").strip() for cell in row] for row in table
                        ]
                        doc.tables.append(cleaned)
    except Exception as exc:
        logger.debug(f"pdfplumber table extraction failed for {path.name}: {exc}")

    # OCR if scanned
    if doc.is_scanned:
        from .ocr_engine import run_ocr

        ocr_text = run_ocr(path)
        if ocr_text.strip():
            doc.full_text = ocr_text
            doc.is_scanned = True


def _parse_pdf_pypdf(path: Path, doc: ParsedDocument) -> None:
    """Fallback PDF parser using pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        doc.page_count = len(reader.pages)
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        doc.full_text = "\n".join(texts)
        avg = len(doc.full_text) / max(doc.page_count, 1)
        doc.is_scanned = avg < 50
    except Exception as exc:
        doc.error = f"PDF parse error: {exc}"
        logger.error(f"pypdf failed for {path.name}: {exc}")


def _parse_docx(path: Path, doc: ParsedDocument) -> None:
    try:
        from docx import Document

        document = Document(str(path))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        doc.full_text = "\n".join(paragraphs)
        doc.page_count = 1  # DOCX doesn't have explicit pages

        for table in document.tables:
            tbl: List[List[str]] = []
            for row in table.rows:
                tbl.append([cell.text.strip() for cell in row.cells])
            if tbl:
                doc.tables.append(tbl)
    except Exception as exc:
        doc.error = f"DOCX parse error: {exc}"
        logger.error(f"docx parse failed for {path.name}: {exc}")


def _parse_doc(path: Path, doc: ParsedDocument) -> None:
    """Legacy .doc — try python-docx then fallback to reading as binary text."""
    try:
        _parse_docx(path, doc)
    except Exception:
        try:
            content = path.read_bytes()
            # Very basic: extract readable ASCII strings
            text = re.sub(rb"[^\x20-\x7E\n\t]", b" ", content).decode(
                "ascii", errors="ignore"
            )
            doc.full_text = text
        except Exception as exc:
            doc.error = f"DOC parse error: {exc}"


def _parse_xlsx(path: Path, doc: ParsedDocument) -> None:
    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        all_text: List[str] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            tbl: List[List[str]] = []
            for row in ws.iter_rows(values_only=True):
                row_vals = [str(v).strip() if v is not None else "" for v in row]
                if any(row_vals):
                    tbl.append(row_vals)
                    all_text.append("\t".join(row_vals))
            if tbl:
                doc.tables.append(tbl)
        doc.full_text = "\n".join(all_text)
        doc.page_count = len(wb.sheetnames)
    except Exception as exc:
        doc.error = f"XLSX parse error: {exc}"
        logger.error(f"xlsx parse failed: {exc}")


def _parse_xls(path: Path, doc: ParsedDocument) -> None:
    """Legacy .xls using openpyxl (reads xlrd format via compatibility)."""
    try:
        import pandas as pd

        dfs = pd.read_excel(str(path), sheet_name=None)
        all_text: List[str] = []
        for sheet_name, df in dfs.items():
            rows = df.fillna("").astype(str).values.tolist()
            doc.tables.append(rows)
            for row in rows:
                all_text.append("\t".join(row))
        doc.full_text = "\n".join(all_text)
        doc.page_count = len(dfs)
    except Exception as exc:
        doc.error = f"XLS parse error: {exc}"


def _parse_csv(path: Path, doc: ParsedDocument) -> None:
    try:
        for encoding in ("utf-8-sig", "utf-8", "cp1252"):
            try:
                content = path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            content = path.read_bytes().decode("ascii", errors="ignore")

        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        doc.tables.append(rows)
        doc.full_text = "\n".join([",".join(r) for r in rows])
        doc.page_count = 1
    except Exception as exc:
        doc.error = f"CSV parse error: {exc}"


def _parse_txt(path: Path, doc: ParsedDocument) -> None:
    try:
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                doc.full_text = path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        doc.page_count = 1
    except Exception as exc:
        doc.error = f"TXT parse error: {exc}"


def _parse_html(path: Path, doc: ParsedDocument) -> None:
    try:
        from bs4 import BeautifulSoup

        content = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(content, "lxml")
        # Extract tables
        for table_tag in soup.find_all("table"):
            tbl: List[List[str]] = []
            for tr in table_tag.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    tbl.append(cells)
            if tbl:
                doc.tables.append(tbl)
        doc.full_text = soup.get_text(separator="\n", strip=True)
        doc.page_count = 1
    except Exception as exc:
        doc.error = f"HTML parse error: {exc}"


def _parse_json(path: Path, doc: ParsedDocument) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        doc.full_text = json.dumps(data, indent=2)
        doc.metadata["json_structure"] = type(data).__name__
        doc.page_count = 1
    except Exception as exc:
        doc.error = f"JSON parse error: {exc}"


def _parse_xml(path: Path, doc: ParsedDocument) -> None:
    try:
        from bs4 import BeautifulSoup

        content = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(content, "xml")
        doc.full_text = soup.get_text(separator="\n", strip=True)
        doc.page_count = 1
    except Exception as exc:
        try:
            doc.full_text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            doc.error = f"XML parse error: {exc}"


def _parse_pptx(path: Path, doc: ParsedDocument) -> None:
    try:
        from pptx import Presentation

        prs = Presentation(str(path))
        slides_text: List[str] = []
        for slide in prs.slides:
            slide_parts: List[str] = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            slide_parts.append(text)
                if shape.has_table:
                    tbl: List[List[str]] = []
                    for row in shape.table.rows:
                        tbl.append([cell.text.strip() for cell in row.cells])
                    doc.tables.append(tbl)
            slides_text.append("\n".join(slide_parts))
        doc.full_text = "\n\n".join(slides_text)
        doc.page_count = len(prs.slides)
    except Exception as exc:
        doc.error = f"PPTX parse error: {exc}"


def _parse_image(path: Path, doc: ParsedDocument) -> None:
    """Images always go through OCR."""
    doc.is_scanned = True
    doc.page_count = 1
    from .ocr_engine import run_ocr

    ocr_text = run_ocr(path)
    doc.full_text = ocr_text


# ── Dispatch table ─────────────────────────────────────────────────────────────

_PARSER_MAP = {
    ".pdf": _parse_pdf,
    ".doc": _parse_doc,
    ".docx": _parse_docx,
    ".xlsx": _parse_xlsx,
    ".xls": _parse_xls,
    ".csv": _parse_csv,
    ".txt": _parse_txt,
    ".html": _parse_html,
    ".htm": _parse_html,
    ".json": _parse_json,
    ".xml": _parse_xml,
    ".ppt": _parse_pptx,
    ".pptx": _parse_pptx,
    ".png": _parse_image,
    ".jpg": _parse_image,
    ".jpeg": _parse_image,
    ".tiff": _parse_image,
    ".tif": _parse_image,
    ".bmp": _parse_image,
}


# ── Public API ─────────────────────────────────────────────────────────────────


def parse_document(
    file_id: str, original_name: str, stored_path: str, extension: str
) -> ParsedDocument:
    """
    Parse a single document.
    Returns a ParsedDocument with full_text, tables, metadata.
    """
    doc = ParsedDocument(
        file_id=file_id, original_name=original_name, extension=extension
    )
    path = Path(stored_path)

    if not path.exists():
        doc.error = f"File not found: {stored_path}"
        return doc

    parser_fn = _PARSER_MAP.get(extension.lower())
    if not parser_fn:
        doc.error = f"No parser for extension: {extension}"
        return doc

    try:
        parser_fn(path, doc)
        # Phase 5: Cross-page intelligence — de-duplicate table rows across pages
        doc.tables = _deduplicate_tables(doc.tables)
        logger.info(
            f"Parsed {original_name}: {len(doc.full_text)} chars, "
            f"{len(doc.tables)} tables, {doc.page_count} pages, scanned={doc.is_scanned}"
        )
    except Exception as exc:
        doc.error = f"Unexpected parser error: {exc}"
        logger.exception(f"Parser crashed for {original_name}")

    return doc


def _deduplicate_tables(tables: List[List[List[str]]]) -> List[List[List[str]]]:
    """
    Phase 5: Remove duplicate table rows that appear in repeated headers
    across pages. Uses a fingerprint set per table.
    """
    result: List[List[List[str]]] = []
    for table in tables:
        seen: set = set()
        clean: List[List[str]] = []
        for row in table:
            fp = "|".join(row)
            if fp not in seen:
                seen.add(fp)
                clean.append(row)
        if clean:
            result.append(clean)
    return result
