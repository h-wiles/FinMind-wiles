#!/usr/bin/env python3
"""
财务指标计算脚本。

用法:
    python calculate.py --data-file /path/to/financials.json \
        --metrics "roe,gross_margin,dupont" \
        --output /path/to/metrics.json

支持指标: roe, gross_margin, net_margin, debt_ratio, current_ratio,
          dupont, fcf_yield, yoy_growth, cagr, altman_z, all
"""

import argparse
import json
import sys
from pathlib import Path


# ─── 数据提取工具 ──────────────────────────────────────────

def _extract(data: dict, *keys: str, default=0.0) -> float:
    """从财报 JSON 中递归提取科目金额。遍历 data["data"] 列表匹配 item 名称。"""
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            for entry in data["data"]:
                item_name = entry.get("item", "")
                if any(k in item_name for k in keys):
                    try:
                        return float(entry.get("amount", 0))
                    except (ValueError, TypeError):
                        return default
        for v in data.values():
            result = _extract(v, *keys, default=default)
            if result != default:
                return result
    return default


def _find_period_data(data: dict, period: str) -> dict | None:
    """找到指定期间的数据。"""
    if isinstance(data, dict):
        for key in ["income_statement", "balance_sheet", "cash_flow"]:
            if key in data:
                section = data[key]
                if isinstance(section, dict) and "data" in section:
                    return section
                if isinstance(section, list):
                    for item in section:
                        if isinstance(item, dict) and item.get("period") == period:
                            return item
    return data


# ─── 计算函数（纯函数，可直接 import）─────────────────────

def calc_roe(data: dict) -> dict:
    """ROE = 净利润 / 股东权益 × 100%"""
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    equity = _extract(data, "股东权益合计", "归属于母公司股东权益合计", "所有者权益合计")
    if equity == 0:
        return {"value": None, "formula": "净利润 / 股东权益 × 100%", "unit": "%", "error": "股东权益为0"}
    return {
        "value": round(net_profit / equity * 100, 2),
        "formula": "净利润 / 股东权益 × 100%",
        "unit": "%",
        "detail": {"net_profit": net_profit, "equity": equity},
    }


def calc_gross_margin(data: dict) -> dict:
    """毛利率 = (营业收入 - 营业成本) / 营业收入 × 100%"""
    revenue = _extract(data, "营业收入", "营业总收入", "总收入")
    cost = _extract(data, "营业成本", "营业总成本")
    if revenue == 0:
        return {"value": None, "formula": "(营收 - 营业成本) / 营收 × 100%", "unit": "%", "error": "营收为0"}
    return {
        "value": round((revenue - cost) / revenue * 100, 2),
        "formula": "(营收 - 营业成本) / 营收 × 100%",
        "unit": "%",
        "detail": {"revenue": revenue, "cost": cost},
    }


def calc_net_margin(data: dict) -> dict:
    """净利率 = 净利润 / 营业收入 × 100%"""
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    revenue = _extract(data, "营业收入", "营业总收入", "总收入")
    if revenue == 0:
        return {"value": None, "formula": "净利润 / 营收 × 100%", "unit": "%", "error": "营收为0"}
    return {
        "value": round(net_profit / revenue * 100, 2),
        "formula": "净利润 / 营收 × 100%",
        "unit": "%",
        "detail": {"net_profit": net_profit, "revenue": revenue},
    }


def calc_debt_ratio(data: dict) -> dict:
    """资产负债率 = 总负债 / 总资产 × 100%"""
    total_liability = _extract(data, "负债合计", "负债总计", "总负债")
    total_asset = _extract(data, "资产总计", "总资产", "资产合计")
    if total_asset == 0:
        return {"value": None, "formula": "总负债 / 总资产 × 100%", "unit": "%", "error": "总资产为0"}
    return {
        "value": round(total_liability / total_asset * 100, 2),
        "formula": "总负债 / 总资产 × 100%",
        "unit": "%",
        "detail": {"total_liability": total_liability, "total_asset": total_asset},
    }


