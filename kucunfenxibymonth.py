import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Tuple, Optional

# ===================== 页面配置 =====================
st.set_page_config(page_title="库存滞销复盘看板", layout="wide")
st.title("📊 整体滞销情况分析")

# ===================== 常量配置 =====================
TARGET_CLEAR_DATE = datetime(2026, 10, 31)
RISK_LEVELS = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]
RISK_COLORS = {
    "整体": "#f5f5f5",
    "健康": "#e8f5e9",
    "低滞销风险": "#fff8e1",
    "中滞销风险": "#ffebee",
    "高滞销风险": "#ffcdd2",
}
TURN_DAYS_THRESHOLDS = [
    (100, "健康"),
    (150, "低滞销风险"),
    (180, "中滞销风险"),
    (float("inf"), "高滞销风险"),
]
OVER_DAYS_THRESHOLDS = [
    (0, "健康"),
    (10, "低滞销风险"),
    (20, "中滞销风险"),
    (float("inf"), "高滞销风险"),
]


# ===================== 数据加载 =====================
@st.cache_data(ttl=3600, show_spinner="正在加载数据...")
def load_data(file: str = "moon-date.xlsx") -> Tuple[pd.DataFrame, ...]:
    """加载并清洗Excel多表数据"""
    sheets = {
        "snap": "补货建议-每月快照",
        "prod": "商品信息",
        "sale": "销量数据-每月",
        "pur": "采购数据-每月",
    }
    dfs = {}
    with pd.ExcelFile(file) as xls:
        for key, sheet_name in sheets.items():
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            dfs[key] = df

    # 时间字段统一转换
    dfs["snap"]["时间"] = pd.to_datetime(dfs["snap"]["时间"], errors="coerce")
    dfs["sale"]["时间"] = pd.to_datetime(dfs["sale"]["时间"], errors="coerce")

    return dfs["snap"], dfs["prod"], dfs["sale"], dfs["pur"]


df_snap, df_prod, df_sale, df_pur = load_data()


