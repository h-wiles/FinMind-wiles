"""PDF → Markdown conversion with two-converter fallback strategy.

Mirrors the proven approach from deerflow/utils/file_conversion.py:
pymupdf4llm first (better heading detection for Chinese reports),
markitdown as fallback (broader format support).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum character count to consider a conversion successful.
# Image-based / scanned PDFs produce near-empty output.
_MIN_QUALITY_CHARS = 200


def convert_pdf_to_markdown(file_path: Path) -> str:
    """Convert a single PDF file to Markdown.

    Strategy:
        1. Try pymupdf4llm (if installed) — best heading/outline extraction.
        2. Fall back to markitdown — handles more edge cases.

    Returns:
        The converted Markdown text.

    Raises:
        ValueError: If both converters fail or produce near-empty output.
    """
    # ---- pymupdf4llm (optional extra) -----------------------------------
    try:
        import pymupdf4llm

        text = pymupdf4llm.to_markdown(str(file_path))
        if len(text.strip()) >= _MIN_QUALITY_CHARS:
            logger.debug("Converted %s with pymupdf4llm (%d chars)", file_path.name, len(text))
            return text
        logger.debug(
            "pymupdf4llm output too short for %s (%d chars), trying markitdown",
            file_path.name,
            len(text),
        )
    except Exception:
        logger.debug("pymupdf4llm failed for %s, falling back to markitdown", file_path.name)

    # ---- markitdown (always available) ----------------------------------
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(file_path))
        text = result.text_content
        if len(text.strip()) >= _MIN_QUALITY_CHARS:
            logger.debug("Converted %s with markitdown (%d chars)", file_path.name, len(text))
            return text
    except Exception as exc:
        raise ValueError(
            f"markitdown failed for {file_path.name}: {exc}"
        ) from exc

    raise ValueError(
        f"Both converters produced insufficient text for {file_path.name} "
        f"(may be a scanned/image-based PDF)"
    )
