"""Configuration for the report-search MCP server.

All settings are read from environment variables with sensible defaults.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Immutable configuration resolved from environment variables."""

    pdf_dir: Path
    index_dir: Path          # Directory for FAISS index + JSON metadata
    model_name: str
    chunk_max_chars: int = 1500
    chunk_overlap_chars: int = 200
    embedding_dim: int = 512  # bge-small-zh-v1.5


def get_config() -> Config:
    """Resolve configuration from environment variables.

    Environment variables:
        REPORT_SEARCH_DIR   — path to the directory containing PDF financial reports
        REPORT_SEARCH_INDEX — path to the index directory (default: ~/.report_search/)
        REPORT_SEARCH_MODEL — HuggingFace model name (default: BAAI/bge-small-zh-v1.5)
    """
    pdf_dir = Path(
        os.environ.get(
            "REPORT_SEARCH_DIR",
            os.path.expanduser("~/projects/FinMind-wiles/data/reports"),
        )
    )
    index_dir = Path(
        os.environ.get(
            "REPORT_SEARCH_INDEX",
            os.path.expanduser("~/.report_search"),
        )
    )
    index_dir.mkdir(parents=True, exist_ok=True)

    model_name = os.environ.get(
        "REPORT_SEARCH_MODEL", "BAAI/bge-small-zh-v1.5"
    )

    config = Config(
        pdf_dir=pdf_dir,
        index_dir=index_dir,
        model_name=model_name,
    )
    logger.info("Config loaded: pdf_dir=%s, index_dir=%s", config.pdf_dir, config.index_dir)
    return config