# ===================== 数据加工 =====================
def build_master_df(
    df_snap: pd.DataFrame,
    df_prod: pd.DataFrame,
    df_sale: pd.DataFrame,
    df_pur: pd.DataFrame,
) -> pd.DataFrame:
    """构建主分析表：合并快照、销量、商品信息、采购数据"""

    # 1. 合并销量
    df = df_snap.merge(
        df_sale[["MSKU", "时间", "销量"]],
        on=["MSKU", "时间"],
        how="left",
    )
    df["销量"] = df["销量"].fillna(0)

    # 2. 合并商品维度（去重，避免笛卡尔积）
    prod_cols = ["MSKU", "是否年份", "类别", "岁数"]
    df_prod_use = df_prod[prod_cols].drop_duplicates(subset=["MSKU"])
    df = df.merge(df_prod_use, on="MSKU", how="left")

    # 3. 合并采购透视表
    pur_pivot = (
        df_pur.pivot_table(
            index="MSKU",
            columns="采购类型",
            values="采购量",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename(
            columns={
                "年前采购": "年前采购总量",
                "年后采购": "年后采购总量",
            }
        )
    )
    for col in ["年前采购总量", "年后采购总量"]:
        if col not in pur_pivot.columns:
            pur_pivot[col] = 0
    df = df.merge(
        pur_pivot[["MSKU", "年前采购总量", "年后采购总量"]],
        on="MSKU",
        how="left",
    )

    # 4. 库存指标计算（向量化，无逐行循环）
    overseas_cols = ["FBA库存", "FBA在途", "海外仓可用", "海外仓在途"]
    local_cols = ["本地可用", "待检待上架量", "待交付"]

    df["海外库存"] = df[overseas_cols].sum(axis=1, min_count=1).fillna(0)
    df["本地库存"] = df[local_cols].sum(axis=1, min_count=1).fillna(0)
    df["总库存"] = df["海外库存"] + df["本地库存"]

    cost = df["采购成本"].fillna(0)
    df["总库存金额"] = df["总库存"] * cost
    df["总滞销金额"] = (
        df["海外库存"] * (cost + df["头程费用"].fillna(0))
        + df["本地库存"] * cost
    )

    # 5. 周转天数
    df["日均"] = df["日均"].fillna(0)
    df["周转天数"] = np.where(
        df["日均"] > 0,
        df["总库存"] / df["日均"],
        np.nan,
    )

    return df


df_merge = build_master_df(df_snap, df_prod, df_sale, df_pur)


# ===================== 风险等级判定（向量化） =====================
def classify_risk_vectorized(
    df: pd.DataFrame,
    year_option: str,
    target_date: datetime,
) -> pd.Series:
    """向量化判定滞销风险等级，替代逐行apply"""

    # 基础条件
    valid = (
        df["周转天数"].notna()
        & (df["日均"] > 0)
        & (df["总库存"] > 0)
    )
    is_year = df["是否年份"].astype(str).str.strip() == "是"

    # 初始化结果
    risk = pd.Series("无日均/库存数据", index=df.index)

    # --- 非年份品：按周转天数 ---
    mask_non_year = valid & ~is_year
    turn = df.loc[mask_non_year, "周转天数"]
    for threshold, label in TURN_DAYS_THRESHOLDS:
        risk.loc[mask_non_year & (turn <= threshold)] = label

    # --- 年份品 ---
    mask_year = valid & is_year

    if year_option == "按照清库存口径（预计售罄时间）":
        # 向量化计算预计售罄日期与超期天数
        need_days = df.loc[mask_year, "总库存"] / df.loc[mask_year, "日均"]
        sell_dt = df.loc[mask_year, "时间"] + pd.to_timedelta(need_days, unit="D")
        over_days = (sell_dt - target_date).dt.days

        for threshold, label in OVER_DAYS_THRESHOLDS:
            if label == "健康":
                risk.loc[mask_year & (over_days <= threshold)] = label
            else:
                risk.loc[mask_year & (over_days > threshold)] = label
    else:
        # 按周转天数口径
        turn_y = df.loc[mask_year, "周转天数"]
        for threshold, label in TURN_DAYS_THRESHOLDS:
            risk.loc[mask_year & (turn_y <= threshold)] = label

    return risk


st.subheader("⚙️ 年份品计算口径")
year_option = st.radio(
    "",
    ["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"],
    horizontal=True,
)

df_merge["滞销风险等级"] = classify_risk_vectorized(
    df_merge, year_option, TARGET_CLEAR_DATE
)


# ===================== 时间选择 =====================
st.divider()
time_list = sorted(
    df_merge["时间"].dt.strftime("%Y-%m-%d").dropna().unique()
)
sel_time = st.selectbox("选择统计时间", time_list, index=len(time_list) - 1)

# 当前期与上期数据切片
df_curr = df_merge[df_merge["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()
prev_time = time_list[-2] if len(time_list) >= 2 else sel_time
df_prev = df_merge[df_merge["时间"].dt.strftime("%Y-%m-%d") == prev_time].copy()


# ===================== 指标计算 =====================
def calc_metrics(
    df_curr: pd.DataFrame,
    df_prev: pd.DataFrame,
    risk_name: str,
) -> Dict:
    """计算单个风险等级的所有指标"""

    risk_list = ["低滞销风险", "中滞销风险", "高滞销风险"]

    if risk_name == "整体":
        curr_data = df_curr
        prev_data = df_prev
    else:
        curr_data = df_curr[df_curr["滞销风险等级"] == risk_name]
        prev_data = df_prev[df_prev["滞销风险等级"] == risk_name]

    # 基础指标
    sku_curr = curr_data["MSKU"].nunique()
    sku_prev = prev_data["MSKU"].nunique()

    stock_curr = curr_data["总库存"].sum()
    stock_prev = prev_data["总库存"].sum()

    amt_curr = curr_data["总库存金额"].sum()
    amt_prev = prev_data["总库存金额"].sum()

    # 滞销指标（仅非健康卡片需要）
    unsale_curr = curr_data[curr_data["滞销风险等级"].isin(risk_list)]
    unsale_prev = prev_data[prev_data["滞销风险等级"].isin(risk_list)]

    unsale_stock_curr = unsale_curr["总库存"].sum()
    unsale_stock_prev = unsale_prev["总库存"].sum()

    unsale_amt_curr = unsale_curr["总滞销金额"].sum()
    unsale_amt_prev = unsale_prev["总滞销金额"].sum()

    # 占比计算
    if risk_name in risk_list:
        usp = unsale_stock_curr / stock_curr if stock_curr != 0 else 0.0
        uap = unsale_amt_curr / amt_curr if amt_curr != 0 else 0.0
    else:
        usp = 0.0
        uap = 0.0

    return {
        "sku_curr": sku_curr,
        "sku_prev": sku_prev,
        "sku_diff": sku_curr - sku_prev,
        "stock_curr": stock_curr,
        "stock_prev": stock_prev,
        "stock_diff": stock_curr - stock_prev,
        "amt_curr": amt_curr,
        "amt_prev": amt_prev,
        "amt_diff": amt_curr - amt_prev,
        "unsale_stock_curr": unsale_stock_curr,
        "unsale_stock_prev": unsale_stock_prev,
        "unsale_stock_diff": unsale_stock_curr - unsale_stock_prev,
        "unsale_stock_pct": usp,
        "unsale_amt_curr": unsale_amt_curr,
        "unsale_amt_prev": unsale_amt_prev,
        "unsale_amt_diff": unsale_amt_curr - unsale_amt_prev,
        "unsale_amt_pct": uap,
    }


# ===================== 渲染工具函数 =====================
def fmt_diff(diff: float) -> Tuple[str, str]:
    """返回(颜色, 带符号字符串)"""
    color = "#e53935" if diff >= 0 else "#2e7d32"
    sign = f"+{diff:,.0f}" if diff >= 0 else f"{diff:,.0f}"
    return color, sign


def render_card(title: str, metrics: Dict) -> str:
    """生成单个卡片的HTML"""

    bg = RISK_COLORS.get(title, "#f5f5f5")

    # SKU
    sku_color, sku_sign = fmt_diff(metrics["sku_diff"])
    # 库存
    stk_color, stk_sign = fmt_diff(metrics["stock_diff"])
    # 金额
    amt_color, amt_sign = fmt_diff(metrics["amt_diff"])

    # 滞销字段（仅非健康卡片）
    unsale_html = ""
    if title != "健康":
        us_color, us_sign = fmt_diff(metrics["unsale_stock_diff"])
        ua_color, ua_sign = fmt_diff(metrics["unsale_amt_diff"])

        unsale_html = """
        <div style="font-size:14px;margin-bottom:6px;color:#333333;">
            滞销库存：{unsale_stock_curr:,.0f}（占比：{unsale_stock_pct:.2%}）
            <span style="font-size:11px;color:{us_color};font-weight:normal;">（{us_sign}，上月：{unsale_stock_prev:,.0f}）</span>
        </div>
        <div style="font-size:14px;color:#333333;">
            滞销金额：{unsale_amt_curr:,.0f}（占比：{unsale_amt_pct:.2%}）
            <span style="font-size:11px;color:{ua_color};font-weight:normal;">（{ua_sign}，上月：{unsale_amt_prev:,.0f}）</span>
        </div>
        """.format(
            unsale_stock_curr=metrics["unsale_stock_curr"],
            unsale_stock_pct=metrics["unsale_stock_pct"],
            us_color=us_color,
            us_sign=us_sign,
            unsale_stock_prev=metrics["unsale_stock_prev"],
            unsale_amt_curr=metrics["unsale_amt_curr"],
            unsale_amt_pct=metrics["unsale_amt_pct"],
            ua_color=ua_color,
            ua_sign=ua_sign,
            unsale_amt_prev=metrics["unsale_amt_prev"],
        )

    return """
    <div style="background-color:{bg};padding:20px;border-radius:12px;line-height:2.2;margin-bottom:15px;">
        <div style="font-size:22px;font-weight:bold;text-align:center;margin-bottom:15px;color:#1a1a1a;">{title}</div>
        <div style="font-size:18px;font-weight:bold;margin-bottom:8px;color:#1a1a1a;">
            SKU个数：{sku_curr:,.0f}
            <span style="font-size:12px;color:{sku_color};font-weight:normal;">（{sku_sign}，上月：{sku_prev:,.0f}）</span>
        </div>
        <div style="font-size:14px;margin-bottom:6px;color:#333333;">
            总库存：{stock_curr:,.0f}
            <span style="font-size:11px;color:{stk_color};font-weight:normal;">（{stk_sign}，上月：{stock_prev:,.0f}）</span>
        </div>
        {unsale_html}
        <div style="font-size:14px;margin-bottom:6px;color:#333333;">
            总金额：{amt_curr:,.0f}
            <span style="font-size:11px;color:{amt_color};font-weight:normal;">（{amt_sign}，上月：{amt_prev:,.0f}）</span>
        </div>
    </div>
    """.format(
        bg=bg,
        title=title,
        sku_curr=metrics["sku_curr"],
        sku_color=sku_color,
        sku_sign=sku_sign,
        sku_prev=metrics["sku_prev"],
        stock_curr=metrics["stock_curr"],
        stk_color=stk_color,
        stk_sign=stk_sign,
        stock_prev=metrics["stock_prev"],
        unsale_html=unsale_html,
        amt_curr=metrics["amt_curr"],
        amt_color=amt_color,
        amt_sign=amt_sign,
        amt_prev=metrics["amt_prev"],
    )


# ===================== 页面渲染 =====================
st.divider()
st.subheader("📦 整体滞销情况概览")
cols = st.columns(5)

card_titles = ["整体", "健康", "低滞销风险", "中滞销风险", "高滞销风险"]

for idx, title in enumerate(card_titles):
    metrics = calc_metrics(df_curr, df_prev, title)
    with cols[idx]:
        st.markdown(render_card(title, metrics), unsafe_allow_html=True)