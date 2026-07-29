"""MCP server — exposes semantic search over local PDF financial reports.

Provides three tools:

    search_reports       — semantic search with optional company/year filters
    list_indexed_reports — inventory of indexed reports
    index_reports        — scan and (re-)index PDFs
"""

import logging

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from report_search.config import get_config
from report_search.embedder import Embedder
from report_search.indexer import Indexer
from report_search.store import VectorStore

logger = logging.getLogger(__name__)

# Pre-built tool definitions — static, so defined at module level.
_ALL_TOOLS = [
    Tool(
        name="search_reports",
        description=(
            "语义搜索本地已索引的 PDF 财报文件，返回与查询最相关的文本段落。\n\n"
            "使用场景：\n"
            "- 查找管理层对特定话题的讨论（如风险因素、行业竞争、战略规划）\n"
            "- 搜索财报中的定性信息披露（MD&A、关联交易、审计意见）\n"
            "- 补充 financial_data API 无法提供的非结构化文本信息\n\n"
            "注意：此工具仅搜索本地已索引的 PDF。如果索引为空，请先使用 index_reports。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询文本（中文或英文），描述你想查找的内容",
                },
                "company_name": {
                    "type": "string",
                    "description": "可选，按公司名称或代码过滤（如 '600519'、'贵州茅台'）",
                },
                "year": {
                    "type": "integer",
                    "description": "可选，按报告年份过滤（如 2024）",
                },
                "max_results": {
                    "type": "integer",
                    "default": 5,
                    "description": "返回的最大结果数（默认 5）",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_indexed_reports",
        description=(
            "列出所有已索引的 PDF 财报文件及其元数据。\n\n"
            "返回文件名、公司名称、年份、分块数量和索引时间。\n"
            "可用于确认哪些报告已被索引，以及索引是否最新。"
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="index_reports",
        description=(
            "扫描并索引 PDF 报告目录。增量索引：仅处理新增或变更的文件。\n\n"
            "参数 force=true 可强制重新索引所有文件。\n"
            "首次使用或添加新 PDF 后应调用此工具。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否强制重新索引所有文件（默认仅索引新增/变更的文件）",
                },
            },
        },
    ),
]


def _build_server() -> Server:
    """Build the MCP server with all tool handlers wired via constructor."""
    config = get_config()
    store = VectorStore(config.db_path, config.embedding_dim)
    embedder = Embedder(config.model_name)
    indexer = Indexer(config, store, embedder)

    # Auto-index on startup: catch up with any new PDFs
    try:
        result = indexer.scan_and_index()
        logger.info(
            "Startup indexing: %d new, %d updated, %d skipped, %d errors (total: %d)",
            result["new"],
            result["updated"],
            result["skipped"],
            result["errors"],
            result["total"],
        )
    except Exception:
        logger.exception("Startup indexing failed — server will still start")

    # ------------------------------------------------------------------
    # Handler: tools/list
    # ------------------------------------------------------------------

    async def on_list_tools(
        _ctx: ServerRequestContext,
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=_ALL_TOOLS)

    # ------------------------------------------------------------------
    # Handler: tools/call
    # ------------------------------------------------------------------

    async def on_call_tool(
        _ctx: ServerRequestContext,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        name = params.name
        arguments = params.arguments or {}

        if name == "search_reports":
            return await _search_reports(store, embedder, arguments)
        elif name == "list_indexed_reports":
            return await _list_reports(store)
        elif name == "index_reports":
            return await _index_reports(indexer, store, arguments)
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                isError=True,
            )

    return Server(
        "report-search",
        version="0.1.0",
        description="Semantic search over local PDF financial reports (A-share, HK, US)",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------


async def _search_reports(
    store: VectorStore, embedder: Embedder, args: dict
) -> CallToolResult:
    query: str = args["query"]
    company_name: str | None = args.get("company_name")
    year: int | None = args.get("year")
    max_results: int = args.get("max_results", 5)

    if store.get_report_count() == 0:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        "索引为空，没有可搜索的财报内容。\n\n"
                        "请先使用 index_reports 工具索引 PDF 财报文件，然后再搜索。"
                    ),
                )
            ]
        )

    query_embedding = embedder.embed_query(query)
    results = store.search(
        query_embedding,
        top_k=max_results,
        company_name=company_name,
        year=year,
    )

    if not results:
        hint = ""
        if company_name is not None or year is not None:
            hint = " 尝试去掉过滤条件扩大搜索范围。"
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"未找到与 '{query}' 相关的内容。{hint}",
                )
            ]
        )

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"### 结果 {i}（相似度: {r['similarity']:.3f}）\n"
            f"- 文件: {r['file_name']}\n"
            f"- 公司: {r.get('company_name', '-')}  |  年份: {r.get('year', '-')}\n"
            f"- 章节: {r.get('section_path') or r.get('section_title') or '-'}\n"
            f"\n{r['text']}"
        )

    return CallToolResult(
        content=[TextContent(type="text", text="\n\n---\n\n".join(lines))]
    )


async def _list_reports(store: VectorStore) -> CallToolResult:
    reports = store.list_reports()

    if not reports:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        "索引为空，没有已索引的报告。\n\n"
                        "请先使用 index_reports 工具索引 PDF 财报文件。"
                    ),
                )
            ]
        )

    lines = [f"共 {len(reports)} 份已索引报告：\n"]
    for r in reports:
        lines.append(
            f"- {r['file_name']}  |  {r.get('company_name', '-')}  "
            f"|  {r.get('year', '-')} 年  |  {r['num_chunks']} 个片段  "
            f"|  索引时间: {r.get('indexed_at', '-')}"
        )

    return CallToolResult(
        content=[TextContent(type="text", text="\n".join(lines))]
    )


async def _index_reports(
    indexer: Indexer, store: VectorStore, args: dict
) -> CallToolResult:
    force: bool = args.get("force", False)

    result = indexer.scan_and_index(force=force)

    chunks = store.get_chunk_count()
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=(
                    f"索引完成：\n"
                    f"- 新增: {result['new']} 份\n"
                    f"- 更新: {result['updated']} 份\n"
                    f"- 跳过: {result['skipped']} 份（未变更）\n"
                    f"- 错误: {result['errors']} 份\n"
                    f"- 总计: {result['total']} 份 PDF\n"
                    f"- 当前索引共 {chunks} 个可搜索片段"
                ),
            )
        ]
    )


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------


async def run_server() -> None:
    """Boot the MCP server over stdio."""
    server = _build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
