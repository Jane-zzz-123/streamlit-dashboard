# 导入依赖库
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import requests
from io import BytesIO

# -------------------------- 页面基础设置 --------------------------
st.set_page_config(
    page_title="采购交期监控看板",
    page_icon="📊",
    layout="wide"
)
st.title("📦 采购交期监控可视化看板")
st.markdown("---")


# -------------------------- 1. 在线读取 GitHub 数据 --------------------------
@st.cache_data(ttl=3600)  # 缓存数据，提升加载速度
def load_data():
    # GitHub 原始文件下载链接
    url = "https://github.com/Jane-zzz-123/streamlit-dashboard/raw/main/caigoushuju.xlsx"
    response = requests.get(url)
    excel_file = BytesIO(response.content)

    # 读取「源数据」sheet
    df = pd.read_excel(excel_file, sheet_name="源数据")

    # 筛选需要的列
    need_cols = [
        "是否加入看板", "采购单号", "下单时间", "品名", "SKU", "采购量", "待到货量",
        "到货量", "到货年月", "采购交期", "预计到货时间修改", "异常数据", "厂家",
        "厂家类目明细", "产品分类", "实际采购交期", "交期状态", "预计-实际交期的差值"
    ]
    df = df[need_cols]

    # 只保留 加入看板=是 的数据
    df = df[df["是否加入看板"] == "是"].reset_index(drop=True)

    # 数据清洗：时间/数值格式标准化
    df["下单时间"] = pd.to_datetime(df["下单时间"], errors="coerce")
    df["到货年月"] = df["到货年月"].astype(str).str.strip()
    df["实际采购交期"] = pd.to_numeric(df["实际采购交期"], errors="coerce")
    df["预计-实际交期的差值"] = pd.to_numeric(df["预计-实际交期的差值"], errors="coerce")

    return df


# 加载数据
df = load_data()

# -------------------------- 2. 全局筛选器：到货年月 --------------------------
# 获取所有可选择的年月并排序
year_month_list = sorted(df["到货年月"].dropna().unique())
selected_month = st.selectbox("📅 选择到货年月", year_month_list)

# 筛选当前选中月份数据
df_current = df[df["到货年月"] == selected_month].copy()


# 获取上月年月（用于环比计算）
@st.cache_data
def get_last_month(ym):
    try:
        current_dt = datetime.strptime(ym, "%Y%m")
        last_dt = current_dt - pd.DateOffset(months=1)
        return last_dt.strftime("%Y%m")
    except:
        return None


last_month = get_last_month(selected_month)
df_last = df[df["到货年月"] == last_month].copy() if last_month is not None else pd.DataFrame()

st.markdown("---")


# -------------------------- 工具函数：环比展示（红升绿降） --------------------------
def show_metric(label, current_val, last_val, suffix=""):
    # 空值处理
    if pd.isna(current_val): current_val = 0
    if pd.isna(last_val) or last_val == 0:
        st.metric(label=label, value=f"{current_val:.2f}{suffix}", delta="无上月数据")
        return

    # 计算环比
    chain_ratio = (current_val - last_val) / abs(last_val) * 100
    delta_text = f"{chain_ratio:.1f}%"

    # 样式：上升红，下降绿
    st.metric(
        label=label,
        value=f"{current_val:.2f}{suffix}",
        delta=delta_text
    )


# -------------------------- 3. ① 当月整体分析 - 指标卡片区域 --------------------------
st.subheader(f"📆 {selected_month} 月度整体分析")

# 计算当前月核心指标
current_po = df_current["采购单号"].nunique()  # PO单数
current_on_time = df_current[df_current["交期状态"].isin(["提前", "准时"])].shape[0]  # 准时/提前
current_overdue = df_current[df_current["交期状态"] == "逾期"].shape[0]  # 逾期
current_total = current_on_time + current_overdue
current_on_time_rate = current_on_time / current_total * 100 if current_total > 0 else 0  # 准时率
current_diff_avg = df_current["预计-实际交期的差值"].mean()  # 平均交期差值

# 计算上月核心指标
last_po = df_last["采购单号"].nunique() if not df_last.empty else 0
last_on_time = df_last[df_last["交期状态"].isin(["提前", "准时"])].shape[0] if not df_last.empty else 0
last_overdue = df_last[df_last["交期状态"] == "逾期"].shape[0] if not df_last.empty else 0
last_total = last_on_time + last_overdue
last_on_time_rate = last_on_time / last_total * 100 if last_total > 0 else 0
last_diff_avg = df_last["预计-实际交期的差值"].mean() if not df_last.empty else 0

# 5 个指标卡片布局
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    show_metric("PO单数", current_po, last_po)
with col2:
    show_metric("提前/准时订单", current_on_time, last_on_time)
with col3:
    show_metric("逾期订单", current_overdue, last_overdue)
with col4:
    show_metric("准时率", current_on_time_rate, last_on_time_rate, "%")
with col5:
    show_metric("平均交期差值", current_diff_avg, last_diff_avg, "天")

st.markdown("---")

# -------------------------- 月度对比总结文字 --------------------------
st.subheader("📝 本月对比上月总结")
summary = ""
if df_last.empty:
    summary = "⚠️ 无上月数据，无法进行环比对比"
