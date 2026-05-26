import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

# ===================== 数据加载 =====================
@st.cache_data(ttl=3600, show_spinner="正在加载数据...")
def load_data(file: str = "moon-date.xlsx") -> Tuple[pd.DataFrame, ...]:
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

    dfs["snap"]["时间"] = pd.to_datetime(dfs["snap"]["时间"], errors="coerce").dt.normalize()
    dfs["sale"]["时间"] = pd.to_datetime(dfs["sale"]["时间"], errors="coerce").dt.normalize()

    return dfs["snap"], dfs["prod"], dfs["sale"], dfs["pur"]

df_snap, df_prod, df_sale, df_pur = load_data()

# ===================== 数据加工：按你最新公式 100% 重写 =====================
def build_master_df(df_snap, df_prod, df_sale, df_pur):
    df = df_snap.merge(df_sale[["MSKU", "时间", "销量"]], on=["MSKU", "时间"], how="left")
    df["销量"] = df["销量"].fillna(0)

    prod_cols = ["MSKU", "是否年份", "类别", "岁数"]
    df_prod_use = df_prod[prod_cols].drop_duplicates(subset=["MSKU"])
    df = df.merge(df_prod_use, on="MSKU", how="left")

    pur_pivot = df_pur.pivot_table(index="MSKU", columns="采购类型", values="采购量", aggfunc="sum", fill_value=0).reset_index()
    rename_map = {}
    if "年前采购" in pur_pivot.columns: rename_map["年前采购"] = "年前采购总量"
    if "年后采购" in pur_pivot.columns: rename_map["年后采购"] = "年后采购总量"
    pur_pivot = pur_pivot.rename(columns=rename_map)
    for c in ["年前采购总量", "年后采购总量"]:
        if c not in pur_pivot.columns: pur_pivot[c] = 0

    df = df.merge(pur_pivot[["MSKU", "年前采购总量", "年后采购总量"]], on="MSKU", how="left")

    # ===================== 【最新公式】FBA+AWD+在途库存 =====================
    df["FBA+AWD+在途库存"] = (
        df["FBA库存"].fillna(0)
        + df["FBA在途"].fillna(0)
        + df["海外仓可用"].fillna(0)
        + df["海外仓在途"].fillna(0)
    ).round(2)

    # ===================== 本地库存 =====================
    df["本地库存"] = (
        df["本地可用"].fillna(0)
        + df["待检待上架量"].fillna(0)
        + df["待交付"].fillna(0)
    ).round(2)

    # ===================== 【最新公式】总库存 =====================
    df["总库存"] = (
        df["FBA+AWD+在途库存"]
        + df["本地库存"]
    ).round(2)

    # 日均销量防0处理
    df["日均"] = df["日均"].fillna(0)
    df.loc[df["日均"] == 0, "日均"] = 0.01

    # ===================== 周转天数 =====================
    df["周转天数"] = (df["总库存"] / df["日均"]).round(2)
    df["周转天数"] = df["周转天数"].clip(upper=36500)

    # ===================== 预计用完时间 =====================
    df["预计总库存用完时间"] = df["时间"] + pd.to_timedelta(df["周转天数"], unit="D")

    # ===================== ✅ 正确金额计算（你要求的版本） =====================
    df["采购成本"] = df["采购成本"].fillna(0)
    df["头程费用"] = df["头程费用"].fillna(0)

    # FBA金额 = FBA库存 * (成本+头程)
    df["FBA金额"] = (df["FBA+AWD+在途库存"] * (df["采购成本"] + df["头程费用"])).round(2)
    # 本地金额 = 本地库存 * 成本
    df["本地金额"] = (df["本地库存"] * df["采购成本"]).round(2)
    # 总金额 = FBA金额 + 本地金额
    df["总库存金额"] = (df["FBA金额"] + df["本地金额"]).round(2)

    return df

df_merge = build_master_df(df_snap, df_prod, df_sale, df_pur)

