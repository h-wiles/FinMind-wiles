# FinMind-wiles — 财报分析 Super Agent

基于 [DeerFlow](https://github.com/bytedance/deer-flow) AI 超级代理框架构建的垂直领域智能代理，专注 **A 股（沪深）、港股、美股** 上市公司财报分析。

---

## 目录

- [核心能力](#核心能力)
- [架构设计](#架构设计)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [本地 PDF 财报搜索](#本地-pdf-财报搜索)
- [使用示例](#使用示例)
- [依赖](#依赖)

---

## 核心能力

| 能力 | 实现方式 |
|------|---------|
| **多市场数据** | `akshare`（A 股）+ `yfinance`（港股/美股），Provider 模式自动路由 |
| **语义搜索** | 自研 FAISS + BAAI/bge-small-zh-v1.5 嵌入，支持按公司/年份过滤 |
| **指标计算** | 10+ 财务指标确定性计算（ROE、杜邦拆解、毛利率、Altman-Z 等） |
| **风险评估** | 现金流画像、OCF/NI 比、商誉减值检测 |
| **估值分析** | PE/PB/PS 历史分位、FCF Yield、PEG、跨市场对比 |
| **报告生成** | 结构化 Markdown 报告 + 图表 + Excel 导出 |

---

## 架构设计

### 整体服务拓扑

```
用户浏览器 (localhost:2026)
       │
       ▼
    Nginx (port 2026)
       ├── / → Frontend (port 3000, Next.js)
       └── /api/* → Gateway (port 8001, FastAPI)
                       │
                       ├── LangGraph Agent（财报分析助手）
                       │     ├── 系统提示（SOUL.md + memory.json）
                       │     ├── 工具集（financial_data + search_local_reports + ...）
                       │     └── 技能（4 个 SKILL.md）
                       │
                       ├── MCP Server（stdio 子进程）
                       │     └── PDF 索引引擎
                       │
                       └── 子代理（data-fetcher / analyst / report-generator）
```

### 数据流

```
用户提问 "茅台2025年报分红策略"
  │
  ▼
Agent 选择工具
  ├── ① search_local_reports（本地 PDF 语义搜索，优先）
  ├── ② financial_data + stock_info（结构化 API）
  └── ③ web_search（网络兜底）
  │
  ▼
search_local_reports 执行链路：
  SentenceTransformer → 查询向量 → FAISS IndexFlatIP → Top-K → JSON metadata → 返回段落
```

### 本地 PDF 搜索的双层设计

```
┌─────────────────────────────────────────────┐
│ MCP Server（后台索引引擎）                    │
│   PDF → markitdown/pymupdf4llm → Chunk →    │
│   BGE Embedding → FAISS + metadata.json     │
│   提供 3 个 MCP Tool（search/list/index）     │
└─────────────────────────────────────────────┘
                    │ 共享 FAISS 索引
                    ▼
┌─────────────────────────────────────────────┐
│ Community Tool（Agent 搜索通道）              │
│   LangChain @tool，与 financial_data 同级    │
│   直接读取 FAISS 索引 + JSON → 语义搜索      │
└─────────────────────────────────────────────┘
```

**设计理由**：DeepSeek v4 模型对 MCP 协议工具的调用成功率低，但能正常使用同类型的 LangChain 社区工具。MCP Server 负责后台索引，社区工具负责进程内搜索，各司其职。

### 索引流水线

```
data/reports/*.pdf
  │
  ▼ converter.py（pymupdf4llm 优先 → markitdown 兜底）
Markdown 文本
  │
  ▼ chunker.py（按 ## 章节标题拆分，超长段按段落 fallback + overlap）
136 个 Chunk（附带章节路径如 "管理层讨论 > 经营情况"）
  │
  ▼ embedder.py（BAAI/bge-small-zh-v1.5，512 维，本地离线，L2 归一化）
512 维浮点向量
  │
  ▼ store.py（FAISS IndexIDMap(IndexFlatIP) + JSON metadata）
~/.report_search/
  ├── faiss.index    # 向量索引
  └── metadata.json  # 报告元数据 + 分块文本
```

### 保留的 DeerFlow 能力

| 模块 | 在项目中的角色 |
|------|--------------|
| 中间件链（26 个） | 沙箱隔离、工具错误恢复、循环检测、记忆注入 |
| 技能系统 | 4 个自定义财报分析 Skill，斜杠激活 |
| 子代理委托 | 3 个专项子代理（取数/分析/报告），工具白黑名单隔离 |
| 记忆系统 | 12 条财务领域知识种子 + 自动记忆持久化 |
| Agent 身份 | SOUL.md（人格）+ config.yaml（能力）+ memory.json（知识） |

---

## 项目结构

```
FinMind-wiles/
├── data/reports/                     # PDF 财报文件目录（.gitignore 排除）
├── skills/custom/                    # 4 个自定义技能
│   ├── financial-report-analysis/    # 核心分析工作流（5 阶段）
│   ├── financial-metrics-calc/       # 指标计算公式
│   ├── financial-risk-assessment/    # 风险评估方法
│   └── financial-valuation/          # 估值模型
├── mcp_servers/report_search/        # 自研 MCP 语义搜索服务器
│   └── report_search/
│       ├── server.py                 # MCP 服务（3 个 Tool）
│       ├── store.py                  # FAISS + JSON 向量存储
│       ├── indexer.py                # PDF 索引流水线
│       ├── embedder.py               # BGE 嵌入模型封装
│       ├── chunker.py                # 章节级分块
│       ├── converter.py              # PDF → Markdown
│       └── config.py                 # 环境变量配置
├── backend/
│   └── packages/harness/deerflow/
│       └── community/financial/
│           ├── tools.py              # financial_data / stock_info / financial_metrics
│           ├── provider.py           # akshare + yfinance Provider
│           └── report_search_tool.py # search_local_reports（LangChain 工具）
├── extensions_config.json            # MCP 服务器注册 + Skills 开关
├── config.yaml                       # 主配置（工具、子代理、模型、沙箱）
└── .env                              # 环境变量（API Key、离线模式等）
```

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
cd backend && uv sync
cd ../mcp_servers/report_search && uv sync
cd ../..

# 配置 .env
cp .env.example .env  # 填入 DEEPSEEK_API_KEY 等
```

### 2. 放入 PDF 财报

```bash
# 将 PDF 文件放入 data/reports/，命名建议：
#   600519_2025_年报.pdf
#   HK.00700_2024_annual.pdf
#   AAPL_2024_10K.pdf
```

### 3. 启动

```bash
make dev
# 打开 http://localhost:2026
```

首次发消息时 MCP Server 自动启动并索引 PDF，模型首次加载约 20 秒（后续使用缓存）。

### 4. 检查状态

```bash
./scripts/check_status.sh
```

---

## 本地 PDF 财报搜索

### 工作原理

1. Gateway 启动 → MCP Server 子进程启动 → 扫描 `data/reports/` → 自动索引
2. Agent 对话时调用 `search_local_reports` 工具 → FAISS 语义搜索 → 返回最相关段落

### 环境要求

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REPORT_SEARCH_DIR` | PDF 目录 | `data/reports/` |
| `REPORT_SEARCH_INDEX` | 索引目录 | `~/.report_search/` |
| `HF_HUB_OFFLINE` | 离线模式 | `1` |
| `TRANSFORMERS_OFFLINE` | 离线模式 | `1` |
| `KMP_DUPLICATE_LIB_OK` | OpenMP 兼容 | `TRUE` |
| `OMP_NUM_THREADS` | 线程数 | `1` |

---

## 使用示例

### 场景 1：查询年报定性内容

```
用户: 贵州茅台2025年报中讨论了哪些风险因素

Agent:
  1. search_local_reports("风险因素", company_name="贵州茅台", year=2025)
     → 从 PDF 返回 5 个相关段落（行业竞争、政策风险、原材料波动等）
  2. financial_data("600519") → 结构化数据
  3. 综合回答
```

### 场景 2：多公司对比

```
用户: 对比茅台和五粮液2024年的ROE和毛利率

Agent:
  1. search_local_reports → 查两份年报的 MD&A
  2. financial_data → 拉三张表
  3. financial_metrics → 计算 ROE 拆解、毛利率
  4. 输出对比报告
```

### 场景 3：定量 + 定性交叉验证

```
用户: 茅台2025年净利润下降的原因是什么

Agent:
  1. search_local_reports("净利润 下降 原因") → 管理层解释
  2. financial_data → 利润表 → 计算同比变化
  3. financial_metrics → 费用率、毛利率拆解
  4. web_search → 行业动态补充
```

---

## 依赖

### 核心

| 组件 | 用途 |
|------|------|
| DeerFlow | AI 超级代理框架（LangGraph + LangChain） |
| FAISS | 向量相似度搜索 |
| BAAI/bge-small-zh-v1.5 | 中文嵌入模型（512 维，离线） |
| sentence-transformers | 嵌入模型加载 |
| akshare + yfinance | 多市场财务数据 |

### 环境变量

```bash
DEEPSEEK_API_KEY=sk-xxx          # DeepSeek API
DEER_FLOW_AUTH_DISABLED=1        # 本地开发关闭认证
HF_HUB_OFFLINE=1                 # 离线模式
KMP_DUPLICATE_LIB_OK=TRUE        # macOS OpenMP 兼容
OMP_NUM_THREADS=1                # 单线程避免冲突
```
