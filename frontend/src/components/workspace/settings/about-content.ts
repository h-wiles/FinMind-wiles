/**
 * About FinMind-wiles markdown content. Inlined to avoid raw-loader dependency
 * (Turbopack cannot resolve raw-loader for .md imports).
 */
export const aboutMarkdown = `# 📊 [FinMind-wiles](https://github.com/h-wiles/FinMind-wiles)

> **财报分析 Super Agent — 基于 DeerFlow 二次开发**

FinMind-wiles 是基于 [DeerFlow](https://github.com/bytedance/deer-flow) 构建的垂直领域 AI 智能代理，专注于 **A股（沪深）、港股、美股** 上市公司财报分析。

---

## 🚀 核心能力

* **多市场覆盖**: A股 (akshare)、港股 & 美股 (yfinance)，全部免费数据源
* **盈利能力分析**: ROE、杜邦三因子拆解、毛利率、净利率
* **风险评估**: Altman Z-score、OCF/NI 比、现金流画像、商誉减值检测
* **估值分析**: PE/PB/PS 历史分位、FCF Yield、PEG、跨市场对比
* **同业对比**: 多公司指标横向排名与基准对照
* **报告生成**: 结构化 Markdown 报告 + 图表 + Excel 导出

## 🔧 技术架构

* **4 个分析 Skill**: financial-report-analysis / financial-metrics-calc / financial-risk-assessment / financial-valuation
* **3 个专项子代理**: data-fetcher（取数）/ financial-analyst（分析）/ report-generator（报告）
* **2 个数据源**: akshare（A股主力）+ yfinance（美股 & 港股）

---

## 🌟 GitHub 仓库

[github.com/h-wiles/FinMind-wiles](https://github.com/h-wiles/FinMind-wiles)

---

## 📜 许可证

FinMind-wiles 基于 MIT License 开源。

---

## 🙌 致谢

FinMind-wiles 基于 [DeerFlow](https://github.com/bytedance/deer-flow) 构建，感谢 DeerFlow 团队和开源社区。

核心框架:
- **[LangChain](https://github.com/langchain-ai/langchain)** & **[LangGraph](https://github.com/langchain-ai/langgraph)**
- **[Next.js](https://nextjs.org/)**
- **[Shadcn](https://ui.shadcn.com/)**
`;
