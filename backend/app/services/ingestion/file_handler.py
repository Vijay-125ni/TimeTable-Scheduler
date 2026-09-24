"""
file_handler.py — Phase 1: Upload Engine
Handles MIME validation, ZIP extraction, file queue, duplicate detection,
and secure storage to the uploads/ directory.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from loguru import logger

# ── Constants ─────────────────────────────────────────────────────────────────

UPLOADS_DIR = Path(__file__).resolve().parents[4] / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB per file
MAX_TOTAL_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB per batch
MAX_FILES_PER_BATCH = 50

# ZIP bomb protections
MAX_ZIP_EXTRACT_SIZE = 500 * 1024 * 1024  # 500 MB max uncompressed
MAX_ZIP_FILES = 1000

ALLOWED_EXTENSIONS: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".json": "application/json",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".zip": "application/zip",
}

# Magic bytes signatures for MIME validation (first bytes of file)
MAGIC_SIGNATURES: Dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/zip",  # ZIP / Office Open XML
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF8": "image/gif",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
    b"BM": "image/bmp",
}


# ── Data classes ───────────────────────────────────────────────────────────────


class QueuedFile:
    """Represents a validated, stored file ready for processing."""

    def __init__(
        self,
        file_id: str,
        original_name: str,
        stored_path: Path,
        size_bytes: int,
        extension: str,
        content_hash: str,
        mime_type: str,
        session_id: str,
    ):
        self.file_id = file_id
        self.original_name = original_name
        self.stored_path = stored_path
        self.size_bytes = size_bytes
        self.extension = extension
        self.content_hash = content_hash
        self.mime_type = mime_type
        self.session_id = session_id
        self.uploaded_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_id": self.file_id,
            "original_name": self.original_name,
            "stored_path": str(self.stored_path),
            "size_bytes": self.size_bytes,
            "extension": self.extension,
            "content_hash": self.content_hash,
            "mime_type": self.mime_type,
            "session_id": self.session_id,
            "uploaded_at": self.uploaded_at.isoformat(),
        }


# ── Helpers ────────────────────────────────────────────────────────────────────


def _compute_hash(content: bytes) -> str:
    """SHA-256 hash of file content for duplicate detection."""
    return hashlib.sha256(content).hexdigest()


def _detect_mime(content: bytes, filename: str) -> str:
    """Detect MIME type via magic bytes, falling back to extension."""
    for magic, mime in MAGIC_SIGNATURES.items():
        if content.startswith(magic):
            # Office Open XML: all are ZIP but differ by extension
            if mime == "application/zip":
                ext = Path(filename).suffix.lower()
                return ALLOWED_EXTENSIONS.get(ext, mime)
            return mime
    # Fallback: extension-based
    ext = Path(filename).suffix.lower()
    return ALLOWED_EXTENSIONS.get(ext, "application/octet-stream")


def _sanitize_filename(name: str) -> str:
    """Strip path traversal characters and unsafe chars from filename."""
    base = os.path.basename(name)
    base = re.sub(r"[^\w\.\-]", "_", base)
    return base[:200] or "unnamed_file"


def _store_file(content: bytes, session_id: str, safe_name: str) -> Path:
    """Write content to uploads/<session_id>/<uuid>_<safe_name>."""
    session_dir = UPLOADS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest = session_dir / unique_name
    dest.write_bytes(content)
    return dest


def _extract_zip(
    zip_content: bytes,
    session_id: str,
    seen_hashes: set,
    current_depth: int = 0,
    stats: Optional[Dict[str, int]] = None,
) -> List[Tuple[str, bytes]]:
    """
    Recursively extract supported files from a ZIP archive.
    Returns list of (original_name, content) tuples.
    Skips duplicates by content hash and unsupported extensions.
    Enforces ZIP bomb protections (size and file counts).
    """
    if stats is None:
        stats = {"total_files": 0, "total_size": 0}

    if current_depth > 5:
        logger.warning("ZIP extraction depth limit reached.")
        return []

    extracted: List[Tuple[str, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if stats["total_files"] >= MAX_ZIP_FILES:
                    logger.warning(
                        f"ZIP bomb prevention: file limit ({MAX_ZIP_FILES}) reached."
                    )
                    break

                stats["total_files"] += 1

                ext = Path(info.filename).suffix.lower()
                if ext == ".zip":
                    # Nested ZIP
                    nested_content = zf.read(info.filename)
                    nested = _extract_zip(
                        nested_content,
                        session_id,
                        seen_hashes,
                        current_depth + 1,
                        stats,
                    )
                    extracted.extend(nested)
                    continue
                if ext not in ALLOWED_EXTENSIONS:
                    continue

                if stats["total_size"] + info.file_size > MAX_ZIP_EXTRACT_SIZE:
                    logger.warning(
                        f"ZIP bomb prevention: size limit ({MAX_ZIP_EXTRACT_SIZE}B) reached."
                    )
                    break

                stats["total_size"] += info.file_size
                content = zf.read(info.filename)
                h = _compute_hash(content)
                if h in seen_hashes:
                    logger.debug(f"ZIP: skipping duplicate {info.filename}")
                    continue
                seen_hashes.add(h)
                extracted.append((info.filename, content))
    except zipfile.BadZipFile as exc:
        logger.warning(f"Invalid ZIP file: {exc}")
    return extracted


# ── Public API ─────────────────────────────────────────────────────────────────


async def process_uploaded_files(
    files: List[UploadFile],
    session_id: Optional[str] = None,
) -> Tuple[str, List[QueuedFile], List[Dict[str, str]]]:
    """
    Phase 1 entry point.
    Validates, deduplicates, extracts ZIPs, and stores all uploaded files.

    Returns:
        session_id: str — upload session identifier
        queued: List[QueuedFile] — validated files ready for parsing
        errors: List[dict] — per-file error messages
    """
    if not session_id:
        session_id = (
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + "_"
            + uuid.uuid4().hex[:8]
        )

    queued: List[QueuedFile] = []
    errors: List[Dict[str, str]] = []
    seen_hashes: set = set()
    total_size = 0

    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum {MAX_FILES_PER_BATCH} files per upload.",
        )

    # Flatten: read all upload files (may include ZIPs to expand)
    raw_files: List[Tuple[str, bytes]] = []
    for uf in files:
        content = await uf.read()
        raw_files.append((uf.filename or "unnamed", content))

    # Expand ZIPs first
    expanded: List[Tuple[str, bytes]] = []
    for name, content in raw_files:
        ext = Path(name).suffix.lower()
        if ext == ".zip":
            extracted = _extract_zip(content, session_id, seen_hashes)
            if not extracted:
                errors.append(
                    {
                        "file": name,
                        "error": "ZIP archive is empty or contains no supported files.",
                    }
                )
            expanded.extend(extracted)
        else:
            expanded.append((name, content))

    # Process each file
    for name, content in expanded:
        safe_name = _sanitize_filename(name)
        ext = Path(safe_name).suffix.lower()

        # Extension check
        if ext not in ALLOWED_EXTENSIONS:
            errors.append({"file": name, "error": f"Unsupported file type: {ext}"})
            continue

        # Size check
        if len(content) > MAX_FILE_SIZE_BYTES:
            errors.append(
                {
                    "file": name,
                    "error": f"File too large: {len(content) // (1024*1024)}MB. Max is {MAX_FILE_SIZE_BYTES // (1024*1024)}MB.",
                }
            )
            continue

        total_size += len(content)
        if total_size > MAX_TOTAL_SIZE_BYTES:
            errors.append(
                {
                    "file": name,
                    "error": "Total upload size exceeds 500MB limit. Remaining files skipped.",
                }
            )
            break

        # Content hash duplicate detection
        content_hash = _compute_hash(content)
        if content_hash in seen_hashes:
            logger.debug(f"Skipping duplicate file: {name}")
            continue
        seen_hashes.add(content_hash)

        # MIME validation
        detected_mime = _detect_mime(content, safe_name)
        ALLOWED_EXTENSIONS.get(ext, "")
        # Allow Office Open XML files (they are all ZIP internally)
        if detected_mime == "application/octet-stream":
            errors.append(
                {"file": name, "error": "File content does not match its extension."}
            )
            continue

        # Store file
        try:
            stored_path = _store_file(content, session_id, safe_name)
        except OSError as exc:
            errors.append({"file": name, "error": f"Storage error: {exc}"})
            continue

        file_id = uuid.uuid4().hex
        queued.append(
            QueuedFile(
                file_id=file_id,
                original_name=name,
                stored_path=stored_path,
                size_bytes=len(content),
                extension=ext,
                content_hash=content_hash,
                mime_type=detected_mime,
                session_id=session_id,
            )
        )

        logger.info(f"Queued file: {name} ({len(content)} bytes) → {stored_path.name}")

    return session_id, queued, errors
