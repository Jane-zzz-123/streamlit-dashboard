import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px


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
        "店铺","MSKU", "品名","是否年份", "时间",
        "FBA+AWD+在途库存", "总库存", "日均", "周转天数",
        "预计总库存用完时间", "滞销风险等级","采购成本","头程费用",
        "FBA+AWD+在途滞销数量", "总滞销库存", "本地滞销数量",
        "FBA金额", "本地金额", "总库存金额",
        "FBA滞销金额", "本地滞销金额", "总滞销金额"
    ]
    st.dataframe(df_curr[show_cols], use_container_width=True)

# ===================== 1行3列 滞销分析图表（文字排版+配色+环比完整版） =====================
st.divider()
st.subheader("📊 整体滞销金额 & 数量 & SKU 拆解分析")

# 1. 统一计算所有等级数据
risk_list = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]
data_list = []
for r in risk_list:
    m = calc_metrics(df_curr, df_prev, r)
    data_list.append({
        "风险等级": r,
        "SKU数": m["sku_curr"],
        "SKU_prev": m["sku_prev"],
        "SKU_diff": m["sku_diff"],
        "总金额": m["amt_curr"],
        "amt_prev": m["amt_prev"],
        "amt_diff": m["amt_diff"],
        "总库存": m["stock_curr"],
        "stock_prev": m["stock_prev"],
        "stock_diff": m["stock_diff"],
        "滞销金额": m["unsale_amt_curr"],
        "unsale_amt_prev": m["unsale_amt_prev"],
        "unsale_amt_diff": m["unsale_amt_diff"],
        "滞销库存": m["unsale_stock_curr"],
        "unsale_stock_prev": m["unsale_stock_prev"],
        "unsale_stock_diff": m["unsale_stock_diff"],
    })
df_all = pd.DataFrame(data_list)

# 2. 整体指标
total_amt = df_all["总金额"].sum()
total_unsold_amt = df_all[df_all["风险等级"] != "健康"]["滞销金额"].sum()
total_not_unsold_amt = total_amt - total_unsold_amt
amt_diff_total = total_amt - df_all["amt_prev"].sum()
unsale_amt_diff_total = total_unsold_amt - df_all["unsale_amt_prev"].sum()

total_stock = df_all["总库存"].sum()
total_unsold_stock = df_all[df_all["风险等级"] != "健康"]["滞销库存"].sum()
total_not_unsold_stock = total_stock - total_unsold_stock
stock_diff_total = total_stock - df_all["stock_prev"].sum()
unsale_stock_diff_total = total_unsold_stock - df_all["unsale_stock_prev"].sum()

# 3. SKU 统计
df_sku = df_all.set_index("风险等级")
total_sku     = int(df_sku["SKU数"].sum())
total_sku_prev= int(df_sku["SKU_prev"].sum())
total_sku_diff= total_sku - total_sku_prev

healthy_sku   = int(df_sku.loc["健康", "SKU数"])
low_sku       = int(df_sku.loc["低滞销风险", "SKU数"])
mid_sku       = int(df_sku.loc["中滞销风险", "SKU数"])
high_sku      = int(df_sku.loc["高滞销风险", "SKU数"])

low_sku_diff  = int(df_sku.loc["低滞销风险", "SKU_diff"])
mid_sku_diff  = int(df_sku.loc["中滞销风险", "SKU_diff"])
high_sku_diff = int(df_sku.loc["高滞销风险", "SKU_diff"])

unsold_sku    = low_sku + mid_sku + high_sku
unsold_sku_prev = (df_sku.loc["低滞销风险","SKU_prev"]
                   + df_sku.loc["中滞销风险","SKU_prev"]
                   + df_sku.loc["高滞销风险","SKU_prev"])
unsold_sku_diff = unsold_sku - unsold_sku_prev

# 取各等级金额、数量
low_amt    = df_all[df_all["风险等级"]=="低滞销风险"]["滞销金额"].iloc[0]
mid_amt    = df_all[df_all["风险等级"]=="中滞销风险"]["滞销金额"].iloc[0]
high_amt   = df_all[df_all["风险等级"]=="高滞销风险"]["滞销金额"].iloc[0]

low_amt_diff  = df_all[df_all["风险等级"]=="低滞销风险"]["unsale_amt_diff"].iloc[0]
mid_amt_diff  = df_all[df_all["风险等级"]=="中滞销风险"]["unsale_amt_diff"].iloc[0]
high_amt_diff = df_all[df_all["风险等级"]=="高滞销风险"]["unsale_amt_diff"].iloc[0]

low_stk    = df_all[df_all["风险等级"]=="低滞销风险"]["滞销库存"].iloc[0]
mid_stk    = df_all[df_all["风险等级"]=="中滞销风险"]["滞销库存"].iloc[0]
high_stk   = df_all[df_all["风险等级"]=="高滞销风险"]["滞销库存"].iloc[0]

low_stk_diff  = df_all[df_all["风险等级"]=="低滞销风险"]["unsale_stock_diff"].iloc[0]
mid_stk_diff  = df_all[df_all["风险等级"]=="中滞销风险"]["unsale_stock_diff"].iloc[0]
high_stk_diff = df_all[df_all["风险等级"]=="高滞销风险"]["unsale_stock_diff"].iloc[0]

# 格式化颜色函数
def fmt_val(val):
    if val > 0:
        return f'<span style="color:#d32f2f">↑ +{val:,.0f}</span>'
    elif val < 0:
        return f'<span style="color:#388e3c">↓ {val:,.0f}</span>'
    else:
        return f'<span style="color:#666">持平</span>'

# 3. 1行3列布局
col1, col2, col3 = st.columns(3)

