"""PDF indexing pipeline: scan directory, convert, chunk, embed, store."""

import logging
import os
import re
from pathlib import Path

from report_search.chunker import chunk_markdown
from report_search.config import Config
from report_search.converter import convert_pdf_to_markdown
from report_search.embedder import Embedder
from report_search.store import VectorStore

logger = logging.getLogger(__name__)

# Matches company identifier + 4-digit year in filenames like:
#   600519_2024_annual.pdf  → company="600519",  year=2024
#   HK.00700_2024.pdf       → company="HK.00700", year=2024
#   AAPL_2024_10K.pdf       → company="AAPL",     year=2024
#   贵州茅台_2024.pdf        → company="贵州茅台",  year=2024
_FILENAME_META = re.compile(
    r"^(.+?)[\-_](\d{4})[\-_]?.*\.pdf$", re.IGNORECASE
)


class Indexer:
    """Orchestrates the full PDF → searchable-index pipeline."""

    def __init__(self, config: Config, store: VectorStore, embedder: Embedder):
        self._config = config
        self._store = store
        self._embedder = embedder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan_and_index(self, directory: str | None = None, force: bool = False) -> dict:
        """Scan a directory for PDFs and index new or changed files.

        Args:
            directory: Override the configured PDF directory.
            force: If True, re-index all files regardless of modification time.

        Returns:
            Summary dict: {"new": int, "updated": int, "skipped": int, "errors": int, "total": int}
        """
        pdf_dir = Path(directory) if directory else self._config.pdf_dir

        if not pdf_dir.exists():
            logger.warning("PDF directory does not exist: %s", pdf_dir)
            return {"new": 0, "updated": 0, "skipped": 0, "errors": 0, "total": 0}

        pdf_files = sorted(pdf_dir.glob("*.pdf"))
        if not pdf_files:
            logger.warning("No PDF files found in %s", pdf_dir)
            return {"new": 0, "updated": 0, "skipped": 0, "errors": 0, "total": 0}

        indexed_mtimes = self._store.get_indexed_file_mtimes()
        summary = {"new": 0, "updated": 0, "skipped": 0, "errors": 0, "total": len(pdf_files)}

        for pdf_path in pdf_files:
            try:
                stats = pdf_path.stat()

                if not force:
                    prev_mtime = indexed_mtimes.get(str(pdf_path))
                    if prev_mtime is not None and prev_mtime == stats.st_mtime:
                        summary["skipped"] += 1
                        continue

                company_name, year = _extract_metadata(pdf_path)

                report_id = self._store.upsert_report(
                    pdf_path, stats, company_name=company_name, year=year
                )

                # If the file was unchanged (same mtime), skip processing
                if report_id is not None and not force:
                    prev_mtime = indexed_mtimes.get(str(pdf_path))
                    if prev_mtime == stats.st_mtime:
                        summary["skipped"] += 1
                        continue

                self._index_file(pdf_path, report_id, company_name, year)

                if str(pdf_path) in indexed_mtimes:
                    summary["updated"] += 1
                else:
                    summary["new"] += 1

            except Exception as exc:
                logger.error("Failed to index %s: %s", pdf_path.name, exc)
                summary["errors"] += 1

        logger.info(
            "Indexing complete: %d new, %d updated, %d skipped, %d errors (total: %d)",
            summary["new"],
            summary["updated"],
            summary["skipped"],
            summary["errors"],
            summary["total"],
        )
        return summary

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _index_file(
        self,
        pdf_path: Path,
        report_id: int,
        company_name: str | None,
        year: int | None,
    ) -> None:
        """Process a single PDF through the full pipeline."""
        # 1. Convert PDF → Markdown
        md_text = convert_pdf_to_markdown(pdf_path)

        # 2. Chunk
        chunks = chunk_markdown(
            md_text,
            max_chars=self._config.chunk_max_chars,
            overlap=self._config.chunk_overlap_chars,
        )
        if not chunks:
            logger.warning("No chunks produced for %s", pdf_path.name)
            return

        # 3. Embed all chunks in one batch
        texts = [c.text for c in chunks]
        embeddings = self._embedder.embed(texts)

        # 4. Store
        chunk_dicts = [
            {
                "chunk_index": i,
                "text": chunks[i].text,
                "section_title": chunks[i].section_title,
                "section_path": chunks[i].section_path,
                "embedding": embeddings[i],
            }
            for i in range(len(chunks))
        ]
        self._store.insert_chunks(report_id, chunk_dicts)

        logger.info(
            "Indexed %s → %d chunks (company=%s, year=%s)",
            pdf_path.name,
            len(chunks),
            company_name,
            year,
        )


def _extract_metadata(file_path: Path) -> tuple[str | None, int | None]:
    """Extract company name and year from a PDF filename.

    Supports patterns like:
        600519_2024_annual.pdf  → ("600519", 2024)
        HK.00700_2024.pdf       → ("HK.00700", 2024)
        贵州茅台_2024.pdf        → ("贵州茅台", 2024)
    """
    match = _FILENAME_META.match(file_path.name)
    if match is None:
        return None, None

    company = match.group(1).strip("_").strip("-")
    try:
        year = int(match.group(2))
    except (ValueError, TypeError):
        year = None

    # Sanity-check the year
    if year is not None and (year < 2000 or year > 2099):
        year = None

    return company or None, year
