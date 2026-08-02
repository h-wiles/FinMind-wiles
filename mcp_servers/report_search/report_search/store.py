"""FAISS-based vector store with JSON metadata.

FAISS handles the vector similarity search; a JSON file stores report
metadata and chunk text. The index is persisted to disk and reloaded on
startup.
"""

import json
import logging
import os
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore:
    """FAISS + JSON persistent vector store.

    FAISS IndexIDMap(IndexFlatIP) provides exact inner-product search
    (equivalent to cosine similarity with normalised vectors). Metadata
    (report info, chunk text) is stored in a companion JSON file.
    """

    def __init__(self, index_dir: Path, embedding_dim: int):
        self._dir = index_dir
        self._dim = embedding_dim
        self._index_path = index_dir / "faiss.index"
        self._meta_path = index_dir / "metadata.json"

        # FAISS index — lazy init
        self._index = None

        # In-memory metadata
        self._reports: dict[int, dict] = {}   # report_id → metadata
        self._chunks: list[dict] = []          # chunk_id → {report_id, text, ...}
        self._next_chunk_id: int = 0
        self._next_report_id: int = 1

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load FAISS index and metadata from disk."""
        if self._index_path.exists():
            import faiss
            self._index = faiss.read_index(str(self._index_path))
            logger.info("Loaded FAISS index: %d vectors", self._index.ntotal)
        else:
            import faiss
            base_index = faiss.IndexFlatIP(self._dim)
            self._index = faiss.IndexIDMap(base_index)
            logger.info("Created new FAISS IndexFlatIP (dim=%d)", self._dim)

        if self._meta_path.exists():
            with open(self._meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            self._reports = {int(k): v for k, v in meta.get("reports", {}).items()}
            self._chunks = meta.get("chunks", [])
            self._next_chunk_id = meta.get("next_chunk_id", 0)
            self._next_report_id = meta.get("next_report_id", 1)
            logger.info(
                "Loaded metadata: %d reports, %d chunks",
                len(self._reports), len(self._chunks),
            )
        else:
            self._save_meta()

        # Self-heal: if FAISS index is empty but metadata has chunks, it's
        # a broken state (e.g. crash partway through). Reset and re-index.
        if self._index.ntotal == 0 and (self._reports or self._chunks):
            logger.warning(
                "Inconsistent state: FAISS index empty but metadata has %d reports / %d chunks. "
                "Resetting to force re-index.",
                len(self._reports), len(self._chunks),
            )
            self._reports = {}
            self._chunks = []
            self._next_chunk_id = 0
            self._next_report_id = 1
            self._save_meta()

    def _save_meta(self) -> None:
        """Persist metadata to JSON."""
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "reports": {str(k): v for k, v in self._reports.items()},
                    "chunks": self._chunks,
                    "next_chunk_id": self._next_chunk_id,
                    "next_report_id": self._next_report_id,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _save_index(self) -> None:
        """Persist FAISS index to disk."""
        import faiss
        faiss.write_index(self._index, str(self._index_path))

    def close(self) -> None:
        """Save and release resources."""
        if self._index is not None:
            self._save_index()
        self._save_meta()
        logger.info("VectorStore closed: %d reports, %d chunks", len(self._reports), len(self._chunks))

    # ------------------------------------------------------------------
    # Report CRUD
    # ------------------------------------------------------------------

    def upsert_report(
        self,
        file_path: Path,
        stats: os.stat_result,
        company_name: str | None = None,
        year: int | None = None,
    ) -> int:
        """Insert or update a report row. Returns the report id."""
        file_path_str = str(file_path)

        # Check for existing report by file path
        for rid, rep in self._reports.items():
            if rep.get("file_path") == file_path_str:
                if rep.get("file_mtime") == stats.st_mtime:
                    logger.debug("Report %s unchanged, skipping", file_path.name)
                    return rid
                # File changed — remove old chunks
                logger.info("Report %s changed, re-indexing", file_path.name)
                self._remove_report_chunks(rid)
                rep["file_size"] = stats.st_size
                rep["file_mtime"] = stats.st_mtime
                rep["company_name"] = company_name
                rep["year"] = year
                rep["num_chunks"] = 0
                rep["conversion_error"] = None
                rep["indexed_at"] = time.time()
                self._save_meta()
                return rid

        # New report
        rid = self._next_report_id
        self._next_report_id += 1
        self._reports[rid] = {
            "file_path": file_path_str,
            "file_name": file_path.name,
            "file_size": stats.st_size,
            "file_mtime": stats.st_mtime,
            "company_name": company_name,
            "year": year,
            "num_chunks": 0,
            "conversion_error": None,
            "indexed_at": time.time(),
        }
        logger.info("New report: %s (id=%d)", file_path.name, rid)
        self._save_meta()
        return rid

    def mark_conversion_error(self, report_id: int, error: str) -> None:
        """Record a conversion failure for a report."""
        if report_id in self._reports:
            self._reports[report_id]["conversion_error"] = error[:1000]
            self._save_meta()

    def get_indexed_file_mtimes(self) -> dict[str, float]:
        """Return {file_path: file_mtime} for all indexed reports."""
        return {
            r["file_path"]: r["file_mtime"]
            for r in self._reports.values()
            if not r.get("conversion_error")
        }

    # ------------------------------------------------------------------
    # Chunk storage
    # ------------------------------------------------------------------

    def _remove_report_chunks(self, report_id: int) -> None:
        """Remove all chunks and FAISS vectors for a report."""
        # Collect chunk IDs to remove from FAISS
        ids_to_remove = [
            c["id"] for c in self._chunks if c["report_id"] == report_id
        ]
        if ids_to_remove and self._index.ntotal > 0:
            ids_array = np.array(ids_to_remove, dtype=np.int64)
            self._index.remove_ids(ids_array)
            self._save_index()
        # Remove from in-memory list
        self._chunks = [c for c in self._chunks if c["report_id"] != report_id]

    def insert_chunks(self, report_id: int, chunks: list[dict]) -> None:
        """Insert multiple chunks with embeddings into the store.

        Each chunk dict must have:
            chunk_index, text, section_title, section_path, embedding (list[float])
        """
        ids = []
        vectors = []
        for ch in chunks:
            chunk_id = self._next_chunk_id
            self._next_chunk_id += 1
            ids.append(chunk_id)

            vectors.append(ch["embedding"])
            self._chunks.append({
                "id": chunk_id,
                "report_id": report_id,
                "chunk_index": ch["chunk_index"],
                "text": ch["text"],
                "section_title": ch.get("section_title"),
                "section_path": ch.get("section_path"),
            })

        # Add to FAISS
        vec_array = np.array(vectors, dtype=np.float32)
        id_array = np.array(ids, dtype=np.int64)
        self._index.add_with_ids(vec_array, id_array)

        # Update report
        if report_id in self._reports:
            self._reports[report_id]["num_chunks"] = len(chunks)

        self._save_index()
        self._save_meta()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        company_name: str | None = None,
        year: int | None = None,
    ) -> list[dict]:
        """Semantic search with optional metadata filters.

        Searches FAISS for top-k * 3 candidates, then filters by metadata
        in-memory to ensure we return enough results after filtering.
        """
        if self._index.ntotal == 0:
            return []

        # Fetch extra candidates so filtering doesn't starve the result set
        k = min(top_k * 3, self._index.ntotal)
        q = np.array([query_embedding], dtype=np.float32)
        distances, indices = self._index.search(q, k)

        results = []
        chunk_by_id = {c["id"]: c for c in self._chunks}
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:  # FAISS sentinel for "no more results"
                continue
            chunk = chunk_by_id.get(int(idx))
            if chunk is None:
                continue

            # Metadata filter
            rid = chunk["report_id"]
            report = self._reports.get(rid)
            if report is None or report.get("conversion_error"):
                continue
            if company_name and (report.get("company_name") or "") != company_name:
                continue
            if year is not None and report.get("year") != year:
                continue

            results.append({
                "chunk_id": chunk["id"],
                "text": chunk["text"],
                "section_title": chunk.get("section_title"),
                "section_path": chunk.get("section_path"),
                "file_name": report.get("file_name", ""),
                "company_name": report.get("company_name"),
                "year": report.get("year"),
                "similarity": round(float(dist), 4),
            })

            if len(results) >= top_k:
                break

        return results

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_reports(self) -> list[dict]:
        """Return metadata for all successfully indexed reports."""
        return [
            {
                "file_name": r["file_name"],
                "company_name": r.get("company_name"),
                "year": r.get("year"),
                "num_chunks": r.get("num_chunks", 0),
                "indexed_at": r.get("indexed_at"),
            }
            for r in self._reports.values()
            if not r.get("conversion_error")
        ]

    def get_report_count(self) -> int:
        """Return the number of successfully indexed reports."""
        return sum(1 for r in self._reports.values() if not r.get("conversion_error"))

    def get_chunk_count(self) -> int:
        """Return the total number of indexed chunks."""
        return len(self._chunks)