# ---------------------- 第1列：滞销金额结构 ----------------------
with col1:
    st.markdown("#### 💰 滞销金额结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总库存金额：<b>{total_amt:,.0f}</b> 元 {fmt_val(amt_diff_total)}<br>
• 滞销总金额：<b>{total_unsold_amt:,.0f}</b> 元（占总 {total_unsold_amt/total_amt:.1%}）{fmt_val(unsale_amt_diff_total)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_amt:,.0f}</b> 元，占滞销 <b>{high_amt/total_unsold_amt:.1%}</b> {fmt_val(high_amt_diff)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_amt:,.0f}</b> 元，占滞销 <b>{mid_amt/total_unsold_amt:.1%}</b> {fmt_val(mid_amt_diff)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_amt:,.0f}</b> 元，占滞销 <b>{low_amt/total_unsold_amt:.1%}</b> {fmt_val(low_amt_diff)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

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
    fig1.update_layout(height=400, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig1, use_container_width=True)

# ---------------------- 第2列：滞销数量结构 ----------------------
with col2:
    st.markdown("#### 📦 滞销数量结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总库存数量：<b>{total_stock:,.0f}</b> 件 {fmt_val(stock_diff_total)}<br>
• 滞销总数量：<b>{total_unsold_stock:,.0f}</b> 件（占总 {total_unsold_stock/total_stock:.1%}）{fmt_val(unsale_stock_diff_total)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_stk:,.0f}</b> 件，占滞销 <b>{high_stk/total_unsold_stock:.1%}</b> {fmt_val(high_stk_diff)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_stk:,.0f}</b> 件，占滞销 <b>{mid_stk/total_unsold_stock:.1%}</b> {fmt_val(mid_stk_diff)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_stk:,.0f}</b> 件，占滞销 <b>{low_stk/total_unsold_stock:.1%}</b> {fmt_val(low_stk_diff)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

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
    fig3.update_layout(height=400, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig3, use_container_width=True)

# ---------------------- 第3列：滞销SKU结构 ----------------------
with col3:
    st.markdown("#### 📊 滞销SKU结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总SKU数量：<b>{total_sku}</b> 个 {fmt_val(total_sku_diff)}<br>
• 滞销SKU总数：<b>{unsold_sku}</b> 个（占总 {unsold_sku/total_sku:.1%}）{fmt_val(unsold_sku_diff)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_sku}</b> 个，占滞销 <b>{high_sku/unsold_sku:.1%}</b> {fmt_val(high_sku_diff)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_sku}</b> 个，占滞销 <b>{mid_sku/unsold_sku:.1%}</b> {fmt_val(mid_sku_diff)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_sku}</b> 个，占滞销 <b>{low_sku/unsold_sku:.1%}</b> {fmt_val(low_sku_diff)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

    fig_sku = go.Figure()
    fig_sku.add_trace(go.Pie(
        labels=["不滞销SKU", "滞销SKU"],
        values=[healthy_sku, unsold_sku],
        domain=dict(x=[0, 0.65], y=[0, 1]),
        marker=dict(colors=["#e8f5e9", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig_sku.add_trace(go.Pie(
        labels=["低滞销风险", "中滞销风险", "高滞销风险"],
        values=[low_sku, mid_sku, high_sku],
        domain=dict(x=[0.72, 1], y=[0.2, 0.8]),
        marker=dict(colors=["#fff8e1", "#ffebee", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig_sku.update_layout(height=400, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_sku, use_container_width=True)

# ===================== 年份品 / 非年份品 滞销拆分占比分析（每一项都加环比版） =====================
st.divider()
st.subheader("📅 年份品 & 非年份品 滞销结构拆分")

# 1. 按【是否年份】拆分数据
df_year_curr = df_curr[df_curr["是否年份"] == "是"].copy()
df_noyear_curr = df_curr[df_curr["是否年份"] == "否"].copy()

df_year_prev = df_prev[df_prev["是否年份"] == "是"].copy()
df_noyear_prev = df_prev[df_prev["是否年份"] == "否"].copy()

# 滞销风险范围：低/中/高
risk_unsale = ["低滞销风险", "中滞销风险", "高滞销风险"]

# 2. 封装统计函数
def get_unsold_stat(df):
    df_unsale = df[df["滞销风险等级"].isin(risk_unsale)]
    sku_cnt = df_unsale["MSKU"].nunique()
    qty_cnt = df_unsale["总滞销库存"].sum()
    amt_cnt = df_unsale["总滞销金额"].sum()
    return sku_cnt, qty_cnt, amt_cnt

# 3. 当月统计
year_sku, year_qty, year_amt = get_unsold_stat(df_year_curr)
noyear_sku, noyear_qty, noyear_amt = get_unsold_stat(df_noyear_curr)

# 上月统计（环比用）
year_sku_p, year_qty_p, year_amt_p = get_unsold_stat(df_year_prev)
noyear_sku_p, noyear_qty_p, noyear_amt_p = get_unsold_stat(df_noyear_prev)

# 4. 总计
total_all_sku = year_sku + noyear_sku
total_all_qty = year_qty + noyear_qty
total_all_amt = year_amt + noyear_amt

total_all_sku_p = year_sku_p + noyear_sku_p
total_all_qty_p = year_qty_p + noyear_qty_p
total_all_amt_p = year_amt_p + noyear_amt_p

# 环比差值
diff_sku_total = total_all_sku - total_all_sku_p
diff_qty_total = total_all_qty - total_all_qty_p
diff_amt_total = total_all_amt - total_all_amt_p

diff_sku_year = year_sku - year_sku_p
diff_qty_year = year_qty - year_qty_p
diff_amt_year = year_amt - year_amt_p

diff_sku_noyear = noyear_sku - noyear_sku_p
diff_qty_noyear = noyear_qty - noyear_qty_p
diff_amt_noyear = noyear_amt - noyear_amt_p

# 格式化工具
def safe_pct_2(val, total):
    return f"{(val / total)*100:.2f}%" if total > 0 else "0.00%"

def color_num(v):
    if v > 0:
        return f'<span style="color:#d32f2f">↑ +{int(v):,}</span>'
    elif v < 0:
        return f'<span style="color:#388e3c">↓ {int(v):,}</span>'
    else:
        return "—"

# ===================== 布局：文字收紧 + 饼图放大 + 每一项都加环比 =====================
col_left, col_right = st.columns([1, 1.5], gap="small")

with col_left:
    st.markdown(f"""
<div style="background:#f8f9fa; padding:12px; border-radius:8px; line-height:1.6; font-size:13px;">
<b>📊 整体滞销结构总结</b><br>
• 滞销SKU共 <b>{total_all_sku}</b> 个，环比 {color_num(diff_sku_total)}<br>
　年份品 <b>{year_sku}</b> 个（{safe_pct_2(year_sku, total_all_sku)}），环比 {color_num(diff_sku_year)}<br>
　非年份品 <b>{noyear_sku}</b> 个（{safe_pct_2(noyear_sku, total_all_sku)}），环比 {color_num(diff_sku_noyear)}<br>
<br>
• 滞销数量共 <b>{total_all_qty:,.0f}</b> 件，环比 {color_num(diff_qty_total)}<br>
　年份品 <b>{year_qty:,.0f}</b> 件（{safe_pct_2(year_qty, total_all_qty)}），环比 {color_num(diff_qty_year)}<br>
　非年份品 <b>{noyear_qty:,.0f}</b> 件（{safe_pct_2(noyear_qty, total_all_qty)}），环比 {color_num(diff_qty_noyear)}<br>
<br>
• 滞销金额共 <b>{total_all_amt:,.0f}</b> 元，环比 {color_num(diff_amt_total)}<br>
　年份品 <b>{year_amt:,.0f}</b> 元（{safe_pct_2(year_amt, total_all_amt)}），环比 {color_num(diff_amt_year)}<br>
　非年份品 <b>{noyear_amt:,.0f}</b> 元（{safe_pct_2(noyear_amt, total_all_amt)}），环比 {color_num(diff_amt_noyear)}
</div>
""", unsafe_allow_html=True)

with col_right:
    c1, c2, c3 = st.columns(3, gap="small")

    # 左1：SKU占比
    with c1:
        pie_sku = pd.DataFrame({
            "类型": ["年份品", "非年份品"],
            "值": [year_sku, noyear_sku]
        })
        fig = px.pie(pie_sku, names="类型", values="值", title="滞销SKU占比")
        fig.update_layout(height=280, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    # 左2：数量占比
    with c2:
        pie_qty = pd.DataFrame({
            "类型": ["年份品", "非年份品"],
            "值": [year_qty, noyear_qty]
        })
        fig = px.pie(pie_qty, names="类型", values="值", title="滞销数量占比")
        fig.update_layout(height=280, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

    # 左3：金额占比
    with c3:
        pie_amt = pd.DataFrame({
            "类型": ["年份品", "非年份品"],
            "值": [year_amt, noyear_amt]
        })
        fig = px.pie(pie_amt, names="类型", values="值", title="滞销金额占比")
        fig.update_layout(height=280, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

# ======================================================================================
# 👇 下面是你要的：非年份品 滞销拆解分析（和你上面原版完全同结构）
# ======================================================================================
st.divider()
st.subheader("📦 非年份品 滞销金额 & 数量 & SKU 拆解分析")

df_no_year_curr = df_curr[df_curr["是否年份"] == "否"].copy()
df_no_year_prev = df_prev[df_prev["是否年份"] == "否"].copy()

# 1. 统一计算所有等级数据
risk_list = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]
data_list_no = []
for r in risk_list:
    m = calc_metrics(df_no_year_curr, df_no_year_prev, r)
    data_list_no.append({
        "风险等级": r,
        "SKU数": m["sku_curr"],
        "SKU_prev": m["sku_prev"],
        "SKU_diff": m["sku_diff"],
        "总金额": m["amt_curr"],
        "amt_prev": m["amt_prev"],
        "amt_diff": m["amt_diff"],
        "总库存": m["stock_curr"],
        "stock_prev": m["stock_prev"],
        "stock_diff": m["stock_diff"],
        "滞销金额": m["unsale_amt_curr"],
        "unsale_amt_prev": m["unsale_amt_prev"],
        "unsale_amt_diff": m["unsale_amt_diff"],
        "滞销库存": m["unsale_stock_curr"],
        "unsale_stock_prev": m["unsale_stock_prev"],
        "unsale_stock_diff": m["unsale_stock_diff"],
    })
df_all_no = pd.DataFrame(data_list_no)

# 2. 整体指标
total_amt_no = df_all_no["总金额"].sum()
total_unsold_amt_no = df_all_no[df_all_no["风险等级"] != "健康"]["滞销金额"].sum()
total_not_unsold_amt_no = total_amt_no - total_unsold_amt_no
amt_diff_total_no = total_amt_no - df_all_no["amt_prev"].sum()
unsale_amt_diff_total_no = total_unsold_amt_no - df_all_no["unsale_amt_prev"].sum()

total_stock_no = df_all_no["总库存"].sum()
total_unsold_stock_no = df_all_no[df_all_no["风险等级"] != "健康"]["滞销库存"].sum()
total_not_unsold_stock_no = total_stock_no - total_unsold_stock_no
stock_diff_total_no = total_stock_no - df_all_no["stock_prev"].sum()
unsale_stock_diff_total_no = total_unsold_stock_no - df_all_no["unsale_stock_prev"].sum()

# 3. SKU 统计
df_sku_no = df_all_no.set_index("风险等级")
total_sku_no = int(df_sku_no["SKU数"].sum())
total_sku_prev_no = int(df_sku_no["SKU_prev"].sum())
total_sku_diff_no = total_sku_no - total_sku_prev_no

healthy_sku_no = int(df_sku_no.loc["健康", "SKU数"])
low_sku_no = int(df_sku_no.loc["低滞销风险", "SKU数"])
mid_sku_no = int(df_sku_no.loc["中滞销风险", "SKU数"])
high_sku_no = int(df_sku_no.loc["高滞销风险", "SKU数"])

low_sku_diff_no = int(df_sku_no.loc["低滞销风险", "SKU_diff"])
mid_sku_diff_no = int(df_sku_no.loc["中滞销风险", "SKU_diff"])
high_sku_diff_no = int(df_sku_no.loc["高滞销风险", "SKU_diff"])

unsold_sku_no = low_sku_no + mid_sku_no + high_sku_no
unsold_sku_prev_no = (df_sku_no.loc["低滞销风险","SKU_prev"] + df_sku_no.loc["中滞销风险","SKU_prev"] + df_sku_no.loc["高滞销风险","SKU_prev"])
unsold_sku_diff_no = unsold_sku_no - unsold_sku_prev_no

# 取各等级金额、数量
low_amt_no = df_all_no[df_all_no["风险等级"]=="低滞销风险"]["滞销金额"].iloc[0]
mid_amt_no = df_all_no[df_all_no["风险等级"]=="中滞销风险"]["滞销金额"].iloc[0]
high_amt_no = df_all_no[df_all_no["风险等级"]=="高滞销风险"]["滞销金额"].iloc[0]

low_amt_diff_no = df_all_no[df_all_no["风险等级"]=="低滞销风险"]["unsale_amt_diff"].iloc[0]
mid_amt_diff_no = df_all_no[df_all_no["风险等级"]=="中滞销风险"]["unsale_amt_diff"].iloc[0]
high_amt_diff_no = df_all_no[df_all_no["风险等级"]=="高滞销风险"]["unsale_amt_diff"].iloc[0]

low_stk_no = df_all_no[df_all_no["风险等级"]=="低滞销风险"]["滞销库存"].iloc[0]
mid_stk_no = df_all_no[df_all_no["风险等级"]=="中滞销风险"]["滞销库存"].iloc[0]
high_stk_no = df_all_no[df_all_no["风险等级"]=="高滞销风险"]["滞销库存"].iloc[0]

low_stk_diff_no = df_all_no[df_all_no["风险等级"]=="低滞销风险"]["unsale_stock_diff"].iloc[0]
mid_stk_diff_no = df_all_no[df_all_no["风险等级"]=="中滞销风险"]["unsale_stock_diff"].iloc[0]
high_stk_diff_no = df_all_no[df_all_no["风险等级"]=="高滞销风险"]["unsale_stock_diff"].iloc[0]

# 布局
col1_no, col2_no, col3_no = st.columns(3)

# 金额
with col1_no:
    st.markdown("#### 💰 非年份品｜滞销金额结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总库存金额：<b>{total_amt_no:,.0f}</b> 元 {fmt_val(amt_diff_total_no)}<br>
• 滞销总金额：<b>{total_unsold_amt_no:,.0f}</b> 元（占总 {total_unsold_amt_no/total_amt_no:.1%}）{fmt_val(unsale_amt_diff_total_no)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_amt_no:,.0f}</b> 元，占滞销 <b>{high_amt_no/total_unsold_amt_no:.1%}</b> {fmt_val(high_amt_diff_no)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_amt_no:,.0f}</b> 元，占滞销 <b>{mid_amt_no/total_unsold_amt_no:.1%}</b> {fmt_val(mid_amt_diff_no)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_amt_no:,.0f}</b> 元，占滞销 <b>{low_amt_no/total_unsold_amt_no:.1%}</b> {fmt_val(low_amt_diff_no)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=["不滞销金额","滞销金额"], values=[total_not_unsold_amt_no, total_unsold_amt_no], domain=dict(x=[0,0.65],y=[0,1]), marker=dict(colors=["#e8f5e9","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.add_trace(go.Pie(labels=["低","中","高"], values=[low_amt_no,mid_amt_no,high_amt_no], domain=dict(x=[0.72,1],y=[0.2,0.8]), marker=dict(colors=["#fff8e1","#ffebee","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20,b=20,l=20,r=20))
    st.plotly_chart(fig, use_container_width=True)

# 数量
with col2_no:
    st.markdown("#### 📦 非年份品｜滞销数量结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总库存数量：<b>{total_stock_no:,.0f}</b> 件 {fmt_val(stock_diff_total_no)}<br>
• 滞销总数量：<b>{total_unsold_stock_no:,.0f}</b> 件（占总 {total_unsold_stock_no/total_stock_no:.1%}）{fmt_val(unsale_stock_diff_total_no)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_stk_no:,.0f}</b> 件，占滞销 <b>{high_stk_no/total_unsold_stock_no:.1%}</b> {fmt_val(high_stk_diff_no)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_stk_no:,.0f}</b> 件，占滞销 <b>{mid_stk_no/total_unsold_stock_no:.1%}</b> {fmt_val(mid_stk_diff_no)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_stk_no:,.0f}</b> 件，占滞销 <b>{low_stk_no/total_unsold_stock_no:.1%}</b> {fmt_val(low_stk_diff_no)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=["不滞销数量","滞销数量"], values=[total_not_unsold_stock_no, total_unsold_stock_no], domain=dict(x=[0,0.65],y=[0,1]), marker=dict(colors=["#e8f5e9","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.add_trace(go.Pie(labels=["低","中","高"], values=[low_stk_no,mid_stk_no,high_stk_no], domain=dict(x=[0.72,1],y=[0.2,0.8]), marker=dict(colors=["#fff8e1","#ffebee","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20,b=20,l=20,r=20))
    st.plotly_chart(fig, use_container_width=True)

# SKU
with col3_no:
    st.markdown("#### 📊 非年份品｜滞销SKU结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总SKU数量：<b>{total_sku_no}</b> 个 {fmt_val(total_sku_diff_no)}<br>
• 滞销SKU总数：<b>{unsold_sku_no}</b> 个（占总 {unsold_sku_no/total_sku_no:.1%}）{fmt_val(unsold_sku_diff_no)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_sku_no}</b> 个，占滞销 <b>{high_sku_no/unsold_sku_no:.1%}</b> {fmt_val(high_sku_diff_no)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_sku_no}</b> 个，占滞销 <b>{mid_sku_no/unsold_sku_no:.1%}</b> {fmt_val(mid_sku_diff_no)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_sku_no}</b> 个，占滞销 <b>{low_sku_no/unsold_sku_no:.1%}</b> {fmt_val(low_sku_diff_no)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=["不滞销SKU","滞销SKU"], values=[healthy_sku_no, unsold_sku_no], domain=dict(x=[0,0.65],y=[0,1]), marker=dict(colors=["#e8f5e9","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value}<br>%{percent:.1%}", sort=False))
    fig.add_trace(go.Pie(labels=["低","中","高"], values=[low_sku_no,mid_sku_no,high_sku_no], domain=dict(x=[0.72,1],y=[0.2,0.8]), marker=dict(colors=["#fff8e1","#ffebee","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value}<br>%{percent:.1%}", sort=False))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20,b=20,l=20,r=20))
    st.plotly_chart(fig, use_container_width=True)


# ======================================================================================
# 👇 接下来：年份品 滞销拆解分析（结构完全一样）
# ======================================================================================
st.divider()
st.subheader("📅 年份品 滞销金额 & 数量 & SKU 拆解分析")

df_year_curr = df_curr[df_curr["是否年份"] == "是"].copy()
df_year_prev = df_prev[df_prev["是否年份"] == "是"].copy()

risk_list = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]
data_list_yr = []
for r in risk_list:
    m = calc_metrics(df_year_curr, df_year_prev, r)
    data_list_yr.append({
        "风险等级": r,
        "SKU数": m["sku_curr"],
        "SKU_prev": m["sku_prev"],
        "SKU_diff": m["sku_diff"],
        "总金额": m["amt_curr"],
        "amt_prev": m["amt_prev"],
        "amt_diff": m["amt_diff"],
        "总库存": m["stock_curr"],
        "stock_prev": m["stock_prev"],
        "stock_diff": m["stock_diff"],
        "滞销金额": m["unsale_amt_curr"],
        "unsale_amt_prev": m["unsale_amt_prev"],
        "unsale_amt_diff": m["unsale_amt_diff"],
        "滞销库存": m["unsale_stock_curr"],
        "unsale_stock_prev": m["unsale_stock_prev"],
        "unsale_stock_diff": m["unsale_stock_diff"],
    })
df_all_yr = pd.DataFrame(data_list_yr)

# 指标
total_amt_yr = df_all_yr["总金额"].sum()
total_unsold_amt_yr = df_all_yr[df_all_yr["风险等级"] != "健康"]["滞销金额"].sum()
total_not_unsold_amt_yr = total_amt_yr - total_unsold_amt_yr
amt_diff_total_yr = total_amt_yr - df_all_yr["amt_prev"].sum()
unsale_amt_diff_total_yr = total_unsold_amt_yr - df_all_yr["unsale_amt_prev"].sum()

total_stock_yr = df_all_yr["总库存"].sum()
total_unsold_stock_yr = df_all_yr[df_all_yr["风险等级"] != "健康"]["滞销库存"].sum()
total_not_unsold_stock_yr = total_stock_yr - total_unsold_stock_yr
stock_diff_total_yr = total_stock_yr - df_all_yr["stock_prev"].sum()
unsale_stock_diff_total_yr = total_unsold_stock_yr - df_all_yr["unsale_stock_prev"].sum()

# SKU
df_sku_yr = df_all_yr.set_index("风险等级")
total_sku_yr = int(df_sku_yr["SKU数"].sum())
total_sku_prev_yr = int(df_sku_yr["SKU_prev"].sum())
total_sku_diff_yr = total_sku_yr - total_sku_prev_yr

healthy_sku_yr = int(df_sku_yr.loc["健康", "SKU数"])
low_sku_yr = int(df_sku_yr.loc["低滞销风险", "SKU数"])
mid_sku_yr = int(df_sku_yr.loc["中滞销风险", "SKU数"])
high_sku_yr = int(df_sku_yr.loc["高滞销风险", "SKU数"])

low_sku_diff_yr = int(df_sku_yr.loc["低滞销风险", "SKU_diff"])
mid_sku_diff_yr = int(df_sku_yr.loc["中滞销风险", "SKU_diff"])
high_sku_diff_yr = int(df_sku_yr.loc["高滞销风险", "SKU_diff"])

unsold_sku_yr = low_sku_yr + mid_sku_yr + high_sku_yr
unsold_sku_prev_yr = (df_sku_yr.loc["低滞销风险","SKU_prev"] + df_sku_yr.loc["中滞销风险","SKU_prev"] + df_sku_yr.loc["高滞销风险","SKU_prev"])
unsold_sku_diff_yr = unsold_sku_yr - unsold_sku_prev_yr

# 金额/数量
low_amt_yr = df_all_yr[df_all_yr["风险等级"]=="低滞销风险"]["滞销金额"].iloc[0]
mid_amt_yr = df_all_yr[df_all_yr["风险等级"]=="中滞销风险"]["滞销金额"].iloc[0]
high_amt_yr = df_all_yr[df_all_yr["风险等级"]=="高滞销风险"]["滞销金额"].iloc[0]

low_amt_diff_yr = df_all_yr[df_all_yr["风险等级"]=="低滞销风险"]["unsale_amt_diff"].iloc[0]
mid_amt_diff_yr = df_all_yr[df_all_yr["风险等级"]=="中滞销风险"]["unsale_amt_diff"].iloc[0]
high_amt_diff_yr = df_all_yr[df_all_yr["风险等级"]=="高滞销风险"]["unsale_amt_diff"].iloc[0]

low_stk_yr = df_all_yr[df_all_yr["风险等级"]=="低滞销风险"]["滞销库存"].iloc[0]
mid_stk_yr = df_all_yr[df_all_yr["风险等级"]=="中滞销风险"]["滞销库存"].iloc[0]
high_stk_yr = df_all_yr[df_all_yr["风险等级"]=="高滞销风险"]["滞销库存"].iloc[0]

low_stk_diff_yr = df_all_yr[df_all_yr["风险等级"]=="低滞销风险"]["unsale_stock_diff"].iloc[0]
mid_stk_diff_yr = df_all_yr[df_all_yr["风险等级"]=="中滞销风险"]["unsale_stock_diff"].iloc[0]
high_stk_diff_yr = df_all_yr[df_all_yr["风险等级"]=="高滞销风险"]["unsale_stock_diff"].iloc[0]

# 布局
col1_yr, col2_yr, col3_yr = st.columns(3)

# 金额
with col1_yr:
    st.markdown("#### 💰 年份品｜滞销金额结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总库存金额：<b>{total_amt_yr:,.0f}</b> 元 {fmt_val(amt_diff_total_yr)}<br>
• 滞销总金额：<b>{total_unsold_amt_yr:,.0f}</b> 元（占总 {total_unsold_amt_yr/total_amt_yr:.1%}）{fmt_val(unsale_amt_diff_total_yr)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_amt_yr:,.0f}</b> 元，占滞销 <b>{high_amt_yr/total_unsold_amt_yr:.1%}</b> {fmt_val(high_amt_diff_yr)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_amt_yr:,.0f}</b> 元，占滞销 <b>{mid_amt_yr/total_unsold_amt_yr:.1%}</b> {fmt_val(mid_amt_diff_yr)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_amt_yr:,.0f}</b> 元，占滞销 <b>{low_amt_yr/total_unsold_amt_yr:.1%}</b> {fmt_val(low_amt_diff_yr)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=["不滞销金额","滞销金额"], values=[total_not_unsold_amt_yr, total_unsold_amt_yr], domain=dict(x=[0,0.65],y=[0,1]), marker=dict(colors=["#e8f5e9","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.add_trace(go.Pie(labels=["低","中","高"], values=[low_amt_yr,mid_amt_yr,high_amt_yr], domain=dict(x=[0.72,1],y=[0.2,0.8]), marker=dict(colors=["#fff8e1","#ffebee","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20,b=20,l=20,r=20))
    st.plotly_chart(fig, use_container_width=True)

# 数量
with col2_yr:
    st.markdown("#### 📦 年份品｜滞销数量结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总库存数量：<b>{total_stock_yr:,.0f}</b> 件 {fmt_val(stock_diff_total_yr)}<br>
• 滞销总数量：<b>{total_unsold_stock_yr:,.0f}</b> 件（占总 {total_unsold_stock_yr/total_stock_yr:.1%}）{fmt_val(unsale_stock_diff_total_yr)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_stk_yr:,.0f}</b> 件，占滞销 <b>{high_stk_yr/total_unsold_stock_yr:.1%}</b> {fmt_val(high_stk_diff_yr)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_stk_yr:,.0f}</b> 件，占滞销 <b>{mid_stk_yr/total_unsold_stock_yr:.1%}</b> {fmt_val(mid_stk_diff_yr)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_stk_yr:,.0f}</b> 件，占滞销 <b>{low_stk_yr/total_unsold_stock_yr:.1%}</b> {fmt_val(low_stk_diff_yr)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=["不滞销数量","滞销数量"], values=[total_not_unsold_stock_yr, total_unsold_stock_yr], domain=dict(x=[0,0.65],y=[0,1]), marker=dict(colors=["#e8f5e9","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.add_trace(go.Pie(labels=["低","中","高"], values=[low_stk_yr,mid_stk_yr,high_stk_yr], domain=dict(x=[0.72,1],y=[0.2,0.8]), marker=dict(colors=["#fff8e1","#ffebee","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}", sort=False))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20,b=20,l=20,r=20))
    st.plotly_chart(fig, use_container_width=True)

# SKU
with col3_yr:
    st.markdown("#### 📊 年份品｜滞销SKU结构")
    html = f"""
<div style="line-height:1.8;font-size:14px">
• 总SKU数量：<b>{total_sku_yr}</b> 个 {fmt_val(total_sku_diff_yr)}<br>
• 滞销SKU总数：<b>{unsold_sku_yr}</b> 个（占总 {unsold_sku_yr/total_sku_yr:.1%}）{fmt_val(unsold_sku_diff_yr)}<br>
<br>
<b>细分滞销占比：</b><br>
&nbsp;&nbsp;▸ 高滞销风险：<b>{high_sku_yr}</b> 个，占滞销 <b>{high_sku_yr/unsold_sku_yr:.1%}</b> {fmt_val(high_sku_diff_yr)}<br>
&nbsp;&nbsp;▸ 中滞销风险：<b>{mid_sku_yr}</b> 个，占滞销 <b>{mid_sku_yr/unsold_sku_yr:.1%}</b> {fmt_val(mid_sku_diff_yr)}<br>
&nbsp;&nbsp;▸ 低滞销风险：<b>{low_sku_yr}</b> 个，占滞销 <b>{low_sku_yr/unsold_sku_yr:.1%}</b> {fmt_val(low_sku_diff_yr)}
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Pie(labels=["不滞销SKU","滞销SKU"], values=[healthy_sku_yr, unsold_sku_yr], domain=dict(x=[0,0.65],y=[0,1]), marker=dict(colors=["#e8f5e9","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value}<br>%{percent:.1%}", sort=False))
    fig.add_trace(go.Pie(labels=["低","中","高"], values=[low_sku_yr,mid_sku_yr,high_sku_yr], domain=dict(x=[0.72,1],y=[0.2,0.8]), marker=dict(colors=["#fff8e1","#ffebee","#ffcdd2"]), textinfo="label+value+percent", texttemplate="%{label}<br>%{value}<br>%{percent:.1%}", sort=False))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20,b=20,l=20,r=20))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("📦 滞销库存来源分析（按采购类型）")

# ===================== 1. 基础配置 =====================
stock_date = pd.to_datetime(df_curr["时间"].iloc[0])
risk_unsale = ["低滞销风险", "中滞销风险", "高滞销风险"]
df_unsale = df_curr[df_curr["滞销风险等级"].isin(risk_unsale)].copy()

# 上月滞销数据
df_unsale_prev = df_prev[df_prev["滞销风险等级"].isin(risk_unsale)].copy()
stock_date_prev = pd.to_datetime(df_prev["时间"].iloc[0])


# ===================== 2. 采购数据：只算库存日期之前 =====================
def get_pur_before(df_pur_raw, date_limit):
    pur_clean = df_pur_raw.copy()
    pur_clean["采购日期"] = pd.to_datetime(pur_clean["采购日期"], errors="coerce")

    # 只过滤采购日期明显异常的记录（比如超过1年的未来日期）
    date_upper = date_limit + pd.DateOffset(years=1)
    pur_before = pur_clean[
        (pur_clean["采购日期"] <= date_upper) &
        (pur_clean["采购日期"].notna())
        ].copy()

    msku_pur = pur_before.pivot_table(
        index="MSKU",
        columns="采购类型",
        values="采购量",
        aggfunc="sum"
    ).fillna(0).reset_index()
    for c in ["年前采购", "年后采购", "年货采购"]:
        if c not in msku_pur.columns:
            msku_pur[c] = 0
    return msku_pur


msku_pur_curr = get_pur_before(df_pur, stock_date)
msku_pur_prev = get_pur_before(df_pur, stock_date_prev)

# ===================== 3. 【核心修复】计算全量年货前采购总库存（包含不滞销SKU） =====================
# 逻辑：用当月全量库存表（不是只滞销表），计算所有SKU的年货前采购库存
inv_full_all = df_curr.groupby("MSKU").agg(
    店铺=("店铺", "first"),
    品名=("品名", "first"),
    采购成本=("采购成本", "first"),
    头程费用=("头程费用", "first"),
    FBA_AWD_在途库存=("FBA+AWD+在途库存", "sum"),
    本地库存=("本地库存", "sum"),
    总库存=("总库存", "sum"),
    滞销总库存=("总滞销库存", "sum")
).reset_index()

# 全量表关联采购数据
df_merge_all = inv_full_all.merge(msku_pur_curr, on="MSKU", how="left").fillna(0)

# 计算全量年货前采购总库存（所有SKU，包含不滞销的）
df_merge_all["年货前采购总库存"] = (
            df_merge_all["总库存"] - df_merge_all["年货采购"] - df_merge_all["年前采购"] - df_merge_all[
        "年后采购"]).clip(lower=0)

# 单独提取滞销SKU的表，用于后面的滞销分摊计算
df_merge_curr = df_merge_all[df_merge_all["MSKU"].isin(df_unsale["MSKU"])].copy()

# 上月数据同步修复
inv_full_all_prev = df_prev.groupby("MSKU").agg(
    店铺=("店铺", "first"),
    品名=("品名", "first"),
    采购成本=("采购成本", "first"),
    头程费用=("头程费用", "first"),
    FBA_AWD_在途库存=("FBA+AWD+在途库存", "sum"),
    本地库存=("本地库存", "sum"),
    总库存=("总库存", "sum"),
    滞销总库存=("总滞销库存", "sum")
).reset_index()
df_merge_all_prev = inv_full_all_prev.merge(msku_pur_prev, on="MSKU", how="left").fillna(0)
df_merge_all_prev["年货前采购总库存"] = (
            df_merge_all_prev["总库存"] - df_merge_all_prev["年货采购"] - df_merge_all_prev["年前采购"] -
            df_merge_all_prev["年后采购"]).clip(lower=0)
df_merge_prev = df_merge_all_prev[df_merge_all_prev["MSKU"].isin(df_unsale_prev["MSKU"])].copy()


# ===================== 4. 第一步：按年后→年前→年货→年货前 分摊滞销数量 =====================
def alloc_qty_by_purchase(row):
    unsale = row["滞销总库存"]
    after = row["年后采购"]
    before = row["年前采购"]
    goods = row["年货采购"]

    # 年后
    a = min(unsale, after)
    unsale -= a
    # 年前
    b = min(unsale, before)
    unsale -= b
    # 年货
    c = min(unsale, goods)
    unsale -= c
    # 年货前兜底
    d = unsale
    return pd.Series([d, c, b, a])


# 当月4类滞销数量
df_merge_curr[["年货前采购滞销数量", "年货采购滞销数量", "年前采购滞销数量", "年后采购滞销数量"]] = \
    df_merge_curr.apply(alloc_qty_by_purchase, axis=1)

# 上月4类滞销数量
df_merge_prev[["年货前采购滞销数量", "年货采购滞销数量", "年前采购滞销数量", "年后采购滞销数量"]] = \
    df_merge_prev.apply(alloc_qty_by_purchase, axis=1)


# ===================== 5. 第二步：按【本地先扣、剩余走FBA】计算每类滞销金额 =====================
def calc_amt_by_local_fba(row):
    local_total = row["本地库存"]
    fba_total = row["FBA_AWD_在途库存"]
    cost = row["采购成本"]
    freight = row["头程费用"]
    # 四类滞销数量
    qty_pre_year = row["年货前采购滞销数量"]
    qty_goods = row["年货采购滞销数量"]
    qty_before = row["年前采购滞销数量"]
    qty_after = row["年后采购滞销数量"]

    remain_local = local_total

    def calc_single_amt(qty):
        nonlocal remain_local
        if qty <= 0:
            return 0
        # 先走本地
        use_local = min(qty, remain_local)
        use_fba = qty - use_local
        remain_local -= use_local
        amt = use_local * cost + use_fba * (cost + freight)
        return round(amt, 2)

    amt_after = calc_single_amt(qty_after)
    amt_before = calc_single_amt(qty_before)
    amt_goods = calc_single_amt(qty_goods)
    amt_pre_year = calc_single_amt(qty_pre_year)

    return pd.Series([amt_pre_year, amt_goods, amt_before, amt_after])


# 当月金额
df_merge_curr[["年货前采购滞销金额", "年货采购滞销金额", "年前采购滞销金额", "年后采购滞销金额"]] = \
    df_merge_curr.apply(calc_amt_by_local_fba, axis=1)

# 上月金额
df_merge_prev[["年货前采购滞销金额", "年货采购滞销金额", "年前采购滞销金额", "年后采购滞销金额"]] = \
    df_merge_prev.apply(calc_amt_by_local_fba, axis=1)


# ===================== 6. 汇总当月/上月 数量&金额 =====================
def sum_all_data(df):
    return {
        "pre_qty": int(df["年货前采购滞销数量"].sum()),
        "goods_qty": int(df["年货采购滞销数量"].sum()),
        "before_qty": int(df["年前采购滞销数量"].sum()),
        "after_qty": int(df["年后采购滞销数量"].sum()),
        "pre_amt": round(df["年货前采购滞销金额"].sum(), 2),
        "goods_amt": round(df["年货采购滞销金额"].sum(), 2),
        "before_amt": round(df["年前采购滞销金额"].sum(), 2),
        "after_amt": round(df["年后采购滞销金额"].sum(), 2),
    }


curr_sum = sum_all_data(df_merge_curr)
prev_sum = sum_all_data(df_merge_prev)

# 【核心修复】全量年货前采购总库存 = 所有SKU（含不滞销）的年货前采购库存之和
total_pre_all_stock = int(df_merge_all["年货前采购总库存"].sum())

# 总滞销
total_curr_qty = curr_sum["pre_qty"] + curr_sum["goods_qty"] + curr_sum["before_qty"] + curr_sum["after_qty"]
total_prev_qty = prev_sum["pre_qty"] + prev_sum["goods_qty"] + prev_sum["before_qty"] + prev_sum["after_qty"]
total_curr_amt = curr_sum["pre_amt"] + curr_sum["goods_amt"] + curr_sum["before_amt"] + curr_sum["after_amt"]
total_prev_amt = prev_sum["pre_amt"] + prev_sum["goods_amt"] + prev_sum["before_amt"] + prev_sum["after_amt"]

# 采购总量
total_pur_year = msku_pur_curr["年货采购"].sum()
total_pur_before = msku_pur_curr["年前采购"].sum()
total_pur_after = msku_pur_curr["年后采购"].sum()


# 占比
def safe_pct(val, total):
    return val / total * 100 if total else 0


pct_pre = safe_pct(curr_sum["pre_qty"], total_curr_qty)
pct_goods = safe_pct(curr_sum["goods_qty"], total_curr_qty)
pct_before = safe_pct(curr_sum["before_qty"], total_curr_qty)
pct_after = safe_pct(curr_sum["after_qty"], total_curr_qty)

# 滞销占采购量比例
pct_of_pur_pre = safe_pct(curr_sum["pre_qty"], total_pre_all_stock)
pct_of_pur_goods = safe_pct(curr_sum["goods_qty"], total_pur_year)
pct_of_pur_before = safe_pct(curr_sum["before_qty"], total_pur_before)
pct_of_pur_after = safe_pct(curr_sum["after_qty"], total_pur_after)


# ===================== 7. 环比格式化 =====================
def fmt_num_curr(curr, prev):
    diff = curr - prev
    if diff > 0:
        return f"{curr:,}", f'<span style="color:#d32f2f">↑ +{diff:,}</span>'
    elif diff < 0:
        return f"{curr:,}", f'<span style="color:#388e3c">↓ {diff:,}</span>'
    else:
        return f"{curr:,}", '<span style="color:#666">持平</span>'


def fmt_amt_curr(curr, prev):
    diff = curr - prev
    if diff > 0:
        return f"{curr:,.2f}", f'<span style="color:#d32f2f">↑ +{diff:,.2f}</span>'
    elif diff < 0:
        return f"{curr:,.2f}", f'<span style="color:#388e3c">↓ {diff:,.2f}</span>'
    else:
        return f"{curr:,.2f}", '<span style="color:#666">持平</span>'


# ===================== 8. 四张卡片 =====================
c1, c2, c3, c4 = st.columns(4)

# 1.年货前（已修复：总库存包含不滞销SKU）
qty_str1, qty_fluc1 = fmt_num_curr(curr_sum["pre_qty"], prev_sum["pre_qty"])
amt_str1, amt_fluc1 = fmt_amt_curr(curr_sum["pre_amt"], prev_sum["pre_amt"])
with c1:
    st.markdown(f"""
    <div style="background:#f3f4f6; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#444;">⏳ 年货前采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str1} 件 {qty_fluc1}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str1} 元 {amt_fluc1}</div>
        <div style="font-size:14px;color:#666;">年货前采购总库存：{total_pre_all_stock:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_pre:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_pre:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 2.年货
qty_str2, qty_fluc2 = fmt_num_curr(curr_sum["goods_qty"], prev_sum["goods_qty"])
amt_str2, amt_fluc2 = fmt_amt_curr(curr_sum["goods_amt"], prev_sum["goods_amt"])
with c2:
    st.markdown(f"""
    <div style="background:#fff9e6; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#e65100;">🧧 年货采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str2} 件 {qty_fluc2}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str2} 元 {amt_fluc2}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_year:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_goods:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_goods:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 3.年前
qty_str3, qty_fluc3 = fmt_num_curr(curr_sum["before_qty"], prev_sum["before_qty"])
amt_str3, amt_fluc3 = fmt_amt_curr(curr_sum["before_amt"], prev_sum["before_amt"])
with c3:
    st.markdown(f"""
    <div style="background:#ffebee; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#c62828;">🧨 年前采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str3} 件 {qty_fluc3}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str3} 元 {amt_fluc3}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_before:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_before:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_before:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 4.年后
qty_str4, qty_fluc4 = fmt_num_curr(curr_sum["after_qty"], prev_sum["after_qty"])
amt_str4, amt_fluc4 = fmt_amt_curr(curr_sum["after_amt"], prev_sum["after_amt"])
with c4:
    st.markdown(f"""
    <div style="background:#e3f2fd; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#1565c0;">🧊 年后采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str4} 件 {qty_fluc4}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str4} 元 {amt_fluc4}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_after:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_after:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_after:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# ===================== 9. 明细表格 =====================
with st.expander("📄 查看 MSKU 滞销来源明细（数量+金额+本地/FBA口径）"):
    show_cols = [
        "MSKU", "店铺", "品名",
        "总库存", "采购成本","头程费用","年货前采购总库存",
        "本地库存", "FBA_AWD_在途库存", "滞销总库存",
        "年货采购", "年前采购", "年后采购",
        "年货前采购滞销数量", "年货采购滞销数量", "年前采购滞销数量", "年后采购滞销数量",
        "年货前采购滞销金额", "年货采购滞销金额", "年前采购滞销金额", "年后采购滞销金额"
    ]
    st.dataframe(
        df_merge_curr[show_cols].sort_values("滞销总库存", ascending=False),
        use_container_width=True, height=600
    )

# ===================== 【最终格式化版】一行8列 · 滞销结构分析（年份品/非年份品） =====================
st.divider()
st.subheader("🍰 滞销结构分析（年份品 / 非年份品）")

# 1. 从 df_prod 匹配【是否年份】字段
df_temp = df_merge_curr.merge(
    df_prod[["MSKU", "是否年份"]],
    on="MSKU",
    how="left"
).fillna("否")

df_temp["商品类型"] = df_temp["是否年份"].apply(
    lambda x: "年份品" if str(x).strip() == "是" else "非年份品"
)

# 上月数据同步打标签，用于环比计算
df_temp_prev = df_merge_prev.merge(
    df_prod[["MSKU", "是否年份"]],
    on="MSKU",
    how="left"
).fillna("否")
df_temp_prev["商品类型"] = df_temp_prev["是否年份"].apply(
    lambda x: "年份品" if str(x).strip() == "是" else "非年份品"
)


# 2. 按4类滞销 + 商品类型 汇总（当月+上月）
def get_type_summary(df_curr, df_prev, col_qty, col_amt):
    # 当月汇总
    sum_curr = df_curr.groupby("商品类型").agg(
        滞销数量=(col_qty, "sum"),
        滞销金额=(col_amt, "sum")
    ).fillna(0)
    # 上月汇总
    sum_prev = df_prev.groupby("商品类型").agg(
        滞销数量=(col_qty, "sum"),
        滞销金额=(col_amt, "sum")
    ).fillna(0)
    # 全量合计
    total_qty = sum_curr["滞销数量"].sum()
    total_amt = sum_curr["滞销金额"].sum()
    prev_total_qty = sum_prev["滞销数量"].sum()
    prev_total_amt = sum_prev["滞销金额"].sum()
    return sum_curr, sum_prev, total_qty, total_amt, prev_total_qty, prev_total_amt


# 4类数据汇总
sum_pre, sum_pre_prev, total_pre_qty, total_pre_amt, prev_pre_qty, prev_pre_amt = get_type_summary(
    df_temp, df_temp_prev, "年货前采购滞销数量", "年货前采购滞销金额"
)
sum_goods, sum_goods_prev, total_goods_qty, total_goods_amt, prev_goods_qty, prev_goods_amt = get_type_summary(
    df_temp, df_temp_prev, "年货采购滞销数量", "年货采购滞销金额"
)
sum_before, sum_before_prev, total_before_qty, total_before_amt, prev_before_qty, prev_before_amt = get_type_summary(
    df_temp, df_temp_prev, "年前采购滞销数量", "年前采购滞销金额"
)
sum_after, sum_after_prev, total_after_qty, total_after_amt, prev_after_qty, prev_after_amt = get_type_summary(
    df_temp, df_temp_prev, "年后采购滞销数量", "年后采购滞销金额"
)

# 3. 饼图绘图函数（适配一行8列的小尺寸）
import plotly.express as px


def pie_chart(df, title):
    labels = df.index.tolist()
    colors = ["#ff9999", "#66b3ff"]

    fig = px.pie(names=labels, values=df["滞销数量"],
                 color_discrete_sequence=colors)
    fig.update_traces(textposition="inside", textinfo="percent", showlegend=False)
    fig.update_layout(
        height=160,
        margin=dict(l=5, r=5, t=30, b=5),
        title=dict(text=title, font=dict(size=11)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig


# 4. 【核心优化】格式化环比显示：保留整数+颜色区分
def fmt_fluc(curr, prev, is_qty=True):
    diff = int(round(curr - prev, 0))
    if diff > 0:
        color = "#d32f2f"  # 上升用红色
        arrow = "↑ +"
    elif diff < 0:
        color = "#2e7d32"  # 下降用绿色
        arrow = "↓ "
    else:
        color = "#666666"  # 持平用灰色
        arrow = ""

    # 上月数值保留整数
    prev_fmt = f"{int(round(prev, 0)):,}"
    # 环比差值带颜色
    fluc_text = f'<span style="color:{color}">{arrow}{diff:,}</span>'
    return fluc_text, prev_fmt


# -------------------- 第一行：4个分类的优化版总结文字 --------------------
c_text1, c_text2, c_text3, c_text4 = st.columns(4)

# 1. 年货前
with c_text1:
    # 总数量
    fluc_pre_qty, prev_pre_qty_fmt = fmt_fluc(total_pre_qty, prev_pre_qty)
    # 年份品数量
    fluc_pre_year_qty, prev_pre_year_qty_fmt = fmt_fluc(sum_pre.loc['年份品', '滞销数量'],
                                                        sum_pre_prev.loc['年份品', '滞销数量'])
    # 非年份品数量
    fluc_pre_non_qty, prev_pre_non_qty_fmt = fmt_fluc(sum_pre.loc['非年份品', '滞销数量'],
                                                      sum_pre_prev.loc['非年份品', '滞销数量'])
    # 总金额
    fluc_pre_amt, prev_pre_amt_fmt = fmt_fluc(total_pre_amt, prev_pre_amt)
    # 年份品金额
    fluc_pre_year_amt, prev_pre_year_amt_fmt = fmt_fluc(sum_pre.loc['年份品', '滞销金额'],
                                                        sum_pre_prev.loc['年份品', '滞销金额'])
    # 非年份品金额
    fluc_pre_non_amt, prev_pre_non_amt_fmt = fmt_fluc(sum_pre.loc['非年份品', '滞销金额'],
                                                      sum_pre_prev.loc['非年份品', '滞销金额'])

    st.markdown(f"""
    **⏳ 年货前采购**
    - 滞销数量：**{int(round(total_pre_qty, 0)):,}件**（滞销总占比 {pct_pre:.2f}%），环比 {fluc_pre_qty}，上月：{prev_pre_qty_fmt}件
      - 年份品：{int(round(sum_pre.loc['年份品', '滞销数量'], 0)):,}件（占比 {sum_pre.loc['年份品', '滞销数量'] / total_pre_qty * 100:.2f}%），环比 {fluc_pre_year_qty}，上月：{prev_pre_year_qty_fmt}件
      - 非年份品：{int(round(sum_pre.loc['非年份品', '滞销数量'], 0)):,}件（占比 {sum_pre.loc['非年份品', '滞销数量'] / total_pre_qty * 100:.2f}%），环比 {fluc_pre_non_qty}，上月：{prev_pre_non_qty_fmt}件
    - 滞销金额：**{int(round(total_pre_amt, 0)):,}元**，环比 {fluc_pre_amt}，上月：{prev_pre_amt_fmt}元
      - 年份品：{int(round(sum_pre.loc['年份品', '滞销金额'], 0)):,}元（占比 {sum_pre.loc['年份品', '滞销金额'] / total_pre_amt * 100:.2f}%），环比 {fluc_pre_year_amt}，上月：{prev_pre_year_amt_fmt}元
      - 非年份品：{int(round(sum_pre.loc['非年份品', '滞销金额'], 0)):,}元（占比 {sum_pre.loc['非年份品', '滞销金额'] / total_pre_amt * 100:.2f}%），环比 {fluc_pre_non_amt}，上月：{prev_pre_non_amt_fmt}元
    """, unsafe_allow_html=True)

# 2. 年货
with c_text2:
    # 总数量
    fluc_goods_qty, prev_goods_qty_fmt = fmt_fluc(total_goods_qty, prev_goods_qty)
    # 年份品数量
    fluc_goods_year_qty, prev_goods_year_qty_fmt = fmt_fluc(sum_goods.loc['年份品', '滞销数量'],
                                                            sum_goods_prev.loc['年份品', '滞销数量'])
    # 非年份品数量
    fluc_goods_non_qty, prev_goods_non_qty_fmt = fmt_fluc(sum_goods.loc['非年份品', '滞销数量'],
                                                          sum_goods_prev.loc['非年份品', '滞销数量'])
    # 总金额
    fluc_goods_amt, prev_goods_amt_fmt = fmt_fluc(total_goods_amt, prev_goods_amt)
    # 年份品金额
    fluc_goods_year_amt, prev_goods_year_amt_fmt = fmt_fluc(sum_goods.loc['年份品', '滞销金额'],
                                                            sum_goods_prev.loc['年份品', '滞销金额'])
    # 非年份品金额
    fluc_goods_non_amt, prev_goods_non_amt_fmt = fmt_fluc(sum_goods.loc['非年份品', '滞销金额'],
                                                          sum_goods_prev.loc['非年份品', '滞销金额'])

    st.markdown(f"""
    **🧧 年货采购**
    - 滞销数量：**{int(round(total_goods_qty, 0)):,}件**（滞销总占比 {pct_goods:.2f}%），环比 {fluc_goods_qty}，上月：{prev_goods_qty_fmt}件
      - 年份品：{int(round(sum_goods.loc['年份品', '滞销数量'], 0)):,}件（占比 {sum_goods.loc['年份品', '滞销数量'] / total_goods_qty * 100:.2f}%），环比 {fluc_goods_year_qty}，上月：{prev_goods_year_qty_fmt}件
      - 非年份品：{int(round(sum_goods.loc['非年份品', '滞销数量'], 0)):,}件（占比 {sum_goods.loc['非年份品', '滞销数量'] / total_goods_qty * 100:.2f}%），环比 {fluc_goods_non_qty}，上月：{prev_goods_non_qty_fmt}件
    - 滞销金额：**{int(round(total_goods_amt, 0)):,}元**，环比 {fluc_goods_amt}，上月：{prev_goods_amt_fmt}元
      - 年份品：{int(round(sum_goods.loc['年份品', '滞销金额'], 0)):,}元（占比 {sum_goods.loc['年份品', '滞销金额'] / total_goods_amt * 100:.2f}%），环比 {fluc_goods_year_amt}，上月：{prev_goods_year_amt_fmt}元
      - 非年份品：{int(round(sum_goods.loc['非年份品', '滞销金额'], 0)):,}元（占比 {sum_goods.loc['非年份品', '滞销金额'] / total_goods_amt * 100:.2f}%），环比 {fluc_goods_non_amt}，上月：{prev_goods_non_amt_fmt}元
    """, unsafe_allow_html=True)

# 3. 年前
with c_text3:
    # 总数量
    fluc_before_qty, prev_before_qty_fmt = fmt_fluc(total_before_qty, prev_before_qty)
    # 年份品数量
    fluc_before_year_qty, prev_before_year_qty_fmt = fmt_fluc(sum_before.loc['年份品', '滞销数量'],
                                                              sum_before_prev.loc['年份品', '滞销数量'])
    # 非年份品数量
    fluc_before_non_qty, prev_before_non_qty_fmt = fmt_fluc(sum_before.loc['非年份品', '滞销数量'],
                                                            sum_before_prev.loc['非年份品', '滞销数量'])
    # 总金额
    fluc_before_amt, prev_before_amt_fmt = fmt_fluc(total_before_amt, prev_before_amt)
    # 年份品金额
    fluc_before_year_amt, prev_before_year_amt_fmt = fmt_fluc(sum_before.loc['年份品', '滞销金额'],
                                                              sum_before_prev.loc['年份品', '滞销金额'])
    # 非年份品金额
    fluc_before_non_amt, prev_before_non_amt_fmt = fmt_fluc(sum_before.loc['非年份品', '滞销金额'],
                                                            sum_before_prev.loc['非年份品', '滞销金额'])

    st.markdown(f"""
    **🧨 年前采购**
    - 滞销数量：**{int(round(total_before_qty, 0)):,}件**（滞销总占比 {pct_before:.2f}%），环比 {fluc_before_qty}，上月：{prev_before_qty_fmt}件
      - 年份品：{int(round(sum_before.loc['年份品', '滞销数量'], 0)):,}件（占比 {sum_before.loc['年份品', '滞销数量'] / total_before_qty * 100:.2f}%），环比 {fluc_before_year_qty}，上月：{prev_before_year_qty_fmt}件
      - 非年份品：{int(round(sum_before.loc['非年份品', '滞销数量'], 0)):,}件（占比 {sum_before.loc['非年份品', '滞销数量'] / total_before_qty * 100:.2f}%），环比 {fluc_before_non_qty}，上月：{prev_before_non_qty_fmt}件
    - 滞销金额：**{int(round(total_before_amt, 0)):,}元**，环比 {fluc_before_amt}，上月：{prev_before_amt_fmt}元
      - 年份品：{int(round(sum_before.loc['年份品', '滞销金额'], 0)):,}元（占比 {sum_before.loc['年份品', '滞销金额'] / total_before_amt * 100:.2f}%），环比 {fluc_before_year_amt}，上月：{prev_before_year_amt_fmt}元
      - 非年份品：{int(round(sum_before.loc['非年份品', '滞销金额'], 0)):,}元（占比 {sum_before.loc['非年份品', '滞销金额'] / total_before_amt * 100:.2f}%），环比 {fluc_before_non_amt}，上月：{prev_before_non_amt_fmt}元
    """, unsafe_allow_html=True)

# 4. 年后
with c_text4:
    # 总数量
    fluc_after_qty, prev_after_qty_fmt = fmt_fluc(total_after_qty, prev_after_qty)
    # 年份品数量
    fluc_after_year_qty, prev_after_year_qty_fmt = fmt_fluc(sum_after.loc['年份品', '滞销数量'],
                                                            sum_after_prev.loc['年份品', '滞销数量'])
    # 非年份品数量
    fluc_after_non_qty, prev_after_non_qty_fmt = fmt_fluc(sum_after.loc['非年份品', '滞销数量'],
                                                          sum_after_prev.loc['非年份品', '滞销数量'])
    # 总金额
    fluc_after_amt, prev_after_amt_fmt = fmt_fluc(total_after_amt, prev_after_amt)
    # 年份品金额
    fluc_after_year_amt, prev_after_year_amt_fmt = fmt_fluc(sum_after.loc['年份品', '滞销金额'],
                                                            sum_after_prev.loc['年份品', '滞销金额'])
    # 非年份品金额
    fluc_after_non_amt, prev_after_non_amt_fmt = fmt_fluc(sum_after.loc['非年份品', '滞销金额'],
                                                          sum_after_prev.loc['非年份品', '滞销金额'])

    st.markdown(f"""
    **🧊 年后采购**
    - 滞销数量：**{int(round(total_after_qty, 0)):,}件**（滞销总占比 {pct_after:.2f}%），环比 {fluc_after_qty}，上月：{prev_after_qty_fmt}件
      - 年份品：{int(round(sum_after.loc['年份品', '滞销数量'], 0)):,}件（占比 {sum_after.loc['年份品', '滞销数量'] / total_after_qty * 100:.2f}%），环比 {fluc_after_year_qty}，上月：{prev_after_year_qty_fmt}件
      - 非年份品：{int(round(sum_after.loc['非年份品', '滞销数量'], 0)):,}件（占比 {sum_after.loc['非年份品', '滞销数量'] / total_after_qty * 100:.2f}%），环比 {fluc_after_non_qty}，上月：{prev_after_non_qty_fmt}件
    - 滞销金额：**{int(round(total_after_amt, 0)):,}元**，环比 {fluc_after_amt}，上月：{prev_after_amt_fmt}元
      - 年份品：{int(round(sum_after.loc['年份品', '滞销金额'], 0)):,}元（占比 {sum_after.loc['年份品', '滞销金额'] / total_after_amt * 100:.2f}%），环比 {fluc_after_year_amt}，上月：{prev_after_year_amt_fmt}元
      - 非年份品：{int(round(sum_after.loc['非年份品', '滞销金额'], 0)):,}元（占比 {sum_after.loc['非年份品', '滞销金额'] / total_after_amt * 100:.2f}%），环比 {fluc_after_non_amt}，上月：{prev_after_non_amt_fmt}元
    """, unsafe_allow_html=True)

# -------------------- 第二行：一行8列饼图，和上面卡片完美对齐 --------------------
c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)

# 年货前
fig_pre_qty = pie_chart(sum_pre, "年货前\n数量占比")
fig_pre_amt = pie_chart(sum_pre, "年货前\n金额占比")
with c1: st.plotly_chart(fig_pre_qty, use_container_width=True)
with c2: st.plotly_chart(fig_pre_amt, use_container_width=True)

# 年货
fig_goods_qty = pie_chart(sum_goods, "年货\n数量占比")
fig_goods_amt = pie_chart(sum_goods, "年货\n金额占比")
with c3: st.plotly_chart(fig_goods_qty, use_container_width=True)
with c4: st.plotly_chart(fig_goods_amt, use_container_width=True)

# 年前
fig_before_qty = pie_chart(sum_before, "年前\n数量占比")
fig_before_amt = pie_chart(sum_before, "年前\n金额占比")
with c5: st.plotly_chart(fig_before_qty, use_container_width=True)
with c6: st.plotly_chart(fig_before_amt, use_container_width=True)

# 年后
fig_after_qty = pie_chart(sum_after, "年后\n数量占比")
fig_after_amt = pie_chart(sum_after, "年后\n金额占比")
with c7: st.plotly_chart(fig_after_qty, use_container_width=True)
with c8: st.plotly_chart(fig_after_amt, use_container_width=True)

# ===================== 【最终版】年份品 / 非年份品 一行4列饼图 =====================
# ===================== 【最终细化版】年份品 & 非年份品 · 滞销结构占比（含环比+细分总结） =====================
st.divider()
st.subheader("🍰 年份品 & 非年份品 · 滞销结构占比")

# 1. 匹配年份品标签 + 上月数据
df_temp = df_merge_curr.merge(
    df_prod[["MSKU", "是否年份"]], on="MSKU", how="left"
).fillna("否")
df_temp["商品类型"] = df_temp["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")

df_temp_prev = df_merge_prev.merge(
    df_prod[["MSKU", "是否年份"]], on="MSKU", how="left"
).fillna("否")
df_temp_prev["商品类型"] = df_temp_prev["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")

# 2. 环比格式化函数（保留整数+颜色区分）
def fmt_fluc(curr, prev):
    curr_int = int(round(curr, 0))
    prev_int = int(round(prev, 0))
    diff = curr_int - prev_int
    if diff > 0:
        color = "#d32f2f"
        arrow = "↑ +"
    elif diff < 0:
        color = "#2e7d32"
        arrow = "↓ "
    else:
        color = "#666666"
        arrow = ""
    fluc_html = f'<span style="color:{color}">{arrow}{diff:,}</span>'
    return curr_int, prev_int, fluc_html

# 3. 按【商品类型 + 4类滞销】汇总（当月+上月）
def get_full_summary(df_curr, df_prev, type_name):
    curr = df_curr[df_curr["商品类型"] == type_name]
    prev = df_prev[df_prev["商品类型"] == type_name]

    # 数量数据
    qty_pre_curr, qty_pre_prev, qty_pre_fluc = fmt_fluc(curr["年货前采购滞销数量"].sum(), prev["年货前采购滞销数量"].sum())
    qty_goods_curr, qty_goods_prev, qty_goods_fluc = fmt_fluc(curr["年货采购滞销数量"].sum(), prev["年货采购滞销数量"].sum())
    qty_before_curr, qty_before_prev, qty_before_fluc = fmt_fluc(curr["年前采购滞销数量"].sum(), prev["年前采购滞销数量"].sum())
    qty_after_curr, qty_after_prev, qty_after_fluc = fmt_fluc(curr["年后采购滞销数量"].sum(), prev["年后采购滞销数量"].sum())
    total_qty_curr = qty_pre_curr + qty_goods_curr + qty_before_curr + qty_after_curr
    total_qty_prev = qty_pre_prev + qty_goods_prev + qty_before_prev + qty_after_prev
    _, _, total_qty_fluc = fmt_fluc(total_qty_curr, total_qty_prev)

    # 金额数据
    amt_pre_curr, amt_pre_prev, amt_pre_fluc = fmt_fluc(curr["年货前采购滞销金额"].sum(), prev["年货前采购滞销金额"].sum())
    amt_goods_curr, amt_goods_prev, amt_goods_fluc = fmt_fluc(curr["年货采购滞销金额"].sum(), prev["年货采购滞销金额"].sum())
    amt_before_curr, amt_before_prev, amt_before_fluc = fmt_fluc(curr["年前采购滞销金额"].sum(), prev["年前采购滞销金额"].sum())
    amt_after_curr, amt_after_prev, amt_after_fluc = fmt_fluc(curr["年后采购滞销金额"].sum(), prev["年后采购滞销金额"].sum())
    total_amt_curr = amt_pre_curr + amt_goods_curr + amt_before_curr + amt_after_curr
    total_amt_prev = amt_pre_prev + amt_goods_prev + amt_before_prev + amt_after_prev
    _, _, total_amt_fluc = fmt_fluc(total_amt_curr, total_amt_prev)

    return {
        "labels": ["年货前", "年货", "年前", "年后"],
        "qty": [qty_pre_curr, qty_goods_curr, qty_before_curr, qty_after_curr],
        "amt": [amt_pre_curr, amt_goods_curr, amt_before_curr, amt_after_curr],
        "total_qty_curr": total_qty_curr,
        "total_qty_prev": total_qty_prev,
        "total_qty_fluc": total_qty_fluc,
        "total_amt_curr": total_amt_curr,
        "total_amt_prev": total_amt_prev,
        "total_amt_fluc": total_amt_fluc,
        "detail_qty": [
            (qty_pre_curr, qty_pre_prev, qty_pre_fluc, qty_pre_curr/total_qty_curr*100 if total_qty_curr else 0),
            (qty_goods_curr, qty_goods_prev, qty_goods_fluc, qty_goods_curr/total_qty_curr*100 if total_qty_curr else 0),
            (qty_before_curr, qty_before_prev, qty_before_fluc, qty_before_curr/total_qty_curr*100 if total_qty_curr else 0),
            (qty_after_curr, qty_after_prev, qty_after_fluc, qty_after_curr/total_qty_curr*100 if total_qty_curr else 0)
        ],
        "detail_amt": [
            (amt_pre_curr, amt_pre_prev, amt_pre_fluc, amt_pre_curr/total_amt_curr*100 if total_amt_curr else 0),
            (amt_goods_curr, amt_goods_prev, amt_goods_fluc, amt_goods_curr/total_amt_curr*100 if total_amt_curr else 0),
            (amt_before_curr, amt_before_prev, amt_before_fluc, amt_before_curr/total_amt_curr*100 if total_amt_curr else 0),
            (amt_after_curr, amt_after_prev, amt_after_fluc, amt_after_curr/total_amt_curr*100 if total_amt_curr else 0)
        ]
    }

non_year = get_full_summary(df_temp, df_temp_prev, "非年份品")
year = get_full_summary(df_temp, df_temp_prev, "年份品")

# 4. 饼图函数
import plotly.express as px
def pie(data, names, title):
    fig = px.pie(values=data, names=names, color_discrete_sequence=["#ff9999","#66b3ff","#99ff99","#ffcc99"])
    fig.update_traces(textposition="inside", textinfo="percent", showlegend=False)
    fig.update_layout(height=220, margin=dict(l=10,r=10,t=30,b=10),
                      title=dict(text=title, font=dict(size=13)))
    return fig

# -------------------- 一行4列布局 --------------------
col1, col2, col3, col4 = st.columns(4)

# 左1：非年份品 · 数量占比 + 详细总结
with col1:
    st.markdown(f"""
    **🔹 非年份品 滞销数量**  
    总计：{non_year['total_qty_curr']:,} 件，环比 {non_year['total_qty_fluc']}，上月：{non_year['total_qty_prev']:,} 件  
    其中：  
    - 年货前采购：{non_year['detail_qty'][0][0]:,} 件（占比 {non_year['detail_qty'][0][3]:.2f}%），环比 {non_year['detail_qty'][0][2]}，上月：{non_year['detail_qty'][0][1]:,} 件  
    - 年货采购：{non_year['detail_qty'][1][0]:,} 件（占比 {non_year['detail_qty'][1][3]:.2f}%），环比 {non_year['detail_qty'][1][2]}，上月：{non_year['detail_qty'][1][1]:,} 件  
    - 年前采购：{non_year['detail_qty'][2][0]:,} 件（占比 {non_year['detail_qty'][2][3]:.2f}%），环比 {non_year['detail_qty'][2][2]}，上月：{non_year['detail_qty'][2][1]:,} 件  
    - 年后采购：{non_year['detail_qty'][3][0]:,} 件（占比 {non_year['detail_qty'][3][3]:.2f}%），环比 {non_year['detail_qty'][3][2]}，上月：{non_year['detail_qty'][3][1]:,} 件  
    """, unsafe_allow_html=True)
    st.plotly_chart(pie(non_year['qty'], non_year['labels'], "数量占比"), use_container_width=True)

# 左2：非年份品 · 金额占比 + 详细总结
with col2:
    st.markdown(f"""
    **🔹 非年份品 滞销金额**  
    总计：{non_year['total_amt_curr']:,} 元，环比 {non_year['total_amt_fluc']}，上月：{non_year['total_amt_prev']:,} 元  
    其中：  
    - 年货前采购：{non_year['detail_amt'][0][0]:,} 元（占比 {non_year['detail_amt'][0][3]:.2f}%），环比 {non_year['detail_amt'][0][2]}，上月：{non_year['detail_amt'][0][1]:,} 元  
    - 年货采购：{non_year['detail_amt'][1][0]:,} 元（占比 {non_year['detail_amt'][1][3]:.2f}%），环比 {non_year['detail_amt'][1][2]}，上月：{non_year['detail_amt'][1][1]:,} 元  
    - 年前采购：{non_year['detail_amt'][2][0]:,} 元（占比 {non_year['detail_amt'][2][3]:.2f}%），环比 {non_year['detail_amt'][2][2]}，上月：{non_year['detail_amt'][2][1]:,} 元  
    - 年后采购：{non_year['detail_amt'][3][0]:,} 元（占比 {non_year['detail_amt'][3][3]:.2f}%），环比 {non_year['detail_amt'][3][2]}，上月：{non_year['detail_amt'][3][1]:,} 元  
    """, unsafe_allow_html=True)
    st.plotly_chart(pie(non_year['amt'], non_year['labels'], "金额占比"), use_container_width=True)

# 右1：年份品 · 数量占比 + 详细总结
with col3:
    st.markdown(f"""
    **🔸 年份品 滞销数量**  
    总计：{year['total_qty_curr']:,} 件，环比 {year['total_qty_fluc']}，上月：{year['total_qty_prev']:,} 件  
    其中：  
    - 年货前采购滞销数量：{year['detail_qty'][0][0]:,} 件（占比 {year['detail_qty'][0][3]:.2f}%），环比 {year['detail_qty'][0][2]}，上月：{year['detail_qty'][0][1]:,} 件  
    - 年货采购滞销数量：{year['detail_qty'][1][0]:,} 件（占比 {year['detail_qty'][1][3]:.2f}%），环比 {year['detail_qty'][1][2]}，上月：{year['detail_qty'][1][1]:,} 件  
    - 年前采购滞销数量：{year['detail_qty'][2][0]:,} 件（占比 {year['detail_qty'][2][3]:.2f}%），环比 {year['detail_qty'][2][2]}，上月：{year['detail_qty'][2][1]:,} 件  
    - 年后采购滞销数量：{year['detail_qty'][3][0]:,} 件（占比 {year['detail_qty'][3][3]:.2f}%），环比 {year['detail_qty'][3][2]}，上月：{year['detail_qty'][3][1]:,} 件  
    """, unsafe_allow_html=True)
    st.plotly_chart(pie(year['qty'], year['labels'], "数量占比"), use_container_width=True)

# 右2：年份品 · 金额占比 + 详细总结
with col4:
    st.markdown(f"""
    **🔸 年份品 滞销金额**  
    总计：{year['total_amt_curr']:,} 元，环比 {year['total_amt_fluc']}，上月：{year['total_amt_prev']:,} 元  
    其中：  
    - 年货前采购滞销金额：{year['detail_amt'][0][0]:,} 元（占比 {year['detail_amt'][0][3]:.2f}%），环比 {year['detail_amt'][0][2]}，上月：{year['detail_amt'][0][1]:,} 元  
    - 年货采购滞销金额：{year['detail_amt'][1][0]:,} 元（占比 {year['detail_amt'][1][3]:.2f}%），环比 {year['detail_amt'][1][2]}，上月：{year['detail_amt'][1][1]:,} 元  
    - 年前采购滞销金额：{year['detail_amt'][2][0]:,} 元（占比 {year['detail_amt'][2][3]:.2f}%），环比 {year['detail_amt'][2][2]}，上月：{year['detail_amt'][2][1]:,} 元  
    - 年后采购滞销金额：{year['detail_amt'][3][0]:,} 元（占比 {year['detail_amt'][3][3]:.2f}%），环比 {year['detail_amt'][3][2]}，上月：{year['detail_amt'][3][1]:,} 元  
    """, unsafe_allow_html=True)
    st.plotly_chart(pie(year['amt'], year['labels'], "金额占比"), use_container_width=True)

# ===================== 年货前采购滞销 - 按店铺拆分 =====================
st.divider()
st.subheader("🧧 年货前采购滞销 - 按店铺拆分分析")

df_shop_curr = df_merge_curr.merge(df_prod[["MSKU", "是否年份"]], on="MSKU", how="left").fillna("否")
df_shop_prev = df_merge_prev.merge(df_prod[["MSKU", "是否年份"]], on="MSKU", how="left").fillna("否")
df_shop_curr["商品类型"] = df_shop_curr["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")
df_shop_prev["商品类型"] = df_shop_prev["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")

df_shop_curr = df_shop_curr[df_shop_curr["年货前采购滞销数量"] > 0].copy()
df_shop_prev = df_shop_prev[df_shop_prev["年货前采购滞销数量"] > 0].copy()

shop_total_curr = df_shop_curr.groupby("店铺").agg(总数量=("年货前采购滞销数量", "sum"),
                                                   总金额=("年货前采购滞销金额", "sum")).reset_index()
shop_total_prev = df_shop_prev.groupby("店铺").agg(总数量_上月=("年货前采购滞销数量", "sum"),
                                                   总金额_上月=("年货前采购滞销金额", "sum")).reset_index()
shop_type_curr = df_shop_curr.groupby(["店铺", "商品类型"]).agg(数量=("年货前采购滞销数量", "sum"),
                                                                金额=("年货前采购滞销金额", "sum")).reset_index()
shop_type_prev = df_shop_prev.groupby(["店铺", "商品类型"]).agg(数量_上月=("年货前采购滞销数量", "sum"),
                                                                金额_上月=("年货前采购滞销金额", "sum")).reset_index()

shop_all = shop_total_curr.merge(shop_total_prev, on="店铺", how="left").fillna(0)
shop_type_all = shop_type_curr.merge(shop_type_prev, on=["店铺", "商品类型"], how="left").fillna(0)

total_qty = shop_all["总数量"].sum()
total_amt = shop_all["总金额"].sum()


def fmt_fluc(curr, prev):
    curr_int = int(round(curr, 0))
    prev_int = int(round(prev, 0))
    diff = curr_int - prev_int
    if diff > 0:
        return f'<span style="color:#d32f2f">↑ +{diff:,}</span>', curr_int, prev_int
    elif diff < 0:
        return f'<span style="color:#2e7d32">↓ {diff:,}</span>', curr_int, prev_int
    else:
        return '<span style="color:#666">持平</span>', curr_int, prev_int


import plotly.express as px

shops = shop_all["店铺"].unique().tolist()
for idx in range(0, len(shops), 5):
    batch = shops[idx:idx + 5]
    cols = st.columns(len(batch))
    for i, shop in enumerate(batch):
        d = shop_all[shop_all["店铺"] == shop].iloc[0]
        t = shop_type_all[shop_type_all["店铺"] == shop]

        qf, q, qp = fmt_fluc(d["总数量"], d["总数量_上月"])
        af, a, ap = fmt_fluc(d["总金额"], d["总金额_上月"])
        qpct = q / total_qty * 100 if total_qty else 0
        apct = a / total_amt * 100 if total_amt else 0

        y = t[t["商品类型"] == "年份品"]
        yq = int(y["数量"].iloc[0]) if not y.empty else 0
        ya = int(y["金额"].iloc[0]) if not y.empty else 0
        yqp = int(y["数量_上月"].iloc[0]) if not y.empty else 0
        yap = int(y["金额_上月"].iloc[0]) if not y.empty else 0
        yqf, _, _ = fmt_fluc(yq, yqp)
        yaf, _, _ = fmt_fluc(ya, yap)
        yqpct = yq / q * 100 if q else 0
        yapct = ya / a * 100 if a else 0

        n = t[t["商品类型"] == "非年份品"]
        nq = int(n["数量"].iloc[0]) if not n.empty else 0
        na = int(n["金额"].iloc[0]) if not n.empty else 0
        nqp = int(n["数量_上月"].iloc[0]) if not n.empty else 0
        nap = int(n["金额_上月"].iloc[0]) if not n.empty else 0
        nqf, _, _ = fmt_fluc(nq, nqp)
        naf, _, _ = fmt_fluc(na, nap)
        nqpct = nq / q * 100 if q else 0
        napct = na / a * 100 if a else 0

        with cols[i]:
            st.markdown(f"""
**🏪 {shop}**
滞销数量：{q:,} 件（{qpct:.1f}%），环比 {qf}，上月：{qp:,} 件
<small style="color:#888;">
其中：
年份品数量：{yq:,}（{yqpct:.2f}%），环比 {yqf}，上月：{yqp:,} 件
非年份品数量：{nq:,}（{nqpct:.2f}%），环比 {nqf}，上月：{nqp:,} 件
</small>

滞销金额：{a:,} 元（{apct:.1f}%），环比 {af}，上月：{ap:,} 元
<small style="color:#888;">
其中：
年份品金额：{ya:,}（{yapct:.2f}%），环比 {yaf}，上月：{yap:,} 元
非年份品金额：{na:,}（{napct:.2f}%），环比 {naf}，上月：{nap:,} 元
</small>
""", unsafe_allow_html=True)

st.divider()
c1, c2 = st.columns(2)
with c1:
    fig = px.pie(shop_all, names="店铺", values="总数量", title="年货前滞销数量-店铺占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)
with c2:
    fig = px.pie(shop_all, names="店铺", values="总金额", title="年货前滞销金额-店铺占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)

# ===================== 年货采购滞销 - 按店铺拆分 =====================
st.divider()
st.subheader("🧨 年货采购滞销 - 按店铺拆分分析")

df_shop_curr = df_merge_curr.merge(df_prod[["MSKU", "是否年份"]], on="MSKU", how="left").fillna("否")
df_shop_prev = df_merge_prev.merge(df_prod[["MSKU", "是否年份"]], on="MSKU", how="left").fillna("否")
df_shop_curr["商品类型"] = df_shop_curr["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")
df_shop_prev["商品类型"] = df_shop_prev["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")

df_shop_curr = df_shop_curr[df_shop_curr["年货采购滞销数量"] > 0].copy()
df_shop_prev = df_shop_prev[df_shop_prev["年货采购滞销数量"] > 0].copy()

shop_total_curr = df_shop_curr.groupby("店铺").agg(总数量=("年货采购滞销数量", "sum"),
                                                   总金额=("年货采购滞销金额", "sum")).reset_index()
shop_total_prev = df_shop_prev.groupby("店铺").agg(总数量_上月=("年货采购滞销数量", "sum"),
                                                   总金额_上月=("年货采购滞销金额", "sum")).reset_index()
shop_type_curr = df_shop_curr.groupby(["店铺", "商品类型"]).agg(数量=("年货采购滞销数量", "sum"),
                                                                金额=("年货采购滞销金额", "sum")).reset_index()
shop_type_prev = df_shop_prev.groupby(["店铺", "商品类型"]).agg(数量_上月=("年货采购滞销数量", "sum"),
                                                                金额_上月=("年货采购滞销金额", "sum")).reset_index()

shop_all = shop_total_curr.merge(shop_total_prev, on="店铺", how="left").fillna(0)
shop_type_all = shop_type_curr.merge(shop_type_prev, on=["店铺", "商品类型"], how="left").fillna(0)

total_qty = shop_all["总数量"].sum()
total_amt = shop_all["总金额"].sum()


def fmt_fluc(curr, prev):
    curr_int = int(round(curr, 0))
    prev_int = int(round(prev, 0))
    diff = curr_int - prev_int
    if diff > 0:
        return f'<span style="color:#d32f2f">↑ +{diff:,}</span>', curr_int, prev_int
    elif diff < 0:
        return f'<span style="color:#2e7d32">↓ {diff:,}</span>', curr_int, prev_int
    else:
        return '<span style="color:#666">持平</span>', curr_int, prev_int


import plotly.express as px

shops = shop_all["店铺"].unique().tolist()
for idx in range(0, len(shops), 5):
    batch = shops[idx:idx + 5]
    cols = st.columns(len(batch))
    for i, shop in enumerate(batch):
        d = shop_all[shop_all["店铺"] == shop].iloc[0]
        t = shop_type_all[shop_type_all["店铺"] == shop]

        qf, q, qp = fmt_fluc(d["总数量"], d["总数量_上月"])
        af, a, ap = fmt_fluc(d["总金额"], d["总金额_上月"])
        qpct = q / total_qty * 100 if total_qty else 0
        apct = a / total_amt * 100 if total_amt else 0

        y = t[t["商品类型"] == "年份品"]
        yq = int(y["数量"].iloc[0]) if not y.empty else 0
        ya = int(y["金额"].iloc[0]) if not y.empty else 0
        yqp = int(y["数量_上月"].iloc[0]) if not y.empty else 0
        yap = int(y["金额_上月"].iloc[0]) if not y.empty else 0
        yqf, _, _ = fmt_fluc(yq, yqp)
        yaf, _, _ = fmt_fluc(ya, yap)
        yqpct = yq / q * 100 if q else 0
        yapct = ya / a * 100 if a else 0

        n = t[t["商品类型"] == "非年份品"]
        nq = int(n["数量"].iloc[0]) if not n.empty else 0
        na = int(n["金额"].iloc[0]) if not n.empty else 0
        nqp = int(n["数量_上月"].iloc[0]) if not n.empty else 0
        nap = int(n["金额_上月"].iloc[0]) if not n.empty else 0
        nqf, _, _ = fmt_fluc(nq, nqp)
        naf, _, _ = fmt_fluc(na, nap)
        nqpct = nq / q * 100 if q else 0
        napct = na / a * 100 if a else 0

        with cols[i]:
            st.markdown(f"""
**🏪 {shop}**
滞销数量：{q:,} 件（{qpct:.1f}%），环比 {qf}，上月：{qp:,} 件
<small style="color:#888;">
其中：
年份品数量：{yq:,}（{yqpct:.2f}%），环比 {yqf}，上月：{yqp:,} 件
非年份品数量：{nq:,}（{nqpct:.2f}%），环比 {nqf}，上月：{nqp:,} 件
</small>

滞销金额：{a:,} 元（{apct:.1f}%），环比 {af}，上月：{ap:,} 元
<small style="color:#888;">
其中：
年份品金额：{ya:,}（{yapct:.2f}%），环比 {yaf}，上月：{yap:,} 元
非年份品金额：{na:,}（{napct:.2f}%），环比 {naf}，上月：{nap:,} 元
</small>
""", unsafe_allow_html=True)

st.divider()
c1, c2 = st.columns(2)
with c1:
    fig = px.pie(shop_all, names="店铺", values="总数量", title="年货滞销数量-店铺占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)
with c2:
    fig = px.pie(shop_all, names="店铺", values="总金额", title="年货滞销金额-店铺占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)





# ===================== 年前采购滞销 - 按店铺拆分（你要的最终文字版） =====================
st.divider()
st.subheader("🧨 年前采购滞销 - 按店铺拆分分析")

# 1. 数据准备（含年份品标签）
df_shop_curr = df_merge_curr.merge(
    df_prod[["MSKU", "是否年份"]], on="MSKU", how="left"
).fillna("否")
df_shop_prev = df_merge_prev.merge(
    df_prod[["MSKU", "是否年份"]], on="MSKU", how="left"
).fillna("否")

df_shop_curr["商品类型"] = df_shop_curr["是否年份"].apply(
    lambda x: "年份品" if str(x).strip() == "是" else "非年份品"
)
df_shop_prev["商品类型"] = df_shop_prev["是否年份"].apply(
    lambda x: "年份品" if str(x).strip() == "是" else "非年份品"
)

# 只筛选年前采购滞销>0的行
df_shop_curr = df_shop_curr[df_shop_curr["年前采购滞销数量"] > 0].copy()
df_shop_prev = df_shop_prev[df_shop_prev["年前采购滞销数量"] > 0].copy()

# 2. 按店铺聚合【整体】数据
shop_total_curr = df_shop_curr.groupby("店铺").agg(
    总数量=("年前采购滞销数量", "sum"),
    总金额=("年前采购滞销金额", "sum")
).reset_index()

shop_total_prev = df_shop_prev.groupby("店铺").agg(
    总数量_上月=("年前采购滞销数量", "sum"),
    总金额_上月=("年前采购滞销金额", "sum")
).reset_index()

# 3. 按店铺+商品类型聚合【年份/非年份】数据
shop_type_curr = df_shop_curr.groupby(["店铺", "商品类型"]).agg(
    数量=("年前采购滞销数量", "sum"),
    金额=("年前采购滞销金额", "sum")
).reset_index()

shop_type_prev = df_shop_prev.groupby(["店铺", "商品类型"]).agg(
    数量_上月=("年前采购滞销数量", "sum"),
    金额_上月=("年前采购滞销金额", "sum")
).reset_index()

# 合并所有数据
shop_all = shop_total_curr.merge(shop_total_prev, on="店铺", how="left").fillna(0)
shop_type_all = shop_type_curr.merge(shop_type_prev, on=["店铺", "商品类型"], how="left").fillna(0)

# 整体合计（按店铺维度）
total_qty = shop_all["总数量"].sum()
total_amt = shop_all["总金额"].sum()


# 环比格式化函数（红升绿降）
def fmt_fluc(curr, prev):
    curr_int = int(round(curr, 0))
    prev_int = int(round(prev, 0))
    diff = curr_int - prev_int
    if diff > 0:
        return f'<span style="color:#d32f2f">↑ +{diff:,}</span>', curr_int, prev_int
    elif diff < 0:
        return f'<span style="color:#2e7d32">↓ {diff:,}</span>', curr_int, prev_int
    else:
        return '<span style="color:#666">持平</span>', curr_int, prev_int


# 4. 一行五列自适应布局
import plotly.express as px

shops = shop_all["店铺"].unique().tolist()

# 分批显示：每5个店铺一行
for idx in range(0, len(shops), 5):
    batch = shops[idx:idx + 5]
    cols = st.columns(len(batch))
    for i, shop in enumerate(batch):
        shop_data = shop_all[shop_all["店铺"] == shop].iloc[0]
        shop_type_data = shop_type_all[shop_type_all["店铺"] == shop]

        # 整体数据
        qty_fluc, qty, qty_prev = fmt_fluc(shop_data["总数量"], shop_data["总数量_上月"])
        amt_fluc, amt, amt_prev = fmt_fluc(shop_data["总金额"], shop_data["总金额_上月"])
        qty_pct = (qty / total_qty * 100) if total_qty else 0
        amt_pct = (amt / total_amt * 100) if total_amt else 0

        # 年份品
        year_data = shop_type_data[shop_type_data["商品类型"] == "年份品"]
        year_qty = int(year_data["数量"].iloc[0]) if not year_data.empty else 0
        year_amt = int(year_data["金额"].iloc[0]) if not year_data.empty else 0
        year_qty_prev = int(year_data["数量_上月"].iloc[0]) if not year_data.empty else 0
        year_amt_prev = int(year_data["金额_上月"].iloc[0]) if not year_data.empty else 0
        year_qty_pct = (year_qty / qty * 100) if qty else 0
        year_amt_pct = (year_amt / amt * 100) if amt else 0
        year_qty_fluc, _, _ = fmt_fluc(year_qty, year_qty_prev)
        year_amt_fluc, _, _ = fmt_fluc(year_amt, year_amt_prev)

        # 非年份品
        non_year_data = shop_type_data[shop_type_data["商品类型"] == "非年份品"]
        non_year_qty = int(non_year_data["数量"].iloc[0]) if not non_year_data.empty else 0
        non_year_amt = int(non_year_data["金额"].iloc[0]) if not non_year_data.empty else 0
        non_year_qty_prev = int(non_year_data["数量_上月"].iloc[0]) if not non_year_data.empty else 0
        non_year_amt_prev = int(non_year_data["金额_上月"].iloc[0]) if not non_year_data.empty else 0
        non_year_qty_pct = (non_year_qty / qty * 100) if qty else 0
        non_year_amt_pct = (non_year_amt / amt * 100) if amt else 0
        non_year_qty_fluc, _, _ = fmt_fluc(non_year_qty, non_year_qty_prev)
        non_year_amt_fluc, _, _ = fmt_fluc(non_year_amt, non_year_amt_prev)

        # ===================== 你要的最终格式 =====================
        with cols[i]:
            st.markdown(f"""
**🏪 {shop}**
滞销数量：{qty:,} 件（{qty_pct:.1f}%），环比 {qty_fluc}，上月：{qty_prev:,} 件
<small style="color:#888;">
其中：
年份品数量：{year_qty:,}（{year_qty_pct:.2f}%），环比 {year_qty_fluc}，上月：{year_qty_prev:,} 件
非年份品数量：{non_year_qty:,}（{non_year_qty_pct:.2f}%），环比 {non_year_qty_fluc}，上月：{non_year_qty_prev:,} 件
</small>

滞销金额：{amt:,} 元（{amt_pct:.1f}%），环比 {amt_fluc}，上月：{amt_prev:,} 元
<small style="color:#888;">
其中：
年份品金额：{year_amt:,}（{year_amt_pct:.2f}%），环比 {year_amt_fluc}，上月：{year_amt_prev:,} 元
非年份品金额：{non_year_amt:,}（{non_year_amt_pct:.2f}%），环比 {non_year_amt_fluc}，上月：{non_year_amt_prev:,} 元
</small>
            """, unsafe_allow_html=True)

# 5. 饼图区域
st.divider()
c_pie1, c_pie2 = st.columns(2)
with c_pie1:
    fig_qty = px.pie(shop_all, names="店铺", values="总数量", title="年前采购滞销数量 - 店铺占比")
    fig_qty.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig_qty, use_container_width=True)

with c_pie2:
    fig_amt = px.pie(shop_all, names="店铺", values="总金额", title="年前采购滞销金额 - 店铺占比")
    fig_amt.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig_amt, use_container_width=True)

# ===================== 年后采购滞销 - 按店铺拆分 =====================
st.divider()
st.subheader("🧧 年后采购滞销 - 按店铺拆分分析")

df_shop_curr = df_merge_curr.merge(df_prod[["MSKU", "是否年份"]], on="MSKU", how="left").fillna("否")
df_shop_prev = df_merge_prev.merge(df_prod[["MSKU", "是否年份"]], on="MSKU", how="left").fillna("否")
df_shop_curr["商品类型"] = df_shop_curr["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")
df_shop_prev["商品类型"] = df_shop_prev["是否年份"].apply(lambda x: "年份品" if str(x).strip() == "是" else "非年份品")

df_shop_curr = df_shop_curr[df_shop_curr["年后采购滞销数量"] > 0].copy()
df_shop_prev = df_shop_prev[df_shop_prev["年后采购滞销数量"] > 0].copy()

shop_total_curr = df_shop_curr.groupby("店铺").agg(总数量=("年后采购滞销数量", "sum"),
                                                   总金额=("年后采购滞销金额", "sum")).reset_index()
shop_total_prev = df_shop_prev.groupby("店铺").agg(总数量_上月=("年后采购滞销数量", "sum"),
                                                   总金额_上月=("年后采购滞销金额", "sum")).reset_index()
shop_type_curr = df_shop_curr.groupby(["店铺", "商品类型"]).agg(数量=("年后采购滞销数量", "sum"),
                                                                金额=("年后采购滞销金额", "sum")).reset_index()
shop_type_prev = df_shop_prev.groupby(["店铺", "商品类型"]).agg(数量_上月=("年后采购滞销数量", "sum"),
                                                                金额_上月=("年后采购滞销金额", "sum")).reset_index()

shop_all = shop_total_curr.merge(shop_total_prev, on="店铺", how="left").fillna(0)
shop_type_all = shop_type_curr.merge(shop_type_prev, on=["店铺", "商品类型"], how="left").fillna(0)

total_qty = shop_all["总数量"].sum()
total_amt = shop_all["总金额"].sum()


def fmt_fluc(curr, prev):
    curr_int = int(round(curr, 0))
    prev_int = int(round(prev, 0))
    diff = curr_int - prev_int
    if diff > 0:
        return f'<span style="color:#d32f2f">↑ +{diff:,}</span>', curr_int, prev_int
    elif diff < 0:
        return f'<span style="color:#2e7d32">↓ {diff:,}</span>', curr_int, prev_int
    else:
        return '<span style="color:#666">持平</span>', curr_int, prev_int


import plotly.express as px

shops = shop_all["店铺"].unique().tolist()
for idx in range(0, len(shops), 5):
    batch = shops[idx:idx + 5]
    cols = st.columns(len(batch))
    for i, shop in enumerate(batch):
        d = shop_all[shop_all["店铺"] == shop].iloc[0]
        t = shop_type_all[shop_type_all["店铺"] == shop]

        qf, q, qp = fmt_fluc(d["总数量"], d["总数量_上月"])
        af, a, ap = fmt_fluc(d["总金额"], d["总金额_上月"])
        qpct = q / total_qty * 100 if total_qty else 0
        apct = a / total_amt * 100 if total_amt else 0

        y = t[t["商品类型"] == "年份品"]
        yq = int(y["数量"].iloc[0]) if not y.empty else 0
        ya = int(y["金额"].iloc[0]) if not y.empty else 0
        yqp = int(y["数量_上月"].iloc[0]) if not y.empty else 0
        yap = int(y["金额_上月"].iloc[0]) if not y.empty else 0
        yqf, _, _ = fmt_fluc(yq, yqp)
        yaf, _, _ = fmt_fluc(ya, yap)
        yqpct = yq / q * 100 if q else 0
        yapct = ya / a * 100 if a else 0

        n = t[t["商品类型"] == "非年份品"]
        nq = int(n["数量"].iloc[0]) if not n.empty else 0
        na = int(n["金额"].iloc[0]) if not n.empty else 0
        nqp = int(n["数量_上月"].iloc[0]) if not n.empty else 0
        nap = int(n["金额_上月"].iloc[0]) if not n.empty else 0
        nqf, _, _ = fmt_fluc(nq, nqp)
        naf, _, _ = fmt_fluc(na, nap)
        nqpct = nq / q * 100 if q else 0
        napct = na / a * 100 if a else 0

        with cols[i]:
            st.markdown(f"""
**🏪 {shop}**
滞销数量：{q:,} 件（{qpct:.1f}%），环比 {qf}，上月：{qp:,} 件
<small style="color:#888;">
其中：
年份品数量：{yq:,}（{yqpct:.2f}%），环比 {yqf}，上月：{yqp:,} 件
非年份品数量：{nq:,}（{nqpct:.2f}%），环比 {nqf}，上月：{nqp:,} 件
</small>

滞销金额：{a:,} 元（{apct:.1f}%），环比 {af}，上月：{ap:,} 元
<small style="color:#888;">
其中：
年份品金额：{ya:,}（{yapct:.2f}%），环比 {yaf}，上月：{yap:,} 元
非年份品金额：{na:,}（{napct:.2f}%），环比 {naf}，上月：{nap:,} 元
</small>
""", unsafe_allow_html=True)

st.divider()
c1, c2 = st.columns(2)
with c1:
    fig = px.pie(shop_all, names="店铺", values="总数量", title="年后滞销数量-店铺占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)
with c2:
    fig = px.pie(shop_all, names="店铺", values="总金额", title="年后滞销金额-店铺占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)

# ===================== 全店铺总滞销汇总（按店铺 · 文字+双饼图） =====================
st.divider()
st.subheader("📊 全店铺总滞销汇总分析")

# 1. 合并年份品标签（用你现有的字段）
df_shop_curr = df_merge_curr.merge(
    df_prod[["MSKU", "是否年份"]], on="MSKU", how="left"
).fillna("否")
df_shop_prev = df_merge_prev.merge(
    df_prod[["MSKU", "是否年份"]], on="MSKU", how="left"
).fillna("否")

df_shop_curr["商品类型"] = df_shop_curr["是否年份"].apply(
    lambda x: "年份品" if str(x).strip() == "是" else "非年份品"
)
df_shop_prev["商品类型"] = df_shop_prev["是否年份"].apply(
    lambda x: "年份品" if str(x).strip() == "是" else "非年份品"
)

# 2. 计算【总滞销数量/金额】（你真正存在的字段求和）
df_shop_curr["总滞销数量"] = (
    df_shop_curr["年前采购滞销数量"] +
    df_shop_curr["年货前采购滞销数量"] +
    df_shop_curr["年货采购滞销数量"] +
    df_shop_curr["年后采购滞销数量"]
)
df_shop_curr["总滞销金额"] = (
    df_shop_curr["年前采购滞销金额"] +
    df_shop_curr["年货前采购滞销金额"] +
    df_shop_curr["年货采购滞销金额"] +
    df_shop_curr["年后采购滞销金额"]
)

df_shop_prev["总滞销数量"] = (
    df_shop_prev["年前采购滞销数量"] +
    df_shop_prev["年货前采购滞销数量"] +
    df_shop_prev["年货采购滞销数量"] +
    df_shop_prev["年后采购滞销数量"]
)
df_shop_prev["总滞销金额"] = (
    df_shop_prev["年前采购滞销金额"] +
    df_shop_prev["年货前采购滞销金额"] +
    df_shop_prev["年货采购滞销金额"] +
    df_shop_prev["年后采购滞销金额"]
)

# 只保留有滞销的行
df_shop_curr = df_shop_curr[df_shop_curr["总滞销数量"] > 0].copy()
df_shop_prev = df_shop_prev[df_shop_prev["总滞销数量"] > 0].copy()

# 3. 按店铺聚合
shop_total_curr = df_shop_curr.groupby("店铺").agg(
    总数量=("总滞销数量", "sum"),
    总金额=("总滞销金额", "sum")
).reset_index()

shop_total_prev = df_shop_prev.groupby("店铺").agg(
    总数量_上月=("总滞销数量", "sum"),
    总金额_上月=("总滞销金额", "sum")
).reset_index()

# 4. 按店铺+类型聚合
shop_type_curr = df_shop_curr.groupby(["店铺", "商品类型"]).agg(
    数量=("总滞销数量", "sum"),
    金额=("总滞销金额", "sum")
).reset_index()

shop_type_prev = df_shop_prev.groupby(["店铺", "商品类型"]).agg(
    数量_上月=("总滞销数量", "sum"),
    金额_上月=("总滞销金额", "sum")
).reset_index()

# 合并
shop_all = shop_total_curr.merge(shop_total_prev, on="店铺", how="left").fillna(0)
shop_type_all = shop_type_curr.merge(shop_type_prev, on=["店铺", "商品类型"], how="left").fillna(0)

total_qty = shop_all["总数量"].sum()
total_amt = shop_all["总金额"].sum()

# 环比函数
def fmt_fluc(curr, prev):
    curr_int = int(round(curr, 0))
    prev_int = int(round(prev, 0))
    diff = curr_int - prev_int
    if diff > 0:
        return f'<span style="color:#d32f2f">↑ +{diff:,}</span>', curr_int, prev_int
    elif diff < 0:
        return f'<span style="color:#2e7d32">↓ {diff:,}</span>', curr_int, prev_int
    else:
        return '<span style="color:#666">持平</span>', curr_int, prev_int

# 5. 一行五列文字总结
import plotly.express as px
shops = shop_all["店铺"].unique().tolist()

for idx in range(0, len(shops), 5):
    batch = shops[idx:idx+5]
    cols = st.columns(len(batch))
    for i, shop in enumerate(batch):
        d = shop_all[shop_all["店铺"] == shop].iloc[0]
        t = shop_type_all[shop_type_all["店铺"] == shop]

        qf, q, qp = fmt_fluc(d["总数量"], d["总数量_上月"])
        af, a, ap = fmt_fluc(d["总金额"], d["总金额_上月"])
        qpct = q / total_qty * 100 if total_qty else 0
        apct = a / total_amt * 100 if total_amt else 0

        # 年份品
        year_data = t[t["商品类型"] == "年份品"]
        yq = int(year_data["数量"].iloc[0]) if not year_data.empty else 0
        ya = int(year_data["金额"].iloc[0]) if not year_data.empty else 0
        yqp = int(year_data["数量_上月"].iloc[0]) if not year_data.empty else 0
        yap = int(year_data["金额_上月"].iloc[0]) if not year_data.empty else 0
        yqf, _, _ = fmt_fluc(yq, yqp)
        yaf, _, _ = fmt_fluc(ya, yap)
        yqpct = yq / q * 100 if q else 0
        yapct = ya / a * 100 if a else 0

        # 非年份品
        non_year_data = t[t["商品类型"] == "非年份品"]
        nq = int(non_year_data["数量"].iloc[0]) if not non_year_data.empty else 0
        na = int(non_year_data["金额"].iloc[0]) if not non_year_data.empty else 0
        nqp = int(non_year_data["数量_上月"].iloc[0]) if not non_year_data.empty else 0
        nap = int(non_year_data["金额_上月"].iloc[0]) if not non_year_data.empty else 0
        nqf, _, _ = fmt_fluc(nq, nqp)
        naf, _, _ = fmt_fluc(na, nap)
        nqpct = nq / q * 100 if q else 0
        napct = na / a * 100 if a else 0

        with cols[i]:
            st.markdown(f"""
**🏪 {shop}**
滞销数量：{q:,} 件（{qpct:.1f}%），环比 {qf}，上月：{qp:,} 件
<small style="color:#888;">
其中：
年份品数量：{yq:,}（{yqpct:.2f}%），环比 {yqf}，上月：{yqp:,} 件
非年份品数量：{nq:,}（{nqpct:.2f}%），环比 {nqf}，上月：{nqp:,} 件
</small>

滞销金额：{a:,} 元（{apct:.1f}%），环比 {af}，上月：{ap:,} 元
<small style="color:#888;">
其中：
年份品金额：{ya:,}（{yapct:.2f}%），环比 {yaf}，上月：{yap:,} 元
非年份品金额：{na:,}（{napct:.2f}%），环比 {naf}，上月：{nap:,} 元
</small>
""", unsafe_allow_html=True)

# 6. 下方一行两列饼图
st.divider()
c1, c2 = st.columns(2)
with c1:
    fig = px.pie(shop_all, names="店铺", values="总数量", title="店铺总滞销数量占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)
with c2:
    fig = px.pie(shop_all, names="店铺", values="总金额", title="店铺总滞销金额占比")
    fig.update_traces(textinfo="label+percent", textposition="inside")
    st.plotly_chart(fig, use_container_width=True)