# ===================== 风险等级 + 滞销数量 100% 按你要求 =====================
def classify_risk_and_unsold(df, year_option, target_date):
    df = df.copy()
    is_year = df["是否年份"].astype(str).str.strip() == "是"

    # ---------- 1. 基准天数 ----------
    target_days_common = 100
    target_days_year = (target_date - df["时间"]).dt.days  # 到2026-10-31的天数
    df["目标基准天数"] = np.where(
        (is_year) & (year_option == "按照清库存口径（预计售罄时间）"),
        target_days_year,
        target_days_common
    )

    # ---------- 2. 预计用完时间 & 超期天数 ----------
    df["预计总库存用完时间"] = df["时间"] + pd.to_timedelta(df["周转天数"], unit="D")
    over_days = (df["预计总库存用完时间"] - target_date).dt.days

    # ---------- 3. 风险判定 ----------
    risk = pd.Series("高滞销风险", index=df.index)

    if year_option == "按照库存周转天数口径":
        # 全部按周转天数
        turn = df["周转天数"]
        risk = np.where(turn <= 100, "健康",
                 np.where(turn <= 150, "低滞销风险",
                 np.where(turn <= 180, "中滞销风险", "高滞销风险")))
    else:
        # 清库存口径：分年份/非年份
        # --- 非年份品：按周转天数 ---
        mask_non_year = ~is_year
        turn_non_year = df.loc[mask_non_year, "周转天数"]
        risk.loc[mask_non_year] = np.where(
            turn_non_year <= 100, "健康",
            np.where(turn_non_year <= 150, "低滞销风险",
            np.where(turn_non_year <= 180, "中滞销风险", "高滞销风险"))
        )

        # --- 年份品：按 over_days 严格区间（0-10,10-20,>20）---
        mask_year = is_year
        over_year = over_days.loc[mask_year]
        risk.loc[mask_year] = np.where(
            over_year <= 0, "健康",
            np.where((over_year > 0) & (over_year <= 10), "低滞销风险",
            np.where((over_year > 10) & (over_year <= 20), "中滞销风险",
            "高滞销风险"))
        )

    df["滞销风险等级"] = risk

    # ===================== 滞销数量（你最新公式） =====================
    unhealthy = df["滞销风险等级"] != "健康"
    base = df["目标基准天数"]

    # FBA+AWD+在途滞销数量
    df["FBA+AWD+在途滞销数量"] = np.where(
        unhealthy,
        (df["FBA+AWD+在途库存"] - df["日均"] * base).clip(lower=0).round(2),
        0
    )

    # 总滞销库存
    df["总滞销库存"] = np.where(
        unhealthy,
        (df["总库存"] - df["日均"] * base).clip(lower=0).round(2),
        0
    )

    # 本地滞销数量
    df["本地滞销数量"] = (df["总滞销库存"] - df["FBA+AWD+在途滞销数量"]).round(2)

    # ===================== ✅ 滞销金额（你要求的正确计算） =====================
    df["FBA滞销金额"] = (df["FBA+AWD+在途滞销数量"] * (df["采购成本"] + df["头程费用"])).round(2)
    df["本地滞销金额"] = (df["本地滞销数量"] * df["采购成本"]).round(2)
    df["总滞销金额"] = (df["FBA滞销金额"] + df["本地滞销金额"]).round(2)

    return df

# ===================== 界面 =====================
st.subheader("⚙️ 年份品计算口径")
year_option = st.radio("", ["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"], horizontal=True)

# 计算风险 + 滞销
df_merge = classify_risk_and_unsold(df_merge, year_option, TARGET_CLEAR_DATE)

st.divider()
df_merge["年月"] = df_merge["时间"].dt.to_period("M")
time_list = sorted(df_merge["年月"].dropna().astype(str).unique())
sel_month = st.selectbox("选择统计时间", time_list, index=len(time_list)-1)

prev_month = sel_month
if len(time_list) >= 2:
    idx = time_list.index(sel_month)
    prev_month = time_list[idx-1] if idx > 0 else sel_month

df_curr = df_merge[df_merge["年月"] == sel_month].copy()
df_prev = df_merge[df_merge["年月"] == prev_month].copy()

