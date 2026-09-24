"""
ocr_engine.py — OCR subsystem
Primary: PaddleOCR
Fallback: Tesseract OCR (pytesseract, already in requirements)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

_paddle_ocr = None  # lazy-loaded singleton


def _get_paddle() -> Optional[object]:
    global _paddle_ocr
    if _paddle_ocr is not None:
        return _paddle_ocr
    try:
        from paddleocr import PaddleOCR

        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        logger.info("PaddleOCR initialized successfully")
        return _paddle_ocr
    except Exception as exc:
        logger.warning(f"PaddleOCR unavailable: {exc}. Falling back to Tesseract.")
        return None


def _ocr_with_paddle(path: Path) -> str:
    ocr = _get_paddle()
    if not ocr:
        return ""
    try:
        result = ocr.ocr(str(path), cls=True)
        lines = []
        for page_result in result or []:
            if page_result:
                for line in page_result:
                    if line and len(line) >= 2:
                        text_info = line[1]
                        if isinstance(text_info, (list, tuple)) and text_info:
                            lines.append(str(text_info[0]))
                        elif isinstance(text_info, str):
                            lines.append(text_info)
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"PaddleOCR inference failed: {exc}")
        return ""


def _ocr_with_tesseract(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image

        ext = path.suffix.lower()
        if ext == ".pdf":
            try:
                from pdf2image import convert_from_path

                images = convert_from_path(
                    str(path), dpi=200, first_page=1, last_page=6
                )
                texts = [pytesseract.image_to_string(img, lang="eng") for img in images]
                return "\n".join(texts)
            except Exception as exc:
                logger.warning(f"pdf2image failed: {exc}")
                return ""
        else:
            img = Image.open(str(path))
            return pytesseract.image_to_string(img, lang="eng")
    except ImportError:
        logger.warning("pytesseract not installed. OCR unavailable.")
        return ""
    except Exception as exc:
        logger.warning(f"Tesseract OCR failed: {exc}")
        return ""


def run_ocr(path: Path) -> str:
    """
    Run OCR on an image or scanned PDF.
    Tries PaddleOCR first, falls back to Tesseract.
    """
    logger.info(f"Running OCR on: {path.name}")

    # Try Paddle first
    text = _ocr_with_paddle(path)
    if text.strip():
        logger.info(f"PaddleOCR extracted {len(text)} chars from {path.name}")
        return text

    # Tesseract fallback
    text = _ocr_with_tesseract(path)
    if text.strip():
        logger.info(f"Tesseract extracted {len(text)} chars from {path.name}")
    else:
        logger.warning(f"OCR produced no output for {path.name}")
    return text
