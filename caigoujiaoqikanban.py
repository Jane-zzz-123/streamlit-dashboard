import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# -------------------------- 页面配置 --------------------------
st.set_page_config(page_title="采购交期看板", layout="wide")
st.title("📊 采购交期准时率 & 供应商产能监控看板")

# -------------------------- 读取数据（你的GitHub链接） --------------------------
@st.cache_data
def load_data():
    url = "https://github.com/Jane-zzz-123/streamlit-dashboard/raw/main/caigoushuju.xlsx"
    df = pd.read_excel(url, sheet_name="源数据")

    # 只取需要加入看板的数据
    df = df[df["是否加入看板"] == "是"].copy()

    # 时间列标准化
    df["下单时间"] = pd.to_datetime(df["下单时间"], errors="coerce")
    df["采购交期"] = pd.to_datetime(df["采购交期"], errors="coerce")
    df["实际采购交期"] = pd.to_datetime(df["实际采购交期"], errors="coerce")

    # 计算交期偏差天数（核心！）
    # 实际 - 计划：正数=逾期天数，负数=提前天数
    df["交期偏差天数"] = (df["实际采购交期"] - df["采购交期"]).dt.days

    # 下单年月（用于产能分析）
    df["下单年月"] = df["下单时间"].dt.to_period("M").astype(str)
    return df

df = load_data()

# -------------------------- 侧边栏筛选 --------------------------
st.sidebar.header("🔍 筛选条件")
factories = st.sidebar.multiselect("选择厂家", sorted(df["厂家"].dropna().unique()))
product_cates = st.sidebar.multiselect("产品分类", sorted(df["产品分类"].dropna().unique()))
arrive_months = sorted(df["到货年月"].dropna().astype(str).unique())
select_arrive_month = st.sidebar.multiselect("到货年月", arrive_months)

# 应用筛选
df_filter = df.copy()
if factories:
    df_filter = df_filter[df_filter["厂家"].isin(factories)]
if product_cates:
    df_filter = df_filter[df_filter["产品分类"].isin(product_cates)]
if select_arrive_month:
    df_filter = df_filter[df_filter["到货年月"].astype(str).isin(select_arrive_month)]

# ==============================================================================
# 🎯 一、顶部核心整体情况（你要的最开头展示）
# ==============================================================================
st.subheader("🎯 整体交期概况")

total_po = len(df_filter)
on_time_num = len(df_filter[df_filter["交期状态"] == "准时"])
early_num = len(df_filter[df_filter["交期状态"] == "提前"])
late_num = len(df_filter[df_filter["交期状态"] == "逾期"])
on_time_all_num = on_time_num + early_num
on_time_rate = on_time_all_num / total_po * 100 if total_po > 0 else 0

# 平均偏差天数
avg_diff_days = df_filter["交期偏差天数"].mean() if total_po > 0 else 0
# 平均逾期天数（只算逾期订单）
avg_late_days = df_filter[df_filter["交期偏差天数"] > 0]["交期偏差天数"].mean()
# 平均提前天数（只算提前订单）
avg_early_days = df_filter[df_filter["交期偏差天数"] < 0]["交期偏差天数"].mean()

row1 = st.columns(5)
row1[0].metric("总PO单量", total_po)
row1[1].metric("提前订单", early_num)
row1[2].metric("准时订单", on_time_num)
row1[3].metric("逾期订单", late_num)
row1[4].metric("整体准时率", f"{on_time_rate:.1f}%")

row2 = st.columns(3)
row2[0].metric("平均交期偏差天数", f"{avg_diff_days:.1f} 天")
row2[1].metric("平均逾期天数(仅逾期)", f"{avg_late_days:.1f} 天" if not pd.isna(avg_late_days) else "0")
row2[2].metric("平均提前天数(仅提前)", f"{avg_early_days:.1f} 天" if not pd.isna(avg_early_days) else "0")

st.divider()