def calc_current_ratio(data: dict) -> dict:
    """流动比率 = 流动资产 / 流动负债"""
    current_assets = _extract(data, "流动资产合计")
    current_liability = _extract(data, "流动负债合计")
    if current_liability == 0:
        return {"value": None, "formula": "流动资产 / 流动负债", "unit": "", "error": "流动负债为0"}
    return {
        "value": round(current_assets / current_liability, 2),
        "formula": "流动资产 / 流动负债",
        "unit": "",
        "detail": {"current_assets": current_assets, "current_liability": current_liability},
    }


def calc_dupont(data: dict) -> dict:
    """杜邦三因子分析：ROE = 净利率 × 资产周转率 × 权益乘数"""
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    revenue = _extract(data, "营业收入", "营业总收入", "总收入")
    total_asset = _extract(data, "资产总计", "总资产", "资产合计")
    equity = _extract(data, "股东权益合计", "归属于母公司股东权益合计", "所有者权益合计")

    if revenue == 0 or total_asset == 0 or equity == 0:
        return {"value": None, "formula": "净利率 × 资产周转率 × 权益乘数", "unit": "%", "error": "分母含零"}

    net_margin = net_profit / revenue
    asset_turnover = revenue / total_asset
    equity_multiplier = total_asset / equity
    roe = net_margin * asset_turnover * equity_multiplier * 100

    return {
        "value": round(roe, 2),
        "formula": "净利率 × 资产周转率 × 权益乘数",
        "unit": "%",
        "breakdown": {
            "net_margin": {
                "value": round(net_margin * 100, 2),
                "formula": "净利润 / 营收",
                "detail": {"net_profit": net_profit, "revenue": revenue},
            },
            "asset_turnover": {
                "value": round(asset_turnover, 2),
                "formula": "营收 / 总资产",
                "detail": {"revenue": revenue, "total_asset": total_asset},
            },
            "equity_multiplier": {
                "value": round(equity_multiplier, 2),
                "formula": "总资产 / 股东权益",
                "detail": {"total_asset": total_asset, "equity": equity},
            },
        },
        "interpretation_hint": {
            "high_net_margin": "品牌/技术壁垒 → 盈利能力强",
            "high_asset_turnover": "运营效率 → 薄利多销型",
            "high_equity_multiplier": "高杠杆 → 财务风险关注",
        },
    }


def calc_yoy_growth(data: dict) -> dict:
    """同比增长率：营收和净利润的同比变化"""
    # 需要至少两期数据
    current = data
    result = {}
    for metric, keys in [("revenue", ("营业收入", "营业总收入")), ("net_profit", ("净利润",))]:
        current_val = _extract(current, *keys)
        result[metric] = {
            "current": current_val,
            "note": "同比计算需要两期数据，仅提供当期值。请确保 data 中包含去年同期数据",
        }
    return {
        "value": result,
        "formula": "(当期 - 同期) / |同期| × 100%",
        "unit": "%",
    }


def calc_quick_ratio(data: dict) -> dict:
    """速动比率 = (流动资产 - 存货) / 流动负债"""
    current_assets = _extract(data, "流动资产合计")
    inventory = _extract(data, "存货", "存货净额")
    current_liability = _extract(data, "流动负债合计")
    if current_liability == 0:
        return {"value": None, "formula": "(流动资产 - 存货) / 流动负债", "unit": "", "error": "流动负债为0"}
    return {
        "value": round((current_assets - inventory) / current_liability, 2),
        "formula": "(流动资产 - 存货) / 流动负债",
        "unit": "",
    }


def calc_ocf_ni_ratio(data: dict) -> dict:
    """经营现金流 / 净利润"""
    ocf = _extract(data, "经营活动产生的现金流量净额", "经营活动现金流净额")
    net_profit = _extract(data, "净利润", "归属于母公司股东的净利润")
    if net_profit == 0:
        return {"value": None, "formula": "经营现金流 / 净利润", "unit": "", "error": "净利润为0"}
    return {
        "value": round(ocf / net_profit, 2),
        "formula": "经营现金流 / 净利润",
        "unit": "",
        "detail": {"ocf": ocf, "net_profit": net_profit},
    }


