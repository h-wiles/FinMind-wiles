"""Smoke tests for report-search MCP server components.

Run with: uv run python test_smoke.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from subprocess import PIPE, Popen


# ---------------------------------------------------------------------------
# Unit tests (no MCP protocol needed)
# ---------------------------------------------------------------------------

def test_chunker():
    from report_search.chunker import chunk_markdown

    md = """# Test Report

## 经营情况

2024年营收1500亿元，同比增长12%。

## 风险因素

### 行业竞争

行业竞争加剧，部分品牌对公司构成挑战。

### 政策风险

税收政策调整可能影响盈利。
"""
    chunks = chunk_markdown(md, max_chars=500)
    assert len(chunks) >= 3, f"expected >=3 chunks, got {len(chunks)}"
    sections = {c.section_path for c in chunks}
    assert any("风险因素" in s for s in sections), sections
    print("  ✓ chunker")


def test_store():
    import shutil
    from report_search.store import VectorStore

    index_dir = Path(tempfile.mkdtemp())
    try:
        store = VectorStore(index_dir, embedding_dim=3)

        stats = os.stat(__file__)

        # Insert — use 3-dim normalized vectors for FAISS IP
        import math
        v1 = [1.0, 0.0, 0.0]   # normalized: ||v1|| = 1
        v2 = [0.0, 1.0, 0.0]   # orthogonal to v1
        v3 = [0.707, 0.707, 0.0]  # ~45 degrees from v1

        rid = store.upsert_report(Path("test.pdf"), stats, "600519", 2024)
        assert rid == 1
        store.insert_chunks(rid, [
            {"chunk_index": 0, "text": "营收1500亿", "section_title": "经营", "section_path": "经营", "embedding": v1},
            {"chunk_index": 1, "text": "行业分析", "section_title": "行业", "section_path": "行业", "embedding": v2},
        ])

        # Search: query v3 should match v3 more (cosine similarity higher)
        results = store.search(v3, top_k=2)
        assert len(results) == 2
        assert results[0]["text"] == "行业分析"   # v3 closer to v2

        # Filter by year
        assert len(store.search(v1, year=2023)) == 0
        assert len(store.search(v1, year=2024)) == 2

        # List
        reports = store.list_reports()
        assert len(reports) == 1

        # Idempotent re-upsert
        assert store.upsert_report(Path("test.pdf"), stats, "600519", 2024) == rid

        print("  ✓ store")
    finally:
        store.close()
        shutil.rmtree(index_dir)


def test_embedder():
    from report_search.embedder import Embedder

    e = Embedder("BAAI/bge-small-zh-v1.5")
    assert e.dimension == 512

    emb = e.embed_query("测试查询")
    assert len(emb) == 512

    batch = e.embed(["文本1", "文本2"])
    assert len(batch) == 2
    assert len(batch[0]) == 512

    print("  ✓ embedder")


# ---------------------------------------------------------------------------
# Real data search tests
# ---------------------------------------------------------------------------

def test_search_social_responsibility():
    """Search the real indexed PDF for 社会责任 (social responsibility) content."""

    index_dir = Path(os.path.expanduser("~/.report_search"))
    if not (index_dir / "faiss.index").exists():
        print("  ⏭ 跳过: FAISS 索引不存在（需要先用 MCP Server 索引 PDF）")
        return

    from report_search.embedder import Embedder
    from report_search.store import VectorStore

    store = VectorStore(index_dir, embedding_dim=512)

    count = store.get_report_count()
    assert count > 0, f"索引为空: {index_dir}"
    print(f"  索引中有 {count} 份报告, {store.get_chunk_count()} 个片段")

    # ---- 语义搜索 (FAISS) ----
    embedder = Embedder("BAAI/bge-small-zh-v1.5")
    results = store.search(
        embedder.embed_query("社会责任"),
        top_k=5,
        company_name="贵州茅台",
        year=2025,
    )
    assert len(results) > 0, "语义搜索未找到'社会责任'相关内容"

    print(f"  语义搜索: {len(results)} 条结果")
    for i, r in enumerate(results[:3], 1):
        print(f"    [{i}] sim={r['similarity']:.3f} | {r.get('section_title','-')} | {r['text'][:60]}...")

    # ---- 关键词搜索 (遍历 chunks) ----
    keyword_hits = [
        c for c in store._chunks
        if "社会责任" in c["text"]
        and any(
            r.get("company_name") == "贵州茅台" and r.get("year") == 2025
            for r in [store._reports.get(c["report_id"], {})]
        )
    ][:5]
    assert len(keyword_hits) > 0, "关键词搜索'社会责任'无匹配"
    print(f"  关键词搜索: {len(keyword_hits)} 条匹配")
    for i, c in enumerate(keyword_hits[:3], 1):
        text = c["text"]
        idx = text.find("社会责任")
        start = max(0, idx - 30)
        end = min(len(text), idx + 80)
        snippet = text[start:end].replace("\n", " ")
        print(f"    [{i}] | {c.get('section_title','-')} | ...{snippet}...")

    store.close()
    print("  ✓ search_social_responsibility")


# ---------------------------------------------------------------------------
# MCP protocol integration test
# ---------------------------------------------------------------------------

def test_mcp_protocol():
    """Start the server via subprocess and exercise the JSON-RPC protocol."""

    env = {
        **os.environ,
        "REPORT_SEARCH_DIR": tempfile.mkdtemp(),
        "REPORT_SEARCH_DB": tempfile.mktemp(suffix=".db"),
    }

    proc = Popen(
        [sys.executable, "-m", "report_search"],
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
        env=env,
        text=False,
    )

    try:
        # 1. Initialize
        _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "test", "version": "1.0"}}})
        _rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 2. List tools
        result = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tool_names = [t["name"] for t in result.get("tools", [])]
        assert set(tool_names) == {"search_reports", "list_indexed_reports", "index_reports"}, tool_names
        print("  ✓ MCP tools/list")

        # 3. Call list_indexed_reports (empty index)
        result = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "list_indexed_reports", "arguments": {}}})
        text = result["content"][0]["text"]
        assert "索引为空" in text
        print("  ✓ MCP tools/call")

        print("  ✓ MCP protocol")
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _rpc(proc, msg: dict) -> dict:
    """Send a JSON-RPC message and read the response (if id is present)."""
    payload = (json.dumps(msg) + "\n").encode()
    proc.stdin.write(payload)  # type: ignore[union-attr]
    proc.stdin.flush()  # type: ignore[union-attr]

    if msg.get("method") == "notifications/initialized":
        return {}  # notification — no response

    line = proc.stdout.readline()  # type: ignore[union-attr]
    if not line:
        stderr = proc.stderr.read()  # type: ignore[union-attr]
        raise RuntimeError(f"Server closed stdout. stderr:\n{stderr.decode()[-1000:]}")
    return json.loads(line.decode()).get("result", {})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="包含真实数据搜索测试")
    args = parser.parse_args()

    print("report-search MCP server — smoke tests\n")
    test_chunker()
    test_store()
    test_embedder()
    if args.full:
        test_search_social_responsibility()
    test_mcp_protocol()
    print("\n✓ All smoke tests passed!")
