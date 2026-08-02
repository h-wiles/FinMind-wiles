"""Local PDF report semantic search — FAISS + JSON, same data as MCP server."""
import json
import logging
import os
from pathlib import Path

import numpy as np
from langchain.tools import tool

logger = logging.getLogger(__name__)

_INDEX_DIR = os.path.expanduser("~/.report_search")
_EMBEDDER = None
_INDEX = None
_META = None


def _load():
    global _INDEX, _META
    if _INDEX is not None:
        return
    import faiss
    idx_path = Path(_INDEX_DIR) / "faiss.index"
    meta_path = Path(_INDEX_DIR) / "metadata.json"
    if idx_path.exists():
        _INDEX = faiss.read_index(str(idx_path))
        with open(meta_path, encoding="utf-8") as f:
            _META = json.load(f)


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER
    from sentence_transformers import SentenceTransformer
    _EMBEDDER = SentenceTransformer("BAAI/bge-small-zh-v1.5", local_files_only=True)
    return _EMBEDDER


@tool("search_local_reports", parse_docstring=True)
def search_local_reports_tool(query: str, company_name: str = "", year: int = 0, max_results: int = 5) -> str:
    """在本地 PDF 财报库中进行语义搜索。每次用户提到公司年报/财报时优先使用。

    Args:
        query: 搜索关键词（如 "分红策略"、"风险因素"）
        company_name: 可选，公司名称或代码
        year: 可选，报告年份
        max_results: 最大结果数（默认 5）
    """
    try:
        _load()
        if _INDEX is None or _META is None:
            return json.dumps({"error": "索引不存在。请先将 PDF 放入 data/reports/ 目录"}, ensure_ascii=False)

        reports = {int(k): v for k, v in _META.get("reports", {}).items()}
        chunks = _META.get("chunks", [])
        if not chunks:
            return json.dumps({"error": "索引为空"}, ensure_ascii=False)

        embedder = _get_embedder()
        q = np.array([embedder.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]], dtype=np.float32)

        k = min(max_results * 3, _INDEX.ntotal)
        distances, indices = _INDEX.search(q, k)

        chunk_by_id = {c["id"]: c for c in chunks}
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            c = chunk_by_id.get(int(idx))
            if c is None:
                continue
            r = reports.get(c["report_id"])
            if r is None or r.get("conversion_error"):
                continue
            if company_name and (r.get("company_name") or "") != company_name:
                continue
            if year and r.get("year") != year:
                continue
            results.append(dict(file=r.get("file_name", ""), company=r.get("company_name"),
                                year=r.get("year"), section=c.get("section_path") or c.get("section_title") or "",
                                similarity=round(float(dist), 4), text=c["text"][:1500]))
            if len(results) >= max_results:
                break

        if not results:
            return json.dumps({"results": [], "message": f"未找到与'{query}'相关的内容"}, ensure_ascii=False)
        return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("search_local_reports failed")
        return json.dumps({"error": str(e)}, ensure_ascii=False)