def calc_altman_z(data: dict, market_cap: float = 0) -> dict:
    """Altman Z-score = 1.2×X1 + 1.4×X2 + 3.3×X3 + 0.6×X4 + 1.0×X5"""
    working_capital = _extract(data, "流动资产合计") - _extract(data, "流动负债合计")
    total_asset = _extract(data, "资产总计", "总资产")
    retained_earnings = _extract(data, "盈余公积", "未分配利润")
    ebit = _extract(data, "营业利润", "利润总额")
    total_liability = _extract(data, "负债合计", "负债总计")
    revenue = _extract(data, "营业收入", "营业总收入")

    if total_asset == 0:
        return {"value": None, "formula": "1.2X1+1.4X2+3.3X3+0.6X4+1.0X5", "error": "总资产为0"}

    x1 = working_capital / total_asset
    x2 = retained_earnings / total_asset
    x3 = ebit / total_asset
    x4 = (market_cap / total_liability) if total_liability > 0 else 0
    x5 = revenue / total_asset

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    return {
        "value": round(z, 2),
        "formula": "1.2X1+1.4X2+3.3X3+0.6X4+1.0X5",
        "breakdown": {
            "X1_wc_to_ta": round(x1, 4),
            "X2_re_to_ta": round(x2, 4),
            "X3_ebit_to_ta": round(x3, 4),
            "X4_mc_to_tl": round(x4, 4),
            "X5_rev_to_ta": round(x5, 4),
        },
        "zone": "safe" if z > 2.99 else ("grey" if z > 1.81 else "distress"),
        "zone_label": "🟢 安全区" if z > 2.99 else ("🟡 灰色区" if z > 1.81 else "🔴 危险区"),
    }


# ─── 指标注册表 ──────────────────────────────────────────

METRICS_REGISTRY = {
    "roe": calc_roe,
    "gross_margin": calc_gross_margin,
    "net_margin": calc_net_margin,
    "debt_ratio": calc_debt_ratio,
    "current_ratio": calc_current_ratio,
    "quick_ratio": calc_quick_ratio,
    "dupont": calc_dupont,
    "yoy_growth": calc_yoy_growth,
    "ocf_ni_ratio": calc_ocf_ni_ratio,
    "altman_z": calc_altman_z,
}

ALL_METRICS = list(METRICS_REGISTRY.keys())


def main():
    parser = argparse.ArgumentParser(
        description="财务指标计算工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"支持指标: {', '.join(ALL_METRICS)}, all",
    )
    parser.add_argument("--data-file", required=True, help="financial_data 工具输出的 JSON 文件路径")
    parser.add_argument("--metrics", default="all", help="要计算的指标，逗号分隔（默认 all）")
    parser.add_argument("--market-cap", type=float, default=0, help="市值（Altman Z-score 需要）")
    parser.add_argument("--output", default=None, help="输出 JSON 文件路径（默认 stdout）")
    args = parser.parse_args()

    # 读取数据
    data_path = Path(args.data_file)
    if not data_path.exists():
        print(json.dumps({"error": f"文件不存在: {args.data_file}"}, ensure_ascii=False))
        sys.exit(1)
    data = json.loads(data_path.read_text(encoding="utf-8"))

    # 确定要计算的指标
    metric_list = ALL_METRICS if args.metrics == "all" else [m.strip() for m in args.metrics.split(",")]

    # 验证指标名
    invalid = [m for m in metric_list if m not in METRICS_REGISTRY]
    if invalid:
        print(json.dumps({"error": f"不支持的指标: {invalid}", "available": ALL_METRICS}, ensure_ascii=False))
        sys.exit(1)

    # 执行计算
    results = {
        "_meta": {
            "source_file": str(data_path.absolute()),
            "metrics": metric_list,
        }
    }
    for metric in metric_list:
        fn = METRICS_REGISTRY[metric]
        try:
            if metric == "altman_z":
                results[metric] = fn(data, market_cap=args.market_cap)
            else:
                results[metric] = fn(data)
        except Exception as e:
            results[metric] = {"error": str(e), "metric": metric}

    output_json = json.dumps(results, indent=2, ensure_ascii=False, default=str)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"✅ 结果已写入 {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
