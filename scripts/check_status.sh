#!/usr/bin/env bash
# FinMind-wiles 状态检查 — MCP + Skills + Gateway
set -e

echo "╔════════════════════════════════════════╗"
echo "║        FinMind-wiles 状态检查         ║"
echo "╚════════════════════════════════════════╝"

echo ""
echo "━━━ MCP Server ━━━"
if ps aux | grep -q "[r]eport_search"; then
    ps aux | grep "[r]eport_search" | awk '{printf "  进程: PID=%s\n", $2}'
else
    echo "  进程: 未运行（懒加载，发消息后出现）"
fi

grep "MCP tools init\|Total tools.*MCP" logs/gateway.log 2>/dev/null | tail -1 | sed 's/.*- //'

if [ -f ~/.report_search/faiss.index ]; then
    echo "  索引:"
    ls -lh ~/.report_search/ | awk 'NR>1 {printf "    %s  %s\n", $9, $5}'
    cd mcp_servers/report_search && KMP_DUPLICATE_LIB_OK=TRUE uv run python -c "
import faiss, json
idx = faiss.read_index('$HOME/.report_search/faiss.index')
with open('$HOME/.report_search/metadata.json') as f: meta = json.load(f)
reports = meta.get('reports',{})
print(f'    向量: {idx.ntotal}  |  报告: {len(reports)}  |  片段: {len(meta.get(\"chunks\",[]))}')
for r in reports.values():
    print(f'    {r.get(\"file_name\",\"?\")} | {r.get(\"company_name\",\"-\")} | {r.get(\"year\",\"-\")}年 | {r.get(\"num_chunks\",0)} chunks')
" 2>/dev/null
else
    echo "  索引: 未创建"
fi
cd "$(git rev-parse --show-toplevel 2>/dev/null || echo ~/projects/FinMind-wiles)" 2>/dev/null || true

echo ""
echo "━━━ Skills ━━━"
curl -s http://localhost:8001/api/skills 2>/dev/null | python3 -c "
import json, sys
skills = json.load(sys.stdin).get('skills', [])
custom = [s['name'] for s in skills if s.get('category')=='legacy' and s.get('enabled')]
print(f'  总计: {len(skills)}  |  自定义: {len(custom)} 个')
for n in custom: print(f'    ✓ {n}')
" 2>/dev/null

echo ""
echo "━━━ Gateway ━━━"
lsof -ti :8001 >/dev/null 2>&1 && echo "  ✓ Gateway (8001)" || echo "  ✗ Gateway down"
lsof -ti :2026 >/dev/null 2>&1 && echo "  ✓ Nginx (2026)" || true
lsof -ti :3000 >/dev/null 2>&1 && echo "  ✓ Frontend (3000)" || true
