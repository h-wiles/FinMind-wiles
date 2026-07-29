"""DuckDB-based persistent vector store for PDF report chunks."""

import logging
import os
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


class VectorStore:
    """DuckDB-backed vector store with persistent index.

    Stores report metadata and text chunks with their embedding vectors.
    Uses DuckDB's ARRAY type and array_cosine_similarity() for zero-dependency
    semantic search.
    """

    def __init__(self, db_path: Path, embedding_dim: int):
        self._db_path = db_path
        self._dim = embedding_dim
        self._conn = duckdb.connect(str(db_path))
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create tables if they don't already exist."""
        # DuckDB INTEGER PRIMARY KEY does not auto-increment; we use a
        # sequence + DEFAULT so INSERT can omit the id column.
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_reports_id;
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY DEFAULT nextval('seq_reports_id'),
                file_path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_mtime REAL,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                company_name TEXT,
                year INTEGER,
                num_chunks INTEGER DEFAULT 0,
                conversion_error TEXT
            )
        """)
        self._conn.execute(f"""
            CREATE SEQUENCE IF NOT EXISTS seq_chunks_id;
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY DEFAULT nextval('seq_chunks_id'),
                report_id INTEGER NOT NULL REFERENCES reports(id),
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                section_title TEXT,
                section_path TEXT,
                embedding FLOAT[{self._dim}],
                UNIQUE(report_id, chunk_index)
            )
        """)

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
        existing = self._conn.execute(
            "SELECT id, file_mtime FROM reports WHERE file_path = ?",
            [file_path_str],
        ).fetchone()

        if existing is not None:
            report_id, old_mtime = existing
            if old_mtime == stats.st_mtime:
                # File unchanged — skip
                logger.debug("Report %s unchanged, skipping", file_path.name)
                return report_id
            # File changed — delete old chunks and update
            logger.info("Report %s changed, re-indexing", file_path.name)
            self._conn.execute(
                "DELETE FROM chunks WHERE report_id = ?", [report_id]
            )
            self._conn.execute(
                """UPDATE reports SET
                    file_size = ?, file_mtime = ?, company_name = ?, year = ?,
                    num_chunks = 0, conversion_error = NULL,
                    indexed_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                [stats.st_size, stats.st_mtime, company_name, year, report_id],
            )
            return report_id

        # New report
        logger.info("Indexing new report: %s", file_path.name)
        result = self._conn.execute(
            """INSERT INTO reports
               (file_path, file_name, file_size, file_mtime, company_name, year)
               VALUES (?, ?, ?, ?, ?, ?)
               RETURNING id""",
            [
                file_path_str,
                file_path.name,
                stats.st_size,
                stats.st_mtime,
                company_name,
                year,
            ],
        ).fetchone()
        assert result is not None
        return result[0]

    def mark_conversion_error(self, report_id: int, error: str) -> None:
        """Record a conversion failure for a report."""
        self._conn.execute(
            "UPDATE reports SET conversion_error = ? WHERE id = ?",
            [error[:1000], report_id],
        )

    def get_indexed_file_mtimes(self) -> dict[str, float]:
        """Return {file_path: file_mtime} for all indexed reports."""
        rows = self._conn.execute(
            "SELECT file_path, file_mtime FROM reports WHERE conversion_error IS NULL"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------------
    # Chunk storage
    # ------------------------------------------------------------------

    def insert_chunks(
        self,
        report_id: int,
        chunks: list[dict],
    ) -> None:
        """Insert multiple chunks for a report.

        Each chunk dict must have:
            chunk_index, text, section_title, section_path, embedding (list[float])
        """
        for ch in chunks:
            self._conn.execute(
                f"""INSERT INTO chunks
                   (report_id, chunk_index, text, section_title, section_path, embedding)
                   VALUES (?, ?, ?, ?, ?, ?::FLOAT[{self._dim}])""",
                [
                    report_id,
                    ch["chunk_index"],
                    ch["text"],
                    ch.get("section_title"),
                    ch.get("section_path"),
                    ch["embedding"],
                ],
            )
        self._conn.execute(
            "UPDATE reports SET num_chunks = ? WHERE id = ?",
            [len(chunks), report_id],
        )

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

        Returns results sorted by cosine similarity (descending).
        """
        # Build dynamic WHERE clause for optional filters
        conditions: list[str] = []
        params: list = [query_embedding]

        if company_name is not None:
            conditions.append("r.company_name = ?")
            params.append(company_name)
        if year is not None:
            conditions.append("r.year = ?")
            params.append(year)

        where_clause = ""
        if conditions:
            where_clause = " AND " + " AND ".join(conditions)

        params.append(top_k)

        rows = self._conn.execute(
            f"""SELECT
                c.id,
                c.text,
                c.section_title,
                c.section_path,
                r.file_name,
                r.company_name,
                r.year,
                array_cosine_similarity(c.embedding, ?::FLOAT[{self._dim}]) AS similarity
            FROM chunks c
            JOIN reports r ON c.report_id = r.id
            WHERE r.conversion_error IS NULL{where_clause}
            ORDER BY similarity DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        return [
            {
                "chunk_id": row[0],
                "text": row[1],
                "section_title": row[2],
                "section_path": row[3],
                "file_name": row[4],
                "company_name": row[5],
                "year": row[6],
                "similarity": round(row[7], 4),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_reports(self) -> list[dict]:
        """Return metadata for all successfully indexed reports."""
        rows = self._conn.execute(
            """SELECT file_name, company_name, year, num_chunks, indexed_at
               FROM reports
               WHERE conversion_error IS NULL
               ORDER BY indexed_at DESC"""
        ).fetchall()
        return [
            {
                "file_name": row[0],
                "company_name": row[1],
                "year": row[2],
                "num_chunks": row[3],
                "indexed_at": str(row[4]) if row[4] else None,
            }
            for row in rows
        ]

    def get_report_count(self) -> int:
        """Return the number of indexed reports."""
        result = self._conn.execute(
            "SELECT COUNT(*) FROM reports WHERE conversion_error IS NULL"
        ).fetchone()
        return result[0] if result else 0

    def get_chunk_count(self) -> int:
        """Return the total number of indexed chunks."""
        result = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return result[0] if result else 0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
