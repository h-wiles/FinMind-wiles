# FinMind-wiles — 财报分析 Super Agent

基于 [DeerFlow](https://github.com/bytedance/deer-flow) AI 超级代理框架二次开发的垂直领域智能代理。专注于 **A 股（沪深）、港股、美股** 上市公司财报分析，支持自然语言提问，自动完成数据获取、指标计算、风险识别、估值分析和报告生成。

---

## 目录

- [项目简介](#项目简介)
- [核心能力](#核心能力)
- [架构设计](#架构设计)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [使用示例](#使用示例)
- [测试](#测试)
- [依赖](#依赖)
- [扩展方向](#扩展方向)

---

## 项目简介

FinMind-wiles 在 DeerFlow 框架的 **5 个扩展点** 上填入财报分析领域专属内容：

| 扩展点 | 填入内容 | 说明 |
|--------|---------|------|
| ① `community/` 工具 | `financial/` 模块 | 3 个 LangChain Tool：`financial_data`、`stock_info`、`financial_metrics` |
| ② `skills/custom/` | 4 个分析 Skill | 核心工作流 + 指标计算 + 风险评估 + 估值分析 |
| ③ `subagents.custom_agents` | 3 个专项子代理 | 数据获取 / 深度分析 / 报告生成，关注点分离 |
| ④ `SOUL.md` + `memory.json` | Agent 人格 + 领域知识 | 分析师人设 + 12 条预设会计准则和行业基准 |
| ⑤ `config.yaml` + `extensions_config.json` | 全局集成 | 工具注册、子代理配置、Skill 开关 |

### 为什么基于 DeerFlow？

DeerFlow 提供了开箱即用的 Agent 基础设施：

| 能力 | 来源 | 本项目使用方式 |
|------|------|--------------|
| 沙箱执行 | `LocalSandbox` / `AioSandbox` | Agent 在隔离环境中执行数据脚本 |
| 工具系统 | `community/` 插件机制 | 新增 `financial/` 社区工具，挂载到 config |
| Skill 系统 | SKILL.md + 渐进式加载 | 4 个 Skill 按需加载，详细参考放 `references/` |
| 子代理委派 | `task()` 工具 | 3 个子代理分担取数、分析、报告 |
| 记忆系统 | `memory.json` | 播种会计准则、行业基准、用户偏好 |
| Web 搜索 | `ddg_search` / `tavily` | 补充公告、新闻、行业动态 |
| 图表可视化 | `chart-visualization` Skill | 自动生成 ROE 对比、趋势图等 |
| 流式响应 | SSE + `StreamBridge` | 前端实时展示分析进度 |
| 身份系统 | `SOUL.md` + `AgentConfig` | "财报分析师"人设 |

---

## 核心能力

### 多市场覆盖

| 市场 | 代码格式 | 示例 | 数据源 |
|------|---------|------|--------|
| A 股（沪深） | 6 位数字 | `600519`（茅台）、`000858`（五粮液） | akshare → 东方财富 |
| 港股 | `HK.` 前缀 | `HK.00700`（腾讯） | akshare + yfinance |
| 美股 | 字母代码 | `AAPL`、`TSLA` | yfinance |

### 分析维度

| 维度 | Skill | 核心内容 |
|------|-------|---------|
| **盈利能力** | `financial-metrics-calc` | ROE、毛利率、净利率、杜邦三因子拆解 |
| **成长性** | `financial-metrics-calc` | 营收/利润 CAGR、同比环比增长 |
| **财务健康度** | `financial-risk-assessment` | 资产负债率、流动/速动比率、Altman Z-score |
| **现金流质量** | `financial-risk-assessment` | OCF/NI 比、现金流画像、FCF 趋势 |
| **估值分析** | `financial-valuation` | PE/PB/PS 历史分位、FCF Yield、PEG |
| **同业对比** | `financial-metrics-calc` | 多公司指标横向排名、雷达图 |
| **报告生成** | `financial-report-analysis` | 结构化文本 + 图表 + Excel 导出 |

### 输出形式

1. **结构化 Markdown 报告** — 执行摘要 → 财务表现 → 指标解读 → 风险提示 → 总结
2. **可视化图表** — 委托 `chart-visualization` Skill 生成柱状图、趋势图、杜邦拆解图
3. **Excel 数据表** — 3 Sheet（分析摘要 / 财务指标 / 原始数据）

---

## 架构设计

### 5 阶段分析工作流

```
用户: "茅台2024年ROE为什么下降？"
  │
  ▼
┌─ Phase 1: 需求理解 ───────────────────────────────────────┐
│  识别: 600519, A股, 2024年报, 关注 ROE 趋势              │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 2: 数据获取 ───────────────────────────────────────┐
│  委派 financial-data-fetcher 子代理                        │
│  financial_data("600519", "all", "2024")                   │
│  stock_info("600519")                                     │
│  web_search("茅台 2024年报 公告")                          │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 3: 分析计算 ───────────────────────────────────────┐
│  委派 financial-analyst 子代理                             │
│  financial_metrics(data, "roe,dupont,yoy_growth")         │
│  读取 financial-risk-assessment SKILL.md 评估风险         │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 4: 可视化 ─────────────────────────────────────────┐
│  委托 chart-visualization Skill                           │
│  生成 ROE 对比柱状图、趋势折线图                           │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ Phase 5: 报告合成 ───────────────────────────────────────┐
│  委派 report-generator 子代理                              │
│  按 report_template.md 合成，export_report.py 导出 Excel  │
└──────────────────────────────────────────────────────────┘
```

### 子代理分工

```
主 Agent（财报分析师 SOUL）
  │
  ├─→ financial-data-fetcher    只取数，不分析
  │   工具: financial_data, stock_info, web_search
  │   禁用: task, financial_metrics, ask_clarification
  │
  ├─→ financial-analyst         只分析，不取数
  │   工具: financial_metrics, bash
  │   Skill: metrics-calc, risk-assessment, valuation
  │   禁用: financial_data, web_search
  │
  └─→ report-generator          只合成，不分析
      工具: bash, write_file
      Skill: chart-visualization
      禁用: financial_data, financial_metrics
```

### Agent 身份系统

```
SOUL.md ─────→ System Prompt <soul> 标签
  "你是专业财报分析师，专注三地市场..."
  Identity + Core Traits + Communication + Guardrails

config.yaml ─→ Agent 能力清单
  skills: [financial-report-analysis, ...]
  tool_groups: [financial, web, bash, ...]

memory.json ─→ System Prompt <memory> 标签
  12 条预设知识: 会计准则、行业基准、分析偏好
```

---

## 项目结构

```
FinMind-wiles/
│
├── README.md
├── config.yaml                                   # 工具注册 + 3 个子代理
├── extensions_config.json                        # Skill 启用开关
│
├── backend/
│   ├── packages/harness/deerflow/community/
│   │   └── financial/                            # 财务数据工具模块
│   │       ├── __init__.py
│   │       ├── provider.py                       # 数据提供商（akshare + yfinance）
│   │       └── tools.py                          # 3 个 LangChain Tool + 9 个计算函数
│   │
│   ├── tests/
│   │   ├── test_financial_provider.py            # 27 个 provider 测试
│   │   ├── test_financial_tools.py               # 46 个 tools 测试
│   │   └── test_financial_e2e.py                 # 26 个端到端测试
│   │
│   └── .deer-flow/users/default/
│       ├── memory.json                           # 12 条领域知识播种
│       └── agents/financial-analyst/
│           ├── SOUL.md                           # 分析师人格
│           └── config.yaml                       # Agent 能力清单
│
├── skills/custom/
│   ├── financial-report-analysis/                # 核心 Skill：5 阶段工作流
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── calculate.py                      # 9 个指标 CLI 计算工具
│   │   │   └── export_report.py                  # Excel 报告生成
│   │   ├── references/
│   │   │   ├── metrics.md                        # 指标公式参考手册
│   │   │   ├── accounting.md                     # 三地会计准则差异
│   │   │   └── frameworks.md                     # 分析框架详解
│   │   └── templates/
│   │       └── report_template.md                # 标准化报告模板
│   │
│   ├── financial-metrics-calc/                   # 指标计算 + 同业对比
│   │   ├── SKILL.md
│   │   └── references/formulas.md                # 20+ 指标公式大全
│   │
│   ├── financial-risk-assessment/                # 风险评估 + Z-score
│   │   ├── SKILL.md
│   │   └── references/risk-models.md             # 6 大风险维度 + 红旗标志
│   │
│   └── financial-valuation/                      # 估值分析 + 历史分位
│       ├── SKILL.md
│       └── references/valuation-methods.md       # PE/PB/FCF Yield 方法论
│
└── skills/public/                                 # DeerFlow 自带公共 Skill
    ├── chart-visualization/                       # 图表生成（本项目使用）
    ├── deep-research/                             # 深度研究（可选）
    └── data-analysis/                             # 数据分析（可选）
```

---

## 部署指南

FinMind-wiles 是 DeerFlow 的二次开发项目，部署方式与 DeerFlow 一致，支持三种模式。

### 方式一：本地开发（推荐入门）

适合个人使用、调试 Skill、验证分析效果。

```bash
# 1. 克隆 DeerFlow
git clone git@github.com:h-wiles/FinMind-wiles.git
cd FinMind-wiles

# 2. 将 FinMind-wiles 的文件覆盖到 DeerFlow 目录中
#    需要覆盖的内容见下方 "部署文件清单"

# 3. 安装 Python 依赖
cd backend
pip install akshare yfinance openpyxl
cd ..

# 4. 交互式配置（生成 config.yaml + extensions_config.json）
make setup

# 5. 编辑 config.yaml，确保以下内容已配置：
#    - tool_groups 包含 financial
#    - tools 包含 financial_data / stock_info / financial_metrics
#    - subagents.custom_agents 包含 3 个子代理
#    也可直接用 FinMind-wiles 预配置好的 config.yaml 替换

# 6. 编辑 extensions_config.json，启用 4 个 Skill
#    或直接用 FinMind-wiles 的 extensions_config.json 替换

# 7. 启动
make dev
# → Gateway :8001 | Frontend :3000 | Nginx :2026
# 浏览器打开 http://localhost:2026
```

### 方式二：Docker 部署（推荐生产）

适合团队共享、生产环境、需要沙箱隔离。

```bash
# 1. 确保 Docker 已安装并运行
docker --version

# 2. 准备 FinMind-wiles 文件（同方式一第 2 步）

# 3. 构建并启动
make docker-start

# 4. 查看日志
make docker-logs

# 5. 停止
make docker-stop
```

Docker 模式下各服务：
| 服务 | 端口 | 说明 |
|------|------|------|
| Nginx | 2026 | 统一入口（浏览器访问此端口） |
| Gateway | 8001 | Agent 运行时 + REST API |
| Frontend | 3000 | Next.js Web UI |
| Provisioner | 8002 | 沙箱管理（K8s 模式时启用） |

### 方式三：生产部署

```bash
make start          # 前台运行
make start-daemon   # 后台守护进程

# 停止
make stop
```

### 部署文件清单

将以下 FinMind-wiles 新增/修改的文件覆盖到 DeerFlow 项目中：

```
FinMind-wiles 项目文件                              → DeerFlow 对应位置
──────────────────────────────────────────────────────────────────────
# 核心配置文件（修改）
config.yaml                                   → config.yaml
extensions_config.json                        → extensions_config.json

# 财务工具模块（新增）
backend/packages/harness/deerflow/
  community/financial/                        → 同路径
    __init__.py
    provider.py
    tools.py

# 财报分析 Skill（新增）
skills/custom/
  financial-report-analysis/                  → 同路径
    SKILL.md, scripts/, references/, templates/
  financial-metrics-calc/                     → 同路径
    SKILL.md, references/
  financial-risk-assessment/                  → 同路径
    SKILL.md, references/
  financial-valuation/                        → 同路径
    SKILL.md, references/

# Agent 身份配置（新增）
backend/.deer-flow/users/default/
  memory.json                                 → 同路径
  agents/financial-analyst/
    SOUL.md                                   → 同路径
    config.yaml                               → 同路径

# 测试文件（可选）
backend/tests/
  test_financial_provider.py                  → 同路径
  test_financial_tools.py                     → 同路径
  test_financial_e2e.py                       → 同路径
```

### 部署后验证

```bash
# 1. 确认 3 个财务工具已注册
curl http://localhost:8001/api/models | grep financial

# 2. 确认 4 个 Skill 已启用
curl http://localhost:8001/api/skills | grep financial

# 3. 运行测试套件
cd backend && PYTHONPATH=. uv run python -m pytest tests/test_financial_*.py -v

# 4. 在 Chat UI 中测试
#    打开 http://localhost:2026
#    选择 financial-analyst Agent
#    输入: "茅台2024年报的ROE是多少？"
```

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是* | LLM API Key（或其他模型的环境变量） |
| `DEER_FLOW_HOME` | 否 | 数据存储目录（默认 `backend/.deer-flow/`） |
| `DEER_FLOW_CONFIG_PATH` | 否 | config.yaml 路径 |
| `DEER_FLOW_EXTENSIONS_CONFIG_PATH` | 否 | extensions_config.json 路径 |

> \* 取决于 `config.yaml` 中 `models` 的配置，FinMind-wiles 默认使用 DeepSeek。

### 生产环境建议

- **沙箱隔离**：将 `sandbox.use` 从 `LocalSandboxProvider` 切换为 `AioSandboxProvider`（Docker 隔离）
- **API 限流**：akshare 调用频率过高可能被限制，建议在 `provider.py` 中增加调用间隔（≥2s）
- **数据缓存**：财报数据不需要实时更新，建议对接本地缓存层（SQLite/Redis）
- **成本控制**：为子代理设置严格的 `max_turns` 和 `timeout_seconds`（当前已配置）
- **监控**：关注 `financial_data` 工具的调用成功率和响应时间
```

### 运行测试

```bash
cd backend
PYTHONPATH=. uv run python -m pytest tests/test_financial_*.py -v

# 99 passed — 覆盖 provider、tools、e2e 全链路
```

---

## 使用示例

### 场景 1: 单一公司财报分析

```
用户: "分析贵州茅台2024年年报，重点看ROE和毛利率"

Agent:
  → Phase 1: 识别 600519, 2024年报
  → Phase 2: 委派 data-fetcher 获取三张表 + 最新公告
  → Phase 3: 委派 analyst 计算指标
  → Phase 5: 输出报告

📊 贵州茅台 2024 年报分析

一、执行摘要
2024年茅台实现营收1500亿元，净利润750亿元，ROE 31.25%，
毛利率92.0%，盈利能力行业领先。

二、杜邦拆解
ROE = 净利率50.0% × 资产周转率0.5 × 权益乘数1.25
茅台的高ROE主要来自极高的净利率（品牌溢价），杠杆仅1.25倍。

三、风险提示
🟢 资产负债率仅20%，财务极其稳健
```

### 场景 2: 多公司对比

```
用户: "茅台和五粮液2024年谁更赚钱？"

Agent:
  → 同时获取两家数据
  → 对比 ROE / 毛利率 / 净利率 / 营收增速

| 指标 | 茅台 | 五粮液 |
|------|------|--------|
| ROE | 31.25% | 22.5% |
| 毛利率 | 92.0% | 75.2% |
| 净利率 | 50.0% | 38.1% |

茅台在盈利能力上全面领先，主要差距来自毛利率（品牌溢价）。
```

### 场景 3: 风险评估

```
用户: "帮我看看特斯拉有财务风险吗？"

Agent:
  → 读取 financial-risk-assessment Skill
  → 计算 Altman Z-score、OCF/NI 比、负债结构
  → 搜索最新公告和监管动态

🔍 Tesla 财务风险评估 — 综合评级: 🟡 关注

- 流动比率: 1.7（正常）
- 资产负债率: 44%（合理）
- OCF/NI比: 1.3（健康）
- Z-score: 2.8（灰色区）

主要关注点: 行业竞争加剧，价格战压缩毛利率
```

---

## 测试

```
tests/test_financial_provider.py  — 27 passed   市场识别/路由/安全转换
tests/test_financial_tools.py     — 46 passed   数据提取/指标计算/边界/错误处理
tests/test_financial_e2e.py       — 26 passed   全链路: Skill→工具→子代理→报告
─────────────────────────────────────────────────
Total                              99 passed ✅
```

测试覆盖：
- **provider 层**: `_classify` 7 种市场代码、`_route` 路由、`_safe_float` 边界
- **tools 层**: `_extract` 跨三表提取、9 个计算函数正常+空数据+负值+缺表
- **e2e 层**: Skill 发现注入、工具链调用、多公司对比、风险评估、跨市场、子代理配置、脚本 CLI

---

## 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| DeerFlow | 最新 main | AI Agent 框架 |
| Python | ≥ 3.12 | 运行环境 |
| akshare | ≥ 1.14.0 | A 股/港股免费财务数据 |
| yfinance | ≥ 0.2.0 | 美股/港股数据 |
| openpyxl | ≥ 3.1.0 | Excel 报告生成 |
| Node.js | ≥ 18.0.0 | chart-visualization Skill |

---

## 扩展方向

- [ ] **商业数据源接入** — Tushare Pro（A 股）、Wind、Bloomberg
- [ ] **PDF 财报解析** — 用户上传 PDF 自动提取三张表
- [ ] **实时行情** — 分析报告中加入实时股价
- [ ] **定时巡检** — 利用 DeerFlow Scheduler 定时检查关注列表财报更新
- [ ] **产业链图谱** — 上下游联动分析（如茅台毛利率下降 → 高粱涨价 → 上游种植企业）
- [ ] **预测模型** — 基于历史数据训练营收/利润预测
- [ ] **智能预警** — 自动识别财务异常信号主动提醒