# ===================== 指标计算 =====================
def calc_metrics(df_curr, df_prev, risk_name):
    # 定义风险等级列表
    risk_list = ["低滞销风险", "中滞销风险", "高滞销风险"]

    if risk_name == "整体":
        # ========== 【修正核心】整体卡片：分别计算当前月、上月的低+中+高 ==========
        # 当前月：筛选当前月的低/中/高SKU
        curr_unsale = df_curr[df_curr["滞销风险等级"].isin(risk_list)]
        # 上月：筛选上月的低/中/高SKU（不是用当前月的SKU去上月找！）
        prev_unsale = df_prev[df_prev["滞销风险等级"].isin(risk_list)]

        # 整体SKU数：当前月所有SKU
        sku_c = df_curr["MSKU"].nunique()
        sku_p = df_prev["MSKU"].nunique()
        sku_diff = sku_c - sku_p

        # 整体总库存：当前月所有SKU
        stk_c = df_curr["总库存"].sum()
        stk_p = df_prev["总库存"].sum()
        stk_diff = stk_c - stk_p

        # 整体总金额：当前月所有SKU
        amt_c = df_curr["总库存金额"].sum()
        amt_p = df_prev["总库存金额"].sum()
        amt_diff = amt_c - amt_p

        # 滞销库存：当前月低+中+高SKU的库存
        u_stk_c = curr_unsale["总滞销库存"].sum()
        u_stk_p = prev_unsale["总滞销库存"].sum()
        u_stk_diff = u_stk_c - u_stk_p
        pct_stk = u_stk_c / stk_c if stk_c != 0 else 0

        # 滞销金额：当前月低+中+高SKU的金额
        u_amt_c = curr_unsale["总滞销金额"].sum()
        u_amt_p = prev_unsale["总滞销金额"].sum()
        u_amt_diff = u_amt_c - u_amt_p
        pct_amt = u_amt_c / amt_c if amt_c != 0 else 0

    else:
        # ========== 单个风险等级卡片：逻辑不变 ==========
        c = df_curr[df_curr["滞销风险等级"] == risk_name]
        p = df_prev[df_prev["滞销风险等级"] == risk_name]

        sku_c = c["MSKU"].nunique()
        sku_p = p["MSKU"].nunique()
        sku_diff = sku_c - sku_p

        stk_c = c["总库存"].sum()
        stk_p = p["总库存"].sum()
        stk_diff = stk_c - stk_p

        amt_c = c["总库存金额"].sum()
        amt_p = p["总库存金额"].sum()
        amt_diff = amt_c - amt_p

        u_stk_c = c["总滞销库存"].sum()
        u_stk_p = p["总滞销库存"].sum()
        u_stk_diff = u_stk_c - u_stk_p
        pct_stk = u_stk_c / stk_c if stk_c != 0 else 0

        u_amt_c = c["总滞销金额"].sum()
        u_amt_p = p["总滞销金额"].sum()
        u_amt_diff = u_amt_c - u_amt_p
        pct_amt = u_amt_c / amt_c if amt_c != 0 else 0

    return {
        # SKU 指标
        "sku_curr": sku_c, "sku_prev": sku_p, "sku_diff": sku_diff,
        # 总库存 指标
        "stock_curr": stk_c, "stock_prev": stk_p, "stock_diff": stk_diff,
        # 总金额 指标
        "amt_curr": amt_c, "amt_prev": amt_p, "amt_diff": amt_diff,
        # 滞销库存 指标
        "unsale_stock_curr": u_stk_c, "unsale_stock_prev": u_stk_p, "unsale_stock_diff": u_stk_diff, "unsale_stock_pct": pct_stk,
        # 滞销金额 指标
        "unsale_amt_curr": u_amt_c, "unsale_amt_prev": u_amt_p, "unsale_amt_diff": u_amt_diff, "unsale_amt_pct": pct_amt
    }

# ===================== 卡片渲染 =====================
def render_card_compact(title, m):
    bg = RISK_COLORS.get(title, "#f5f5f5")

    # 数值格式化：正数红色，负数绿色
    def fmt(d):
        return ("#e53935", f"+{d:,.0f}") if d >=0 else ("#2e7d32", f"{d:,.0f}")

    # 各指标的环比颜色+符号
    sku_c, sku_s = fmt(m["sku_diff"])
    stk_c, stk_s = fmt(m["stock_diff"])
    amt_c, amt_s = fmt(m["amt_diff"])

    # 卡片HTML主体
    parts = [f'<div style="background:{bg};padding:20px;border-radius:12px;margin-bottom:15px;">',
             f'<div style="font-size:22px;font-weight:bold;text-align:center">{title}</div>',
             # SKU：当前值 + 上月值 + 环比
             f'<div style="font-size:18px;font-weight:bold">SKU：{m["sku_curr"]:,.0f} （上月：{m["sku_prev"]:,.0f}） <span style="color:{sku_c}">({sku_s})</span></div>',
             # 总库存：当前值 + 上月值 + 环比
             f'<div style="font-size:14px">总库存：{m["stock_curr"]:,.0f} （上月：{m["stock_prev"]:,.0f}） <span style="color:{stk_c}">({stk_s})</span></div>']

    # 非健康卡片：新增滞销指标（含上月值）
    if title != "健康":
        usc, uss = fmt(m["unsale_stock_diff"])
        uac, uas = fmt(m["unsale_amt_diff"])
        parts.append(f'<div style="font-size:14px">滞销库存：{m["unsale_stock_curr"]:,.0f} ({m["unsale_stock_pct"]:.1%}) （上月：{m["unsale_stock_prev"]:,.0f}） <span style="color:{usc}">({uss})</span></div>')
        parts.append(f'<div style="font-size:14px">滞销金额：{m["unsale_amt_curr"]:,.0f} ({m["unsale_amt_pct"]:.1%}) （上月：{m["unsale_amt_prev"]:,.0f}） <span style="color:{uac}">({uas})</span></div>')

    # 总金额：当前值 + 上月值 + 环比
    parts.append(f'<div style="font-size:14px">总金额：{m["amt_curr"]:,.0f} （上月：{m["amt_prev"]:,.0f}） <span style="color:{amt_c}">({amt_s})</span></div></div>')
    st.html("".join(parts))

# ===================== 输出 =====================
st.divider()
st.subheader("📦 整体滞销情况概览")
cols = st.columns(5)
for i, t in enumerate(["整体", "健康", "低滞销风险", "中滞销风险", "高滞销风险"]):
    with cols[i]:
        render_card_compact(t, calc_metrics(df_curr, df_prev, t))

# ===================== 可选：展示明细 =====================
with st.expander("📋 查看每个MSKU计算明细（可核对公式）"):
    show_cols = [
        "MSKU", "是否年份", "时间",
        "FBA+AWD+在途库存", "总库存", "日均", "周转天数",
        "预计总库存用完时间", "滞销风险等级","采购成本","头程费用",
        "FBA+AWD+在途滞销数量", "总滞销库存", "本地滞销数量",
        "FBA金额", "本地金额", "总库存金额",
        "FBA滞销金额", "本地滞销金额", "总滞销金额"
    ]
    st.dataframe(df_curr[show_cols], use_container_width=True)

# ===================== 1行4列 滞销分析图表 =====================
st.divider()
st.subheader("📊 滞销金额 & 数量 拆解分析")

# 1. 统一计算所有等级数据
risk_list = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]
data_list = []
for r in risk_list:
    m = calc_metrics(df_curr, df_prev, r)
    data_list.append({
        "风险等级": r,
        "总金额": m["amt_curr"],
        "滞销金额": m["unsale_amt_curr"],
        "总库存": m["stock_curr"],
        "滞销库存": m["unsale_stock_curr"],
    })
df_all = pd.DataFrame(data_list)

# 2. 计算整体指标
total_amt = df_all["总金额"].sum()
total_unsold_amt = df_all[df_all["风险等级"] != "健康"]["滞销金额"].sum()
total_not_unsold_amt = total_amt - total_unsold_amt

total_stock = df_all["总库存"].sum()
total_unsold_stock = df_all[df_all["风险等级"] != "健康"]["滞销库存"].sum()
total_not_unsold_stock = total_stock - total_unsold_stock

# 3. 1行4列布局
col1, col2, col3, col4 = st.columns([2, 1, 2, 1])

# ---------------------- 第1列：滞销金额 饼图 ----------------------
with col1:
    st.markdown("#### 💰 滞销金额结构")
    fig1 = go.Figure()
    fig1.add_trace(go.Pie(
        labels=["不滞销金额", "滞销金额"],
        values=[total_not_unsold_amt, total_unsold_amt],
        domain=dict(x=[0, 0.65], y=[0, 1]),
        marker=dict(colors=["#e8f5e9", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig1.add_trace(go.Pie(
        labels=["低滞销风险", "中滞销风险", "高滞销风险"],
        values=df_all[df_all["风险等级"] != "健康"]["滞销金额"],
        domain=dict(x=[0.72, 1], y=[0.2, 0.8]),
        marker=dict(colors=["#fff8e1", "#ffebee", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig1.update_layout(height=450, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig1, use_container_width=True)

# ---------------------- 第2列：金额明细表 ----------------------
with col2:
    st.markdown("#### 📄 金额明细")
    amt_detail = df_all[["风险等级", "滞销金额"]].copy()
    st.dataframe(amt_detail, use_container_width=True, height=450)

# ---------------------- 第3列：滞销数量 饼图 ----------------------
with col3:
    st.markdown("#### 📦 滞销数量结构")
    fig3 = go.Figure()
    fig3.add_trace(go.Pie(
        labels=["不滞销数量", "滞销数量"],
        values=[total_not_unsold_stock, total_unsold_stock],
        domain=dict(x=[0, 0.65], y=[0, 1]),
        marker=dict(colors=["#e8f5e9", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig3.add_trace(go.Pie(
        labels=["低滞销风险", "中滞销风险", "高滞销风险"],
        values=df_all[df_all["风险等级"] != "健康"]["滞销库存"],
        domain=dict(x=[0.72, 1], y=[0.2, 0.8]),
        marker=dict(colors=["#fff8e1", "#ffebee", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig3.update_layout(height=450, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig3, use_container_width=True)

# ---------------------- 第4列：数量明细表 ----------------------
with col4:
    st.markdown("#### 📄 数量明细")
    stock_detail = df_all[["风险等级", "滞销库存"]].copy()
    st.dataframe(stock_detail, use_container_width=True, height=450)



