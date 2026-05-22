import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import BytesIO
import base64
import math

# ====================== 页面基础配置 ======================
st.set_page_config(page_title="物流成本分析看板", layout="wide", initial_sidebar_state="expanded")

st.title("📊 物流成本分析")

# ====================== 1. 加载数据 ======================
@st.cache_data(show_spinner="加载成本数据中...")
def load_cost_data():
    url = "https://raw.githubusercontent.com/Jane-zzz-123/Logistics/main/CAE.xlsx"
    df_cost = pd.read_excel(url, sheet_name="数据")

    need_cols = ["周期", "月份", "目的仓", "仓库", "区域", "实际物流方式", "货代", "货代渠道", "重量", "报关费",
                 "运输方式", "总费用", "总运费", "入库配置费折算RMB"]
    df_cost = df_cost[[col for col in need_cols if col in df_cost.columns]]

    # 数据清洗
    df_cost = df_cost.dropna(subset=["周期", "实际物流方式", "重量"])
    df_cost = df_cost[(df_cost["重量"] > 0)]

    # 费用字段处理
    for c in ["总费用", "总运费", "入库配置费折算RMB", "报关费"]:
        if c in df_cost.columns:
            df_cost[c] = pd.to_numeric(df_cost[c], errors="coerce").fillna(0)
        else:
            df_cost[c] = 0

    # 重算总费用
    df_cost["总费用"] = df_cost["总运费"] + df_cost["入库配置费折算RMB"]

    # 时间字段标准化
    df_cost["周期"] = pd.to_numeric(df_cost["周期"], errors="coerce").astype(int)
    df_cost["月份"] = pd.to_numeric(df_cost["月份"], errors="coerce").astype(int)
    df_cost = df_cost.sort_values("周期").reset_index(drop=True)
    return df_cost

df_cost = load_cost_data()

# ====================== 全局配置 ======================
# 颜色映射
color_map = {
    "空派": "#1f77b4",        # 蓝色
    "以星特快": "#2ca02c",    # 绿色
    "以星": "#ff7f0e",        # 橙色
    "正班": "#7f7f7f",        # 灰色
    "普船": "#ffdd00"         # 黄色
}
default_color = "#9467bd"

# 指标卡背景色
card_bg_map = {
    "总费用": "#f8f9fa",
    "总运费": "#e8f5e9",
    "入库配置费": "#ffebee",
    "报关费": "#f3e5f5",
    "总重量": "#e3f2fd"
}

# ====================== 2. 视图模式 & 筛选器 ======================
view_mode = st.radio("筛选维度", ["按周期", "按月份"], horizontal=True)

