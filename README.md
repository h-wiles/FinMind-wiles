# 财报分析 Super Agent — 基于 DeerFlow 二次开发

---

# 目录

- [README — 项目概览](#readme--项目概览)
  - [项目简介](#项目简介)
  - [核心能力](#核心能力)
  - [系统架构](#系统架构)
  - [快速开始](#快速开始)
  - [目录结构](#目录结构)
  - [前置条件](#前置条件)

---

# README — 项目概览

## 项目简介

**财报分析 Agent** 是基于 [DeerFlow](https://github.com/deer-flow) AI 超级代理框架，通过二次开发构建的垂直领域智能代理。专注于 **A 股（沪深）、港股、美股** 上市公司财报分析，支持用户以自然语言提问，自动完成数据获取、财务分析、图表可视化和报告生成。

### 为什么基于 DeerFlow？

DeerFlow 提供了完整的 AI Agent 基础设施（详见 [AGENTS.md](../AGENTS.md)），包括：

| 能力 | DeerFlow 提供 | 本项目使用 |
|------|--------------|-----------|
| 沙箱执行 | `LocalSandbox` / `AioSandbox`（Docker） | ✅ Agent 可在隔离环境中执行脚本 |
| 工具系统 | `tools` + `community/` 社区工具 | ✅ 新增 `community/financial/` 财务工具 |
| Skill 系统 | `skills/custom/` + SKILL.md 格式 | ✅ 编写 `financial-report-analysis` skill |
| 子代理委派 | `task()` 工具 + `subagents.custom_agents` | ✅ 3 个专项子代理 |
| 记忆系统 | `memory.json` 持久化用户偏好和知识 | ✅ 播种会计准则和行业基准 |
| MCP 集成 | `extensions_config.json` | 🔧 可选：接入外部金融数据 API |
| Web 搜索 | `web_search` + `web_fetch` 社区工具 | ✅ 补充新闻/公告等非结构化信息 |
| 图表可视化 | `chart-visualization` skill | ✅ 自动生成财务图表 |
| 流式响应 | SSE + `StreamBridge` | ✅ 前端实时展示分析进度 |
| 身份系统 | `SOUL.md` + `AgentConfig` | ✅ 定义财报分析师人格 |

---

## 核心能力

### 🗂️ 多市场覆盖

| 市场 | 股票代码示例 | 数据源 | 财报类型 |
|------|-------------|--------|---------|
| A 股（沪深） | `600519`（茅台）、`000858`（五粮液） | akshare → 东方财富/新浪 | 年报、季报 |
| 港股 | `HK.00700`（腾讯）、`HK.09988`（阿里） | akshare + yfinance | 年度/中期报告 |
| 美股 | `AAPL`（Apple）、`TSLA`（Tesla） | yfinance | 10-K、10-Q |

### 📊 分析维度

- **盈利能力** — ROE、毛利率、净利率、杜邦拆解
- **成长性** — CAGR、营收/利润同比环比增长
- **财务健康度** — 资产负债率、流动比率、自由现金流、Altman Z-score
- **估值分析** — PE/PB/PS/FCF Yield 历史分位
- **现金流质量** — 经营现金流/净利润比、自由现金流趋势
- **同业对比** — 多公司指标横向对比

### 📝 输出形式

1. **结构化文本报告** — 执行摘要 + 分项分析 + 风险提示
2. **可视化图表** — 趋势图、对比柱状图、杜邦分析拆解图（委托 `chart-visualization` skill）
3. **Excel 数据表** — 多 Sheet 工作簿（摘要、指标、原始数据）

---

## 系统架构

```
用户 → "茅台2024年Q3毛利率为什么下滑？"
  │
  ▼
┌─────────────────────────────────────────────────┐
│            财报分析 Agent                         │
│  ┌───────────────────────────────────────────┐  │
│  │        SOUL.md（分析师人格）               │  │
│  │  "你是专业的财务分析师，专注三地财报..."    │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │   financial-report-analysis SKILL         │  │
│  │   ┌─────────┐ ┌──────────┐ ┌───────────┐  │  │
│  │   │Phase 1  │→│Phase 2   │→│Phase 3-5  │  │  │
│  │   │需求理解  │ │数据获取   │ │分析+报告   │  │  │
│  │   └─────────┘ └──────────┘ └───────────┘  │  │
│  └───────────────────────────────────────────┘  │
│                                                    │
│  ┌───────────────┐  ┌────────────────────────┐   │
│  │ 子代理:        │  │ 子代理:                 │   │
│  │ data-fetcher  │  │ financial-analyst       │   │
│  │ "只取数不分析" │  │ "深度分析+风险识别"     │   │
│  └───────────────┘  └────────────────────────┘   │
│  ┌──────────────────────────────────────────┐    │
│  │ 子代理: report-generator                  │    │
│  │ "报告合成+图表+Excel"                      │    │
│  └──────────────────────────────────────────┘    │
│                                                    │
│  工具层:                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │
│  │financial │ │web_search│ │calculate │ │export │ │
│  │_data API │ │(社区工具) │ │.py 脚本  │ │_report│ │
│  │(akshare) │ │          │ │          │ │.py    │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────┘ │
└─────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 1. 克隆 DeerFlow 并启动
git clone https://github.com/deer-flow/deer-flow.git
cd deer-flow
make setup          # 交互式配置向导
make dev            # 启动所有服务（Gateway + Frontend + Nginx）

# 2. 安装财务数据依赖
cd backend
uv pip install akshare openpyxl

# 3. 创建 Skill 目录
mkdir -p skills/custom/financial-report-analysis/{scripts,references,templates}

# 4. 创建财务工具模块
mkdir -p backend/packages/harness/deerflow/community/financial

# 5. 按本文档实施各阶段开发

# 6. 验证
# 在 DeerFlow Chat UI 中提问：
# "茅台2024年报的ROE是多少？和五粮液对比一下"
```

---

## 目录结构

完成开发后，新增/修改的文件如下：

```
deer-flow/
│
├── config.yaml                                  # ✏️ 修改：添加 tools + subagents
├── extensions_config.json                       # ✏️ 修改：启用 skill
├── backend/
│   └── packages/harness/deerflow/
│       └── community/
│           └── financial/                       # ✨ 新建：财务工具模块
│               ├── __init__.py
│               ├── provider.py                  # 数据提供商抽象层
│               └── tools.py                     # 3 个 LangChain tool
│
├── skills/
│   └── custom/
│       └── financial-report-analysis/           # ✨ 新建：财报分析 Skill
│           ├── SKILL.md                         # 核心技能文档（~300 行）
│           ├── scripts/
│           │   ├── calculate.py                 # 财务指标计算脚本
│           │   └── export_report.py             # Excel 报告导出脚本
│           ├── references/
│           │   ├── metrics.md                   # 财务指标参考手册
│           │   ├── accounting.md                # 三地会计准则差异
│           │   └── frameworks.md               # 分析框架详解
│           └── templates/
│               └── report_template.md           # 报告模板
│
└── backend/.deer-flow/
    └── users/{user_id}/
        └── agents/financial-analyst/            # ✨ 新建：Agent 配置
            ├── config.yaml                      # Agent 配置
            └── SOUL.md                          # Agent 人格
```

---

## 前置条件

| 依赖 | 版本 | 用途 |
|------|------|------|
| DeerFlow | 最新 main 分支 | AI Agent 框架 |
| Python | ≥ 3.12 | 运行环境 |
| akshare | ≥ 1.14.0 | A股/港股财务数据（免费，无需 API Key） |
| yfinance | ≥ 0.2.0 | 美股/港股补充数据 |
| openpyxl | ≥ 3.1.0 | Excel 报告生成 |
| Node.js | ≥ 18.0.0 | chart-visualization skill 依赖 |

---