else:
    # PO 对比
    po_trend = "上升" if current_po > last_po else "下降"
    # 准时率对比
    rate_trend = "提升" if current_on_time_rate > last_on_time_rate else "下降"
    # 逾期对比
    overdue_trend = "增加" if current_overdue > last_overdue else "减少"
    # 交期差值
    diff_trend = "延长" if current_diff_avg > last_diff_avg else "缩短"

    summary = f"""
    本月{selected_month}共{current_po}单，较上月{po_trend}；
    准时率{current_on_time_rate:.1f}%，较上月{rate_trend}；
    逾期订单{current_overdue}单，较上月{overdue_trend}；
    平均交期差值{current_diff_avg:.1f}天，较上月{diff_trend}。
    """
st.info(summary)
st.markdown("---")

# -------------------------- 4. ② 图表区域 --------------------------
st.subheader("📊 交期状态可视化分析")
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("#### 当月准时率占比")
    if current_total > 0:
        pie_data = [current_on_time, current_overdue]
        pie_labels = ["提前/准时", "逾期"]
        pie_colors = ["#2E8B57", "#DC143C"]

        fig1, ax1 = plt.subplots()
        ax1.pie(pie_data, labels=pie_labels, autopct="%1.1f%%", colors=pie_colors, startangle=90)
        ax1.axis("equal")
        st.pyplot(fig1)
    else:
        st.warning("当月无有效订单数据")

with chart_col2:
    st.markdown("#### 交期状态订单分布")
    if current_total > 0:
        fig2, ax2 = plt.subplots()
        status_counts = df_current["交期状态"].value_counts().reindex(["提前", "准时", "逾期"], fill_value=0)
        ax2.bar(status_counts.index, status_counts.values, color=["#2E8B57", "#32CD32", "#DC143C"])
        ax2.set_ylabel("订单数量")
        st.pyplot(fig2)
    else:
        st.warning("当月无有效订单数据")

# 交期差值分布直方图
st.markdown("#### 预计-实际交期差值分布")
if not df_current["预计-实际交期的差值"].dropna().empty:
    fig3, ax3 = plt.subplots()
    ax3.hist(df_current["预计-实际交期的差值"].dropna(), bins=15, color="#4682B4", edgecolor="black")
    ax3.set_xlabel("交期差值（天）")
    ax3.set_ylabel("订单数量")
    st.pyplot(fig3)
else:
    st.warning("当月无交期差值数据")

st.markdown("---")

# -------------------------- 5. ③ 交期数据明细表 --------------------------
st.subheader("📋 交期数据明细")
# 展示列
table_cols = [
    "到货年月", "交期状态", "厂家", "下单时间", "采购单号", "品名", "SKU",
    "厂家类目明细", "产品分类", "采购交期", "实际采购交期", "预计-实际交期的差值"
]

# 排序规则：1.逾期优先 2.采购量降序
df_table = df_current.copy()
df_table["逾期排序"] = df_table["交期状态"].apply(lambda x: 0 if x == "逾期" else 1)
df_table = df_table.sort_values(by=["逾期排序", "采购量"], ascending=[True, False])

# 展示表格
st.dataframe(df_table[table_cols], use_container_width=True, height=300)
st.markdown("---")

# -------------------------- 6. 厂家月度统计汇总表 --------------------------
st.subheader("🏭 各厂家交期统计汇总")
if not df_current.empty:
    factory_agg = df_current.groupby("厂家").agg(
        PO单数=("采购单号", "nunique"),
        提前准时订单=("交期状态", lambda x: x.isin(["提前", "准时"]).sum()),
        逾期订单=("交期状态", lambda x: (x == "逾期").sum())
    ).reset_index()

    factory_agg["总订单"] = factory_agg["提前准时订单"] + factory_agg["逾期订单"]
    factory_agg["准时率(%)"] = (factory_agg["提前准时订单"] / factory_agg["总订单"] * 100).round(1)
    factory_agg["逾期率(%)"] = (factory_agg["逾期订单"] / factory_agg["总订单"] * 100).round(1)

    # 交期指标
    diff_agg = df_current.groupby("厂家").agg(
        平均交期差值=("预计-实际交期的差值", "mean"),
        最短实际交期=("实际采购交期", "min"),
        最长实际交期=("实际采购交期", "max")
    ).round(1).reset_index()

    factory_final = pd.merge(factory_agg, diff_agg, on="厂家")
    factory_final = factory_final.sort_values("PO单数", ascending=False)

    st.dataframe(factory_final, use_container_width=True, height=300)
else:
    st.warning("当月无厂家数据")

st.markdown("---")

# -------------------------- 7. 逾期厂家专项分析 --------------------------
st.subheader("⚠️ 逾期厂家专项分析")
df_overdue = df_current[df_current["交期状态"] == "逾期"].copy()

if df_overdue.empty:
    st.success("✅ 本月无逾期订单！")
else:
    # 逾期厂家统计
    overdue_factory_analysis = df_overdue.groupby("厂家").agg(
        逾期订单数=("采购单号", "nunique"),
        平均逾期交期差值=("预计-实际交期的差值", "mean"),
        涉及SKU数=("SKU", "nunique")
    ).round(1).sort_values("逾期订单数", ascending=False).reset_index()

    st.markdown("#### 逾期厂家明细统计")
    st.dataframe(overdue_factory_analysis, use_container_width=True)

    st.markdown("#### 逾期原始订单明细")
    st.dataframe(df_overdue[table_cols], use_container_width=True, height=250)

st.markdown("---")
st.success("✅ 看板加载完成！数据实时同步 GitHub 源文件")