# ==============================================================================
# 🏭 二、厂家维度 + 厂家类目明细下钻
# ==============================================================================
st.subheader("🏭 各厂家交期表现 & 类目明细分析")

# 厂家整体准时率
factory_stat = df_filter.groupby("厂家").agg(
    总订单=("采购单号", "count"),
    准时订单=("交期状态", lambda x: ((x == "准时") | (x == "提前")).sum()),
    平均偏差天数=("交期偏差天数", "mean"),
).reset_index()
factory_stat["准时率%"] = factory_stat["准时订单"] / factory_stat["总订单"] * 100
factory_stat = factory_stat.sort_values("准时率%", ascending=False)
st.dataframe(factory_stat, use_container_width=True)

# 厂家类目明细（蜂窝/横幅等）下钻分析
st.markdown("#### 🔎 厂家类目明细交期（看哪类产品拖延）")
factory_detail_stat = df_filter.groupby(["厂家", "厂家类目明细"]).agg(
    总订单=("采购单号", "count"),
    准时订单=("交期状态", lambda x: ((x == "准时") | (x == "提前")).sum()),
    平均偏差天数=("交期偏差天数", "mean"),
).reset_index()
factory_detail_stat["准时率%"] = factory_detail_stat["准时订单"] / factory_detail_stat["总订单"] * 100
st.dataframe(factory_detail_stat, use_container_width=True)

st.divider()

# ==============================================================================
# 📦 三、产品分类跨厂家对比
# ==============================================================================
st.subheader("📦 产品分类跨厂家准时率对比")
product_cross = df_filter.groupby(["产品分类", "厂家"]).agg(
    总订单=("采购单号", "count"),
    准时订单=("交期状态", lambda x: ((x == "准时") | (x == "提前")).sum()),
).reset_index()
product_cross["准时率%"] = product_cross["准时订单"] / product_cross["总订单"] * 100
st.dataframe(product_cross, use_container_width=True)

st.divider()

# ==============================================================================
# ⚙️ 四、供应商产能负荷分析（按月下单量 VS 历史产能）
# ==============================================================================
st.subheader("⚙️ 供应商产能负荷分析（下单量 VS 月均产能）")

# 1. 厂家+类目 历史月均到货量 = 基准产能
capacity = df_filter.groupby(["厂家", "厂家类目明细"]).agg(
    月均到货量=("到货量", "mean"),
    历史最大到货量=("到货量", "max")
).reset_index()

# 2. 每月实际下单量
monthly_order = df_filter.groupby(["厂家", "厂家类目明细", "下单年月"]).agg(
    当月下单总量=("采购量", "sum")
).reset_index()

# 3. 合并计算负荷率
load_df = pd.merge(monthly_order, capacity, on=["厂家", "厂家类目明细"])
load_df["负荷率%"] = load_df["当月下单总量"] / load_df["月均到货量"] * 100
load_df["负荷状态"] = np.where(
    load_df["负荷率%"] > 120, "🔴 过载",
    np.where(load_df["负荷率%"] > 100, "🟡 偏紧", "🟢 正常")
)

st.dataframe(load_df, use_container_width=True)

# 过载预警
st.markdown("#### ⚠️ 产能过载预警清单")
overload = load_df[load_df["负荷状态"] == "🔴 过载"]
if not overload.empty:
    st.dataframe(overload, use_container_width=True)
else:
    st.success("✅ 目前无供应商产能过载")

st.divider()

# ==============================================================================
# 📝 五、逾期订单明细
# ==============================================================================
st.subheader("📝 逾期订单明细")
late_list = df_filter[df_filter["交期状态"] == "逾期"][[
    "采购单号", "厂家", "厂家类目明细", "产品分类",
    "采购交期", "实际采购交期", "交期偏差天数"
]].sort_values("交期偏差天数", ascending=False)
st.dataframe(late_list, use_container_width=True)

st.caption("✅ 数据已自动从 GitHub 加载 | 仅统计「是否加入看板=是」的订单")