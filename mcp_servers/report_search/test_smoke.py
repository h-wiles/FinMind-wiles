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
    from report_search.store import VectorStore

    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        store = VectorStore(db_path, embedding_dim=512)
        stats = os.stat(__file__)

        # Insert
        rid = store.upsert_report(Path("test.pdf"), stats, "600519", 2024)
        assert rid == 1
        store.insert_chunks(
            rid,
            [
                {
                    "chunk_index": 0,
                    "text": "营收1500亿",
                    "section_title": "经营",
                    "section_path": "经营",
                    "embedding": [0.1] * 512,
                },
            ],
        )

        # Search
        results = store.search([0.15] * 512, top_k=1)
        assert len(results) == 1
        assert results[0]["company_name"] == "600519"

        # Filter
        assert len(store.search([0.15] * 512, year=2023)) == 0
        assert len(store.search([0.15] * 512, year=2024)) == 1

        # List
        reports = store.list_reports()
        assert len(reports) == 1

        # Idempotent re-upsert
        assert store.upsert_report(Path("test.pdf"), stats, "600519", 2024) == rid

        print("  ✓ store")
    finally:
        store.close()
        db_path.unlink(missing_ok=True)


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
    print("report-search MCP server — smoke tests\n")
    test_chunker()
    test_store()
    test_embedder()
    test_mcp_protocol()
    print("\n✓ All smoke tests passed!")
