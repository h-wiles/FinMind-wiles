"""Configuration for the report-search MCP server.

All settings are read from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Immutable configuration resolved from environment variables."""

    pdf_dir: Path
    db_path: Path
    model_name: str
    chunk_max_chars: int = 1500
    chunk_overlap_chars: int = 200
    embedding_dim: int = 512  # bge-small-zh-v1.5


def get_config() -> Config:
    """Resolve configuration from environment variables.

    Environment variables:
        REPORT_SEARCH_DIR  — path to the directory containing PDF financial reports
        REPORT_SEARCH_DB   — path to the DuckDB index file (default: ~/.report_search/index.db)
        REPORT_SEARCH_MODEL — HuggingFace model name (default: BAAI/bge-small-zh-v1.5)
    """
    pdf_dir = Path(
        os.environ.get(
            "REPORT_SEARCH_DIR",
            os.path.expanduser("~/financial_reports"),
        )
    )
    db_path = Path(
        os.environ.get(
            "REPORT_SEARCH_DB",
            os.path.expanduser("~/.report_search/index.db"),
        )
    )
    db_path.parent.mkdir(parents=True, exist_ok=True)

    model_name = os.environ.get(
        "REPORT_SEARCH_MODEL", "BAAI/bge-small-zh-v1.5"
    )

    return Config(
        pdf_dir=pdf_dir,
        db_path=db_path,
        model_name=model_name,
    )
