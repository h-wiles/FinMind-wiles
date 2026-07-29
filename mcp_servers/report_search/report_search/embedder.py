"""Sentence-transformer based embedding for Chinese financial text.

Uses BAAI/bge-small-zh-v1.5 by default — a lightweight (24 MB) bilingual
(Chinese/English) model with a 512-dimensional output, optimised for retrieval.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# BGE models benefit from a query instruction prefix for asymmetric retrieval
# (different encoding paths for queries vs passages). This is the recommended
# Chinese instruction from the BGE model card.
_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class Embedder:
    """Thin wrapper around sentence-transformers for the BGE model family.

    The model is loaded lazily on first use so import errors only surface
    when ``embed`` / ``embed_query`` is actually called.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self._model_name = model_name
        self._model: "SentenceTransformer | None" = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def dimension(self) -> int:
        """Embedding dimension (512 for bge-small-zh-v1.5)."""
        self._ensure_loaded()
        assert self._model is not None
        return self._model.get_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Encode a batch of passage texts.

        Args:
            texts: List of document chunks to embed.

        Returns:
            List of normalised embedding vectors (each a list of floats).
        """
        if not texts:
            return []
        self._ensure_loaded()
        assert self._model is not None
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Encode a single search query.

        Prepends the BGE query instruction for asymmetric retrieval quality.
        """
        self._ensure_loaded()
        assert self._model is not None
        embedding = self._model.encode(
            [_QUERY_INSTRUCTION + query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding[0].tolist()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        logger.info("Loading embedding model %s (first use) ...", self._model_name)
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self._model_name)
        dim = self._model.get_embedding_dimension()
        logger.info(
            "Embedding model loaded: %s (dim=%d)", self._model_name, dim
        )