with st.expander("🔎 筛选条件", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        if view_mode == "按周期":
            period_list = sorted(df_cost["周期"].unique())
            max_p = max(period_list) if len(period_list) else 0
            default_val = [p for p in period_list if p >= max_p - 3] if len(period_list) >=4 else period_list
            selected = st.multiselect("周期", period_list, default=default_val)
        else:
            month_list = sorted(df_cost["月份"].dropna().unique())
            default_val = month_list[-3:] if len(month_list) >= 3 else month_list
            selected = st.multiselect("月份", month_list, default=default_val)

    with col2:
        area_list = ["全部"] + sorted(df_cost["区域"].dropna().unique())
        selected_area = st.selectbox("区域", area_list)

# ====================== 3. 筛选后数据处理 ======================
df = df_cost.copy()
group_col = "周期" if view_mode == "按周期" else "月份"

# 时间筛选
if view_mode == "按周期":
    df = df[df["周期"].isin(selected)] if selected else df
else:
    df = df[df["月份"].isin(selected)] if selected else df

# 区域筛选
if selected_area != "全部":
    df = df[df["区域"] == selected_area]

if df.empty:
    st.warning("无数据")
    st.stop()

# 最新周期/月份 & 上月数据
latest_period = max(selected) if selected else max(df[group_col])
prev_period = sorted(df[group_col].unique())[-2] if len(df[group_col].unique()) >=2 else latest_period

# ====================== 4. 环比计算工具函数 ======================
def get_vs_prev(latest_val, prev_val):
    diff = latest_val - prev_val
    pct = diff / prev_val * 100 if prev_val != 0 else 0
    sign = "↓" if diff < 0 else "↑" if diff > 0 else "→"
    color = "green" if diff < 0 else "red" if diff > 0 else "#888"
    return sign, color, diff, pct

# ==============================================================================
# 🔴 第一部分：核心指标卡（完全复刻你的样式）
# ==============================================================================
st.markdown("## 🎯 核心指标")
st.markdown(f"**统计周期：{view_mode} {latest_period}**")

# 计算最新值 & 上月值
latest_data = df[df[group_col] == latest_period]
prev_data = df[df[group_col] == prev_period] if prev_period in df[group_col].values else pd.DataFrame()

# 核心指标
metrics = [
    {
        "name": "总费用",
        "latest": latest_data["总费用"].sum(),
        "prev": prev_data["总费用"].sum() if not prev_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["总费用"]
    },
    {
        "name": "总运费",
        "latest": latest_data["总运费"].sum(),
        "prev": prev_data["总运费"].sum() if not prev_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["总运费"]
    },
    {
        "name": "入库配置费",
        "latest": latest_data["入库配置费折算RMB"].sum(),
        "prev": prev_data["入库配置费折算RMB"].sum() if not prev_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["入库配置费"]
    },
    {
        "name": "报关费",
        "latest": latest_data["报关费"].sum(),
        "prev": prev_data["报关费"].sum() if not prev_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["报关费"]
    },
    {
        "name": "总重量",
        "latest": latest_data["重量"].sum(),
        "prev": prev_data["重量"].sum() if not prev_data.empty else 0,
        "unit": "kg",
        "bg": card_bg_map["总重量"]
    }
]

# 渲染5张指标卡
cols = st.columns(5)
for i, metric in enumerate(metrics):
    with cols[i]:
        sign, color, diff, pct = get_vs_prev(metric["latest"], metric["prev"])
        # 自定义卡片HTML
        card_html = f"""
        <div style="background-color:{metric['bg']}; padding:20px; border-radius:12px; text-align:center; height:220px; display:flex; flex-direction:column; justify-content:center; align-items:center;">
            <div style="font-size:28px; font-weight:bold; margin-bottom:15px;">{metric['name']}</div>
            <div style="font-size:42px; font-weight:900; margin-bottom:15px;">{metric['unit']}{metric['latest']:,.0f}</div>
            <div style="font-size:20px; color:{color};">
                {sign} {abs(diff):,.0f} (上月: {metric['unit']}{metric['prev']:,.0f})
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

st.markdown("---")

# ==============================================================================
# 📊 第二部分：整体成本趋势（一行五列，数值100%完整显示）
# ==============================================================================
st.markdown("## 📈 整体趋势（与核心指标卡一一对应）")

# 先计算趋势数据
df_trend = df.groupby(group_col).agg(
    总费用=("总费用", "sum"),
    总运费=("总运费", "sum"),
    入库配置费=("入库配置费折算RMB", "sum"),
    报关费=("报关费", "sum"),
    总重量=("重量", "sum")
).reset_index()

# 强制时间列为整数，彻底解决小数点问题
df_trend[group_col] = df_trend[group_col].astype(int).astype(str)

# 一行五列，和上面5张卡片完美对应
t1, t2, t3, t4, t5 = st.columns(5)

# 1. 总费用趋势
with t1:
    fig1 = px.bar(
        df_trend,
        x=group_col,
        y="总费用",
        color_discrete_sequence=["#1f77b4"],
        title="总费用趋势"
    )
    # 柱形顶部显示数值，千分位格式化
    fig1.update_traces(
        text=df_trend["总费用"].apply(lambda x: f"¥{x:,.0f}"),
        textposition="outside",
        textfont=dict(size=12)  # 字体大小适配
    )
    # 关键优化：增大图表高度 + Y轴范围向上预留20%空间，给数值留位置
    max_val1 = df_trend["总费用"].max()
    fig1.update_layout(
        height=400,  # 图表高度从350→400，给数值留垂直空间
        showlegend=False,
        yaxis_title="金额(¥)",
        yaxis=dict(range=[0, max_val1 * 1.2]),  # Y轴最大值放大20%，顶部不会截断
        margin=dict(l=20, r=20, t=60, b=40)  # 调整上下边距，顶部数值不被标题挡住
    )
    st.plotly_chart(fig1, use_container_width=True)

# 2. 总运费趋势
with t2:
    fig2 = px.bar(
        df_trend,
        x=group_col,
        y="总运费",
        color_discrete_sequence=["#ff7f0e"],
        title="总运费趋势"
    )
    fig2.update_traces(
        text=df_trend["总运费"].apply(lambda x: f"¥{x:,.0f}"),
        textposition="outside",
        textfont=dict(size=12)
    )
    max_val2 = df_trend["总运费"].max()
    fig2.update_layout(
        height=400,
        showlegend=False,
        yaxis_title="金额(¥)",
        yaxis=dict(range=[0, max_val2 * 1.2]),
        margin=dict(l=20, r=20, t=60, b=40)
    )
    st.plotly_chart(fig2, use_container_width=True)

# 3. 入库配置费趋势
with t3:
    fig3 = px.bar(
        df_trend,
        x=group_col,
        y="入库配置费",
        color_discrete_sequence=["#2ca02c"],
        title="入库配置费趋势"
    )
    fig3.update_traces(
        text=df_trend["入库配置费"].apply(lambda x: f"¥{x:,.0f}"),
        textposition="outside",
        textfont=dict(size=12)
    )
    max_val3 = df_trend["入库配置费"].max()
    fig3.update_layout(
        height=400,
        showlegend=False,
        yaxis_title="金额(¥)",
        yaxis=dict(range=[0, max_val3 * 1.2]),
        margin=dict(l=20, r=20, t=60, b=40)
    )
    st.plotly_chart(fig3, use_container_width=True)

# 4. 报关费趋势
with t4:
    fig4 = px.bar(
        df_trend,
        x=group_col,
        y="报关费",
        color_discrete_sequence=["#d62728"],
        title="报关费趋势"
    )
    fig4.update_traces(
        text=df_trend["报关费"].apply(lambda x: f"¥{x:,.0f}"),
        textposition="outside",
        textfont=dict(size=12)
    )
    max_val4 = df_trend["报关费"].max()
    fig4.update_layout(
        height=400,
        showlegend=False,
        yaxis_title="金额(¥)",
        yaxis=dict(range=[0, max_val4 * 1.2]),
        margin=dict(l=20, r=20, t=60, b=40)
    )
    st.plotly_chart(fig4, use_container_width=True)

# 5. 总重量趋势
with t5:
    fig5 = px.bar(
        df_trend,
        x=group_col,
        y="总重量",
        color_discrete_sequence=["#9467bd"],
        title="总重量趋势"
    )
    fig5.update_traces(
        text=df_trend["总重量"].apply(lambda x: f"{x:,.0f}kg"),
        textposition="outside",
        textfont=dict(size=12)
    )
    max_val5 = df_trend["总重量"].max()
    fig5.update_layout(
        height=400,
        showlegend=False,
        yaxis_title="重量(kg)",
        yaxis=dict(range=[0, max_val5 * 1.2]),
        margin=dict(l=20, r=20, t=60, b=40)
    )
    st.plotly_chart(fig5, use_container_width=True)

st.markdown("---")

# ==============================================================================
# 💰 第四部分：单价 & 总金额明细分析
# ==============================================================================
st.markdown("## 💰 单价 & 总金额明细（按物流方式）")

# 计算函数
def calc_unit_price(df_filtered, value_col):
    df_sum = df_filtered.groupby([group_col, "实际物流方式"], as_index=False).agg(
        总重量=("重量", "sum"),
        总金额=(value_col, "sum")
    )
    df_sum["折算单价"] = (df_sum["总金额"] / df_sum["总重量"]).round(4)
    df_sum = df_sum.sort_values(["实际物流方式", group_col]).reset_index(drop=True)
    df_sum["上期单价"] = df_sum.groupby("实际物流方式")["折算单价"].shift(1)
    df_sum["环比差值"] = (df_sum["折算单价"] - df_sum["上期单价"]).round(2)
    df_sum["环比幅度"] = np.where(
        df_sum["上期单价"] > 0, (df_sum["环比差值"] / df_sum["上期单价"] * 100).round(2), 0
    )
    return df_sum

def calc_total_amount(df_filtered, value_col):
    df_sum = df_filtered.groupby([group_col, "实际物流方式"], as_index=False).agg(
        总金额=(value_col, "sum")
    )
    df_sum = df_sum.sort_values(["实际物流方式", group_col]).reset_index(drop=True)
    df_sum["上期金额"] = df_sum.groupby("实际物流方式")["总金额"].shift(1)
    df_sum["环比差值"] = (df_sum["总金额"] - df_sum["上期金额"]).round(2)
    df_sum["环比幅度"] = np.where(
        df_sum["上期金额"] > 0, (df_sum["环比差值"] / df_sum["上期金额"] * 100).round(2), 0
    )
    return df_sum

# 计算3组指标
# 总费用
df_cost_unit = calc_unit_price(df, "总费用")
df_cost_amt = calc_total_amount(df, "总费用")
# 总运费
df_freight_unit = calc_unit_price(df, "总运费")
df_freight_amt = calc_total_amount(df, "总运费")
# 入库配置费
df_storage_unit = calc_unit_price(df, "入库配置费折算RMB")
df_storage_amt = calc_total_amount(df, "入库配置费折算RMB")

# 渲染函数：图表+表格完整展示
def render_detail_section(col, title, df_unit, df_amt):
    with col:
        st.markdown(f"### {title}")
        all_logi = sorted(df["实际物流方式"].unique())
        sorted_vals = sorted(df_unit[group_col].unique())

        # 单价图表
        st.markdown("##### 📈 单价趋势（元/kg）")
        df_unit["x_str"] = df_unit[group_col].astype(str)
        fig_unit = px.line(
            df_unit, x="x_str", y="折算单价", color="实际物流方式",
            color_discrete_map={k: color_map.get(k, default_color) for k in all_logi},
            markers=True
        )
        fig_unit.update_xaxes(type="category")
        fig_unit.update_layout(height=250, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_unit, use_container_width=True)

        # 单价明细表
        st.markdown("##### 📋 单价明细表")
        unit_data_map = {(str(r[group_col]), r["实际物流方式"]): r for _, r in df_unit.iterrows()}
        unit_table = "<table style='width:100%;border-collapse:collapse;font-size:12px;text-align:center'>"
        unit_table += f"<tr style='background:#f0f2f6'><td>{group_col}</td>"
        for l in all_logi: unit_table += f"<td style='border:1px solid #ddd;padding:6px'>{l}</td>"
        unit_table += "</tr>"
        for v in sorted_vals:
            unit_table += f"<tr><td style='border:1px solid #ddd;padding:6px'>{v}</td>"
            for logi in all_logi:
                key = (str(v), logi)
                if key not in unit_data_map:
                    unit_table += "<td style='border:1px solid #ddd;padding:6px'>-</td>"
                    continue
                r = unit_data_map[key]
                p = r["折算单价"]
                diff = r["环比差值"]
                if pd.isna(diff):
                    txt, color = "首期", "#888"
                else:
                    sign = "+" if diff > 0 else ""
                    txt = f"{sign}{diff:.2f}"
                    color = "red" if diff > 0 else "green"
                cell = f"{p:.2f}<br><small style='color:{color}'>{txt}</small>"
                unit_table += f"<td style='border:1px solid #ddd;padding:6px'>{cell}</td>"
            unit_table += "</tr>"
        unit_table += "</table>"
        st.markdown(unit_table, unsafe_allow_html=True)

        # 分割线
        st.markdown("---")

        # 总金额图表
        st.markdown("##### 💰 总金额趋势（元）")
        df_amt["x_str"] = df_amt[group_col].astype(str)
        fig_amt = px.line(
            df_amt, x="x_str", y="总金额", color="实际物流方式",
            color_discrete_map={k: color_map.get(k, default_color) for k in all_logi},
            markers=True
        )
        fig_amt.update_xaxes(type="category")
        fig_amt.update_layout(height=250, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_amt, use_container_width=True)

        # 总金额明细表
        st.markdown("##### 📋 总金额明细表")
        amt_data_map = {(str(r[group_col]), r["实际物流方式"]): r for _, r in df_amt.iterrows()}
        amt_table = "<table style='width:100%;border-collapse:collapse;font-size:12px;text-align:center'>"
        amt_table += f"<tr style='background:#f0f2f6'><td>{group_col}</td>"
        for l in all_logi: amt_table += f"<td style='border:1px solid #ddd;padding:6px'>{l}</td>"
        amt_table += "</tr>"
        for v in sorted_vals:
            amt_table += f"<tr><td style='border:1px solid #ddd;padding:6px'>{v}</td>"
            for logi in all_logi:
                key = (str(v), logi)
                if key not in amt_data_map:
                    amt_table += "<td style='border:1px solid #ddd;padding:6px'>-</td>"
                    continue
                r = amt_data_map[key]
                a = r["总金额"]
                diff = r["环比差值"]
                if pd.isna(diff):
                    txt, color = "首期", "#888"
                else:
                    sign = "+" if diff > 0 else ""
                    txt = f"{sign}{diff:,.0f}"
                    color = "red" if diff > 0 else "green"
                cell = f"{a:,.0f}<br><small style='color:{color}'>{txt}</small>"
                amt_table += f"<td style='border:1px solid #ddd;padding:6px'>{cell}</td>"
            amt_table += "</tr>"
        amt_table += "</table>"
        st.markdown(amt_table, unsafe_allow_html=True)

# 渲染3列明细
col1, col2, col3 = st.columns(3)
render_detail_section(col1, "💰 总费用", df_cost_unit, df_cost_amt)
render_detail_section(col2, "🚚 总运费", df_freight_unit, df_freight_amt)
render_detail_section(col3, "📦 入库配置费", df_storage_unit, df_storage_amt)

st.caption("🔴 上涨｜🟢 下降｜单价 = 总金额 ÷ 总重量｜总金额 = 直接汇总求和")

st.markdown("## 📊占比对比柱形图")

# 1. 数据准备（新增单价计算）
df_pie = df.groupby([group_col, "实际物流方式"], as_index=False).agg(
    总费用=("总费用", "sum"),
    总重量=("重量", "sum")
)
# 新增单价 = 总费用 / 总重量，避免除以0
df_pie["单价"] = df_pie.apply(lambda x: x["总费用"] / x["总重量"] if x["总重量"] > 0 else 0, axis=1)

# 计算各维度占比
df_pie["周期总费用"] = df_pie.groupby(group_col)["总费用"].transform("sum")
df_pie["费用占比"] = (df_pie["总费用"] / df_pie["周期总费用"] * 100).round(2)
df_pie["周期总重量"] = df_pie.groupby(group_col)["总重量"].transform("sum")
df_pie["重量占比"] = (df_pie["总重量"] / df_pie["周期总重量"] * 100).round(2)
df_pie["周期总单价"] = df_pie.groupby(group_col)["单价"].transform("mean")
df_pie["单价占比"] = (df_pie["单价"] / df_pie["周期总单价"] * 100).round(2)

# 动态判断 周期 / 月份
dim_label = "周" if group_col == "周期" else "月"

# 2. 渠道专属渐变配色
logi_gradient_map = {
    "红单": ["#ff9999", "#ff6666", "#cc0000"],
    "空派": ["#b3d9ff", "#66a3ff", "#0066cc"],
    "普船": ["#b3f0c6", "#66cc88", "#009944"],
    "以星": ["#ffd9b3", "#ff9933", "#cc6600"],
    "以星特快": ["#fff0b3", "#ffdd66", "#cc9900"],
}
default_gradient = ["#f0e6ff", "#c488ff", "#8822cc"]

# 3. 强制X轴渠道顺序
fixed_order = ["红单", "空派", "普船", "以星", "以星特快"]
other_logi = [logi for logi in df_pie["实际物流方式"].unique() if logi not in fixed_order]
final_order = fixed_order + sorted(other_logi)
df_pie["实际物流方式"] = pd.Categorical(
    df_pie["实际物流方式"],
    categories=final_order,
    ordered=True
)

# 4. 自动获取周期顺序 & 数量
period_list = sorted(df_pie[group_col].unique())
num_periods = len(period_list)

# ====================== 第一部分：全宽图表 ======================
st.markdown("### 🔁 占比变化对比")
fig = go.Figure()
for i, period in enumerate(period_list):
    df_period = df_pie[df_pie[group_col] == period].copy()
    bar_colors = [logi_gradient_map.get(logi, default_gradient)[min(i, 2)] for logi in df_period["实际物流方式"]]
    fig.add_trace(go.Bar(
        x=df_period["实际物流方式"],
        y=df_period["费用占比"],
        name=f"{period}",
        marker_color=bar_colors,
        text=df_period.apply(lambda row: f"{row[group_col]}{dim_label}<br>{row['费用占比']:.2f}%", axis=1),
        textposition="outside",
        textfont=dict(size=10),
        width=0.7 / num_periods
    ))
fig.update_layout(
    height=550,
    barmode="group",
    yaxis_title="占比 (%)",
    xaxis_title="实际物流方式",
    xaxis=dict(categoryorder="array", categoryarray=final_order),
    showlegend=False,
    margin=dict(l=20, r=20, t=40, b=60),
    title=f"各物流方式{group_col}占比变化",
    title_x=0.5,
    bargap=0.3,
    bargroupgap=0.1
)
st.plotly_chart(fig, use_container_width=True)

# ====================== 第二部分：双层表头明细表格 ======================
st.markdown("### 📋 全维度明细")

# 1. 构建表格数据，1:1复刻Excel结构
table_data = []
for logi in final_order:
    for period in period_list:
        row = {
            "实际物流方式": logi,
            "周期/月份": f"{period}{dim_label}"
        }

        # 获取本期数据
        current_data = df_pie[(df_pie[group_col] == period) & (df_pie["实际物流方式"] == logi)]
        current_amount = current_data["总费用"].values[0] if len(current_data) > 0 else 0
        current_weight = current_data["总重量"].values[0] if len(current_data) > 0 else 0
        current_price = current_data["单价"].values[0] if len(current_data) > 0 else 0
        current_amount_ratio = current_data["费用占比"].values[0] if len(current_data) > 0 else 0
        current_weight_ratio = current_data["重量占比"].values[0] if len(current_data) > 0 else 0
        current_price_ratio = current_data["单价占比"].values[0] if len(current_data) > 0 else 0

        # 计算环比差值
        period_idx = period_list.index(period)
        if period_idx == 0:
            amount_diff = "→ 0.00"
            amount_ratio_diff = "→ 0.00%"
            weight_diff = "→ 0.00"
            weight_ratio_diff = "→ 0.00%"
            price_diff = "→ 0.00"
            price_ratio_diff = "→ 0.00%"
        else:
            prev_period = period_list[period_idx - 1]
            prev_data = df_pie[(df_pie[group_col] == prev_period) & (df_pie["实际物流方式"] == logi)]
            prev_amount = prev_data["总费用"].values[0] if len(prev_data) > 0 else 0
            prev_weight = prev_data["总重量"].values[0] if len(prev_data) > 0 else 0
            prev_price = prev_data["单价"].values[0] if len(prev_data) > 0 else 0
            prev_amount_ratio = prev_data["费用占比"].values[0] if len(prev_data) > 0 else 0
            prev_weight_ratio = prev_data["重量占比"].values[0] if len(prev_data) > 0 else 0
            prev_price_ratio = prev_data["单价占比"].values[0] if len(prev_data) > 0 else 0

            # 计算差值
            amount_diff_val = current_amount - prev_amount
            amount_ratio_diff_val = current_amount_ratio - prev_amount_ratio
            weight_diff_val = current_weight - prev_weight
            weight_ratio_diff_val = current_weight_ratio - prev_weight_ratio
            price_diff_val = current_price - prev_price
            price_ratio_diff_val = current_price_ratio - prev_price_ratio

            # 格式化差值
            amount_diff = f"{'↑' if amount_diff_val > 0 else '↓' if amount_diff_val < 0 else '→'} {amount_diff_val:,.2f}"
            amount_ratio_diff = f"{'↑' if amount_ratio_diff_val > 0 else '↓' if amount_ratio_diff_val < 0 else '→'} {amount_ratio_diff_val:.2f}%"
            weight_diff = f"{'↑' if weight_diff_val > 0 else '↓' if weight_diff_val < 0 else '→'} {weight_diff_val:,.2f}"
            weight_ratio_diff = f"{'↑' if weight_ratio_diff_val > 0 else '↓' if weight_ratio_diff_val < 0 else '→'} {weight_ratio_diff_val:.2f}%"
            price_diff = f"{'↑' if price_diff_val > 0 else '↓' if price_diff_val < 0 else '→'} {price_diff_val:,.2f}"
            price_ratio_diff = f"{'↑' if price_ratio_diff_val > 0 else '↓' if price_ratio_diff_val < 0 else '→'} {price_ratio_diff_val:.2f}%"

        # 填充总费用维度
        row["总费用_金额"] = f"{current_amount:,.2f}"
        row["总费用_金额差值"] = amount_diff
        row["总费用_占比"] = f"{current_amount_ratio:.2f}%"
        row["总费用_占比差值"] = amount_ratio_diff

        # 填充总重量维度
        row["总重量_重量"] = f"{current_weight:,.2f}"
        row["总重量_重量差值"] = weight_diff
        row["总重量_占比"] = f"{current_weight_ratio:.2f}%"
        row["总重量_占比差值"] = weight_ratio_diff

        # 填充单价维度
        row["单价_金额"] = f"{current_price:,.2f}"
        row["单价_金额差值"] = price_diff
        row["单价_占比"] = f"{current_price_ratio:.2f}%"
        row["单价_占比差值"] = price_ratio_diff

        table_data.append(row)

# 2. 转成DataFrame
pv_display = pd.DataFrame(table_data)


# 3. 高亮：上涨红，下跌绿
def highlight_changes(val):
    val_str = str(val)
    if "↑" in val_str:
        return "color: #e63946; font-weight: bold;"
    elif "↓" in val_str:
        return "color: #2a9d8f; font-weight: bold;"
    elif "→" in val_str:
        return "color: #666;"
    return ""


change_cols = [c for c in pv_display.columns if "差值" in c]
pv_styled = pv_display.style.applymap(highlight_changes, subset=change_cols)

# 4. 渲染表格，冻结首列，动态高度
st.dataframe(
    pv_styled,
    use_container_width=True,
    height=min(800, len(pv_display) * 35 + 50),
    hide_index=True
)

# 5. CSS优化：冻结首列，压缩内边距
st.markdown("""
<style>
    /* 压缩内边距，减少宽度占用 */
    [data-testid="stDataFrame"] div[role="cell"] {
        padding: 4px 6px !important;
        font-size: 13px !important;
    }
    /* 冻结前两列，滚动时不消失 */
    [data-testid="stDataFrame"] div[role="columnheader"][data-colindex="0"],
    [data-testid="stDataFrame"] div[role="cell"][data-colindex="0"],
    [data-testid="stDataFrame"] div[role="columnheader"][data-colindex="1"],
    [data-testid="stDataFrame"] div[role="cell"][data-colindex="1"] {
        position: sticky !important;
        left: calc(120px * var(--colindex)) !important;
        z-index: 999 !important;
        background-color: white !important;
        border-right: 2px solid #e0e0e0 !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("---")

# ------------------------------------------------------
# 【新增：空运成本深度分析（红单+空派）】
# ------------------------------------------------------
st.markdown("---")
st.header("📦 空运成本深度分析（红单 + 空派）")

# 读取 货件明细 数据（和你原有代码风格完全一致）
def load_shipment_data():
    url = "https://raw.githubusercontent.com/Jane-zzz-123/Logistics/main/CAE.xlsx"
    df_ship = pd.read_excel(url, sheet_name="货件明细")  # 读取你新增的sheet
    return df_ship

# 加载数据
df_detail = load_shipment_data()

# 时间清洗（统一格式，防止报错）
df_detail["开售时间"] = pd.to_datetime(df_detail["开售时间"], errors="coerce")
df_detail["出货时间"] = pd.to_datetime(df_detail["出货时间"], errors="coerce")
df_detail["月份"] = df_detail["月份"].astype(str)

# 只保留空运：红单 + 空派
air_list = ["红单", "空派"]
df_air = df_detail[df_detail["实际物流方式"].isin(air_list)].copy()

# -------------------------- 筛选器 --------------------------
st.sidebar.markdown("### 🔍 空运专项筛选")
month_list = sorted(df_air["月份"].astype(str).unique(), reverse=False)
default_months = month_list[-3:] if len(month_list) >=3 else month_list

select_months = st.sidebar.multiselect("月份", month_list, default=default_months)
select_logistics = st.sidebar.multiselect("物流方式", sorted(df_air["实际物流方式"].unique()), default=["红单","空派"])

# 应用筛选
df = df_air[
    (df_air["月份"].isin(select_months)) &
    (df_air["实际物流方式"].isin(select_logistics))
].copy()

if df.empty:
    st.warning("当前筛选条件下无空运数据")
    st.stop()

# -------------------------- 核心指标：成本类型汇总 --------------------------
st.subheader("🎯 空运成本结构概览")
cost_type_sum = df.groupby("成本类型").agg(
    总费用=("分摊总费用", "sum"),
    总重量=("总重量", "sum"),
    总申报量=("申报量", "sum")
).reset_index()

total_cost = df["分摊总费用"].sum()
cost_type_sum["占比"] = (cost_type_sum["总费用"] / total_cost * 100).round(1).astype(str) + "%"

# 指标卡展示
cols = st.columns(len(cost_type_sum))
for idx, row in cost_type_sum.iterrows():
    with cols[idx]:
        bg = "#2a9d8f" if "首批" in row["成本类型"] else "#f4a261" if "补货" in row["成本类型"] else "#3498db"
        st.markdown(f"""
        <div style='background-color:{bg}; padding:16px; border-radius:12px; color:white; text-align:center'>
            <div style='font-size:15px'>{row['成本类型']}</div>
            <div style='font-size:22px; font-weight:bold'>${row['总费用']:,.0f}</div>
            <div style='font-size:13px'>占比 {row['占比']}</div>
        </div>
        """, unsafe_allow_html=True)

# -------------------------- 按月趋势图 --------------------------
st.subheader("📈 月度空运成本趋势")
trend_df = df.groupby(["月份", "成本类型"])["分摊总费用"].sum().reset_index()
fig_trend = px.bar(
    trend_df, x="月份", y="分摊总费用", color="成本类型",
    title="各成本类型月度费用趋势", barmode="stack"
)
st.plotly_chart(fig_trend, use_container_width=True)

# -------------------------- 成本结构饼图 --------------------------
st.subheader("🥧 空运成本占比分布")
fig_pie = px.pie(
    cost_type_sum, values="总费用", names="成本类型", hole=0.4,
    color="成本类型", title="空运成本结构（新品/老品/补货）"
)
st.plotly_chart(fig_pie, use_container_width=True)

# -------------------------- 明细汇总表 --------------------------
st.subheader("📋 空运成本明细汇总")
table_df = df.groupby(["月份", "实际物流方式", "成本类型"]).agg(
    总费用=("分摊总费用", "sum"),
    总重量=("总重量", "sum"),
    总申报量=("申报量", "sum")
).reset_index()

table_df["总费用"] = table_df["总费用"].round(2)
table_df["总重量"] = table_df["总重量"].round(2)

st.dataframe(table_df, use_container_width=True, height=400)

st.success("✅ 空运成本深度分析已加载完成")