import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import BytesIO
import base64
import math

st.set_page_config(page_title="物流成本分析看板", layout="wide", initial_sidebar_state="expanded")

st.title("📊 物流成本分析")


# ====================== 1. 加载数据 ======================
@st.cache_data(show_spinner="加载成本数据中...")
def load_cost_data():
    url = "https://raw.githubusercontent.com/Jane-zzz-123/Logistics/main/CAE.xlsx"
    df_cost = pd.read_excel(url, sheet_name="数据")

    need_cols = ["年份", "周期", "月份", "目的仓", "仓库", "区域", "实际物流方式", "货代", "货代渠道", "重量", "报关费",
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
    df_cost["年份"] = pd.to_numeric(df_cost["年份"], errors="coerce").astype(int)

    # 生成带年份的周期/月份
    df_cost["年份周期"] = df_cost["年份"].astype(str) + "年" + df_cost["周期"].astype(str) + "周"
    df_cost["年份月份"] = df_cost["年份"].astype(str) + "年" + df_cost["月份"].apply(lambda x: f"{x:02d}") + "月"

    # 正确排序
    df_cost = df_cost.sort_values(by=["年份", "周期", "月份"], ascending=[True, True, True]).reset_index(drop=True)
    return df_cost


df_cost = load_cost_data()

# ====================== 全局配置 ======================
# 颜色映射
color_map = {
    "空派": "#1f77b4",  # 蓝色
    "以星特快": "#2ca02c",  # 绿色
    "以星": "#ff7f0e",  # 橙色
    "正班": "#7f7f7f",  # 灰色
    "普船": "#ffdd00"  # 黄色
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
            # 排序规则：年份 + 周期数字
            period_list = sorted(df_cost["年份周期"].unique(),
                                 key=lambda x: (int(x.split("年")[0]), int(x.split("年")[1].replace("周", ""))))
            default_val = period_list[-4:] if len(period_list) >= 4 else period_list
            selected = st.multiselect("周期", period_list, default=default_val)
        else:
            month_list = sorted(df_cost["年份月份"].unique(),
                                key=lambda x: (int(x.split("年")[0]), int(x.split("年")[1].replace("月", ""))))
            default_val = month_list[-3:] if len(month_list) >= 3 else month_list
            selected = st.multiselect("月份", month_list, default=default_val)

    with col2:
        area_list = ["全部"] + sorted(df_cost["区域"].dropna().unique())
        selected_area = st.selectbox("区域", area_list)

# ====================== 3. 筛选后数据处理 ======================
df = df_cost.copy()
group_col = "年份周期" if view_mode == "按周期" else "年份月份"

# 时间筛选
if view_mode == "按周期":
    df = df[df["年份周期"].isin(selected)] if selected else df
else:
    df = df[df["年份月份"].isin(selected)] if selected else df

# 区域筛选
if selected_area != "全部":
    df = df[df["区域"] == selected_area]

if df.empty:
    st.warning("无数据")
    st.stop()

# 最新 & 上期（自动兼容25+26年）
sorted_selected = sorted(selected, key=lambda x: (int(x.split("年")[0]),
                                                  int(x.split("年")[1].replace("周", "").replace("月", ""))))
latest_period = sorted_selected[-1] if sorted_selected else None
prev_period = sorted_selected[-2] if len(sorted_selected) >= 2 else latest_period


# ====================== 4. 环比计算工具函数 ======================
def get_vs_prev(latest_val, prev_val):
    diff = latest_val - prev_val
    pct = diff / prev_val * 100 if prev_val != 0 else 0
    sign = "↓" if diff < 0 else "↑" if diff > 0 else "→"
    color = "green" if diff < 0 else "red" if diff > 0 else "#888"
    return sign, color, diff, pct


# ====================== 5. 核心指标（修复同比计算） ======================
st.markdown("## 🎯 核心指标")
st.markdown(f"**统计周期：{view_mode} {latest_period}**")


# 【修复】同比周期自动计算逻辑
def get_yy_period(latest_period_str, view_mode):
    """
    自动计算同比周期：
    - 月份视图：2026年04月 → 2025年04月
    - 周期视图：2026年18周 → 2025年18周
    """
    try:
        if view_mode == "按月份":
            year_part = latest_period_str[:4]
            month_part = latest_period_str[5:]
            yy_year = str(int(year_part) - 1)
            return f"{yy_year}年{month_part}"
        elif view_mode == "按周期":
            year_part = latest_period_str[:4]
            week_part = latest_period_str[5:]
            yy_year = str(int(year_part) - 1)
            return f"{yy_year}年{week_part}"
        else:
            return None
    except:
        return None


# 自动获取同比周期
yy_period = get_yy_period(latest_period, view_mode)

# 【关键修复】同比数据：用全量数据匹配，不受筛选器限制
latest_data = df[df[group_col] == latest_period]
prev_data = df[df[group_col] == prev_period] if prev_period in df[group_col].values else pd.DataFrame()
# 同比数据：从全量df_cost中匹配，只要表里有就显示，不受当前多选筛选限制
yy_data = df_cost[df_cost[group_col] == yy_period] if (
            yy_period is not None and yy_period in df_cost[group_col].values) else pd.DataFrame()

# 核心指标
metrics = [
    {
        "name": "总费用",
        "latest": latest_data["总费用"].sum(),
        "prev": prev_data["总费用"].sum() if not prev_data.empty else 0,
        "yy": yy_data["总费用"].sum() if not yy_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["总费用"]
    },
    {
        "name": "总运费",
        "latest": latest_data["总运费"].sum(),
        "prev": prev_data["总运费"].sum() if not prev_data.empty else 0,
        "yy": yy_data["总运费"].sum() if not yy_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["总运费"]
    },
    {
        "name": "入库配置费",
        "latest": latest_data["入库配置费折算RMB"].sum(),
        "prev": prev_data["入库配置费折算RMB"].sum() if not prev_data.empty else 0,
        "yy": yy_data["入库配置费折算RMB"].sum() if not yy_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["入库配置费"]
    },
    {
        "name": "报关费",
        "latest": latest_data["报关费"].sum(),
        "prev": prev_data["报关费"].sum() if not prev_data.empty else 0,
        "yy": yy_data["报关费"].sum() if not yy_data.empty else 0,
        "unit": "¥",
        "bg": card_bg_map["报关费"]
    },
    {
        "name": "总重量",
        "latest": latest_data["重量"].sum(),
        "prev": prev_data["重量"].sum() if not prev_data.empty else 0,
        "yy": yy_data["重量"].sum() if not yy_data.empty else 0,
        "unit": "kg",
        "bg": card_bg_map["总重量"]
    }
]

# 渲染5张指标卡（环比+同比双对比）
cols = st.columns(5)
for i, metric in enumerate(metrics):
    with cols[i]:
        # 环比计算
        mom_sign, mom_color, mom_diff, mom_pct = get_vs_prev(metric["latest"], metric["prev"])
        # 同比计算
        yoy_sign, yoy_color, yoy_diff, yoy_pct = get_vs_prev(metric["latest"], metric["yy"])

        # 同比文案：无数据时友好显示
        if metric["yy"] == 0:
            yoy_text = f"→ 无去年同期数据"
        else:
            yoy_text = f"{yoy_sign} {abs(yoy_diff):,.0f} (去年同期: {metric['unit']}{metric['yy']:,.0f})"

        # 自定义卡片HTML
        card_html = f"""
        <div style="background-color:{metric['bg']}; padding:20px; border-radius:12px; text-align:center; min-height:280px; display:flex; flex-direction:column; justify-content:center; align-items:center;">
            <div style="font-size:28px; font-weight:bold; margin-bottom:15px;">{metric['name']}</div>
            <div style="font-size:42px; font-weight:900; margin-bottom:15px;">{metric['unit']}{metric['latest']:,.0f}</div>
            <!-- 环比行 -->
            <div style="font-size:18px; color:{mom_color}; margin-bottom:8px;">
                环比 {mom_sign} {abs(mom_diff):,.0f} (上期: {metric['unit']}{metric['prev']:,.0f})
            </div>
            <!-- 同比行 -->
            <div style="font-size:18px; color:{yoy_color};">
                同比 {yoy_text}
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

# ====================== ✅ 这里只改了这一行 ======================
df_trend[group_col] = df_trend[group_col].astype(str)

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
# ====================== 【新增】顶部费用计算公式说明 ======================
st.markdown("## 💰 单价 & 总金额明细（按物流方式）")

formula_html = """
<div style="background:#f8f9fa; padding:14px; border-radius:8px; margin-bottom:20px; border-left:4px solid #1f77b4;">
<b>📌 费用计算公式说明</b>
<ul style="margin:5px 0 0 20px; padding:0; line-height:1.7;">
<li>运费 = 账单运费 + 附加费 + 运费税点</li>
<li>总运费 = 报关费 + 报关费税点 + 运费</li>
<li>入库配置费折算RMB = 入库配置费单价（美元） × 汇率</li>
<li>总费用 = 总运费 + 入库配置费折算RMB</li>
</ul>
</div>
"""
st.markdown(formula_html, unsafe_allow_html=True)


# ====================== 原有计算函数（不变） ======================
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
df_cost_unit = calc_unit_price(df, "总费用")
df_cost_amt = calc_total_amount(df, "总费用")
df_freight_unit = calc_unit_price(df, "总运费")
df_freight_amt = calc_total_amount(df, "总运费")
df_storage_unit = calc_unit_price(df, "入库配置费折算RMB")
df_storage_amt = calc_total_amount(df, "入库配置费折算RMB")


# ====================== 【新增】自动生成：单价+总金额 文字总结 ======================
def generate_summary(df_unit, df_amt):
    try:
        latest_p = sorted(df_unit[group_col].unique())[-1]
    except:
        return "<div>暂无数据</div>"

    lines = []
    for logi in sorted(df["实际物流方式"].unique()):
        u = df_unit[(df_unit[group_col] == latest_p) & (df_unit["实际物流方式"] == logi)]
        a = df_amt[(df_amt[group_col] == latest_p) & (df_amt["实际物流方式"] == logi)]

        if u.empty or a.empty:
            lines.append(f"- {logi}：无数据")
            continue

        ur = u.iloc[0]
        ar = a.iloc[0]

        # 单价
        up = ur["折算单价"]
        ud = ur["环比差值"]
        upct = ur["环比幅度"]

        # 金额
        am = ar["总金额"]
        ad = ar["环比差值"]
        apct = ar["环比幅度"]

        # 单价符号
        if pd.isna(ud):
            uinfo = f"单价：首期 ¥{up:.2f}"
        else:
            uarr = "↑" if ud > 0 else "↓"
            uinfo = f"单价{uarr}¥{abs(ud):.2f}({uarr}{abs(upct):.1f}%) 现价¥{up:.2f}"

        # 金额符号
        if pd.isna(ad):
            ainfo = f"金额：首期 ¥{am:,.0f}"
        else:
            aarr = "↑" if ad > 0 else "↓"
            ainfo = f"金额{aarr}¥{abs(ad):,.0f}({aarr}{abs(apct):.1f}%) 本期¥{am:,.0f}"

        line = f"- {logi}：{uinfo}｜{ainfo}"
        lines.append(line)

    html = '<div style="font-size:13px; line-height:1.7; margin-bottom:12px;">'
    for l in lines:
        if "↑" in l:
            html += f'<div style="color:#d93025;">{l}</div>'
        elif "↓" in l:
            html += f'<div style="color:#009d5a;">{l}</div>'
        else:
            html += f'<div style="color:#666;">{l}</div>'
    html += "</div>"
    return html


# ====================== 原有渲染函数（只优化排序） ======================
def render_detail_section(col, title, df_unit, df_amt):
    with col:
        st.markdown(f"### {title}")
        st.markdown(generate_summary(df_unit, df_amt), unsafe_allow_html=True)

        all_logi = sorted(df["实际物流方式"].unique())

        # ====================== ✅ 修复：年月格式不转int，直接排序 ======================
        sorted_vals = sorted(df_unit[group_col].unique())

        # 单价图表
        st.markdown("##### 📈 单价趋势（元/kg）")
        df_unit["x_str"] = df_unit[group_col].astype(str)
        fig_unit = px.line(
            df_unit, x="x_str", y="折算单价", color="实际物流方式",
            color_discrete_map={k: color_map.get(k, default_color) for k in all_logi},
            markers=True
        )
        fig_unit.update_xaxes(type="category", categoryorder="array", categoryarray=sorted_vals)
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
        st.markdown("---")

        # 总金额图表
        st.markdown("##### 💰 总金额趋势（元）")
        df_amt["x_str"] = df_amt[group_col].astype(str)
        fig_amt = px.line(
            df_amt, x="x_str", y="总金额", color="实际物流方式",
            color_discrete_map={k: color_map.get(k, default_color) for k in all_logi},
            markers=True
        )
        fig_amt.update_xaxes(type="category", categoryorder="array", categoryarray=sorted_vals)
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


# 渲染3列
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

# 已修复：去掉 int(x)，支持年月格式
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
        text=df_period.apply(lambda row: f"{row[group_col]}<br>{row['费用占比']:.2f}%", axis=1),
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


# 1. 同比周期计算函数
def get_yy_period(latest_period_str, view_mode):
    try:
        if view_mode == "按月份":
            year_part = latest_period_str[:4]
            month_part = latest_period_str[5:]
            yy_year = str(int(year_part) - 1)
            return f"{yy_year}年{month_part}"
        elif view_mode == "按周期":
            year_part = latest_period_str[:4]
            week_part = latest_period_str[5:]
            yy_year = str(int(year_part) - 1)
            return f"{yy_year}年{week_part}"
        else:
            return None
    except:
        return None


# 2. 【优化】数值格式化+分层样式生成函数
def format_value_with_compare(current_val, prev_val, yy_val, is_ratio=False):
    """
    分层样式：主数值放大加粗，对比文案缩小，自动加颜色标签
    """
    # 环比计算
    mom_diff = current_val - prev_val
    mom_sign = "↑" if mom_diff > 0 else "↓" if mom_diff < 0 else "→"
    mom_color = "#e63946" if mom_diff > 0 else "#2a9d8f" if mom_diff < 0 else "#666"
    # 同比计算
    yoy_diff = current_val - yy_val
    yoy_sign = "↑" if yoy_diff > 0 else "↓" if yoy_diff < 0 else "→"
    yoy_color = "#e63946" if yoy_diff > 0 else "#2a9d8f" if yoy_diff < 0 else "#666"

    # 数值格式：占比保留2位+%，金额/重量保留2位
    val_format = f"{current_val:.2f}%" if is_ratio else f"{current_val:,.2f}"

    # 环比文案
    if prev_val == 0:
        mom_text = f'<span style="font-size:12px; color:#666">环比：无上期数据</span>'
    else:
        diff_text = f"{mom_sign}{abs(mom_diff):.2f}%" if is_ratio else f"{mom_sign}{abs(mom_diff):,.2f}"
        mom_text = f'<span style="font-size:12px; color:{mom_color}">环比变化：{diff_text}</span>'

    # 同比文案
    if yy_val == 0:
        yoy_text = f'<span style="font-size:12px; color:#666">同比：无去年同期数据</span>'
    else:
        diff_text = f"{yoy_sign}{abs(yoy_diff):.2f}%" if is_ratio else f"{yoy_sign}{abs(yoy_diff):,.2f}"
        yoy_text = f'<span style="font-size:12px; color:{yoy_color}">同比变化：{diff_text}，去年同期：{yy_val:.2f}%</span>' if is_ratio else f'<span style="font-size:12px; color:{yoy_color}">同比变化：{diff_text}，去年同期：{yy_val:,.2f}</span>'

    # 最终拼接：主数值放大加粗，对比文案缩小换行
    return f'<span style="font-size:18px; font-weight:bold; line-height:1.6;">{val_format}</span><br>{mom_text}<br>{yoy_text}'


# 3. 构建表格数据（同比从全量数据加载）
table_data = []
for logi in final_order:
    for period in period_list:
        # 基础行
        row = {
            "实际物流方式": logi,
            "周期/月份": period
        }

        # 获取本期数据（从当前筛选后的df_pie）
        current_data = df_pie[(df_pie[group_col] == period) & (df_pie["实际物流方式"] == logi)]
        current_amount = current_data["总费用"].values[0] if len(current_data) > 0 else 0
        current_weight = current_data["总重量"].values[0] if len(current_data) > 0 else 0
        current_price = current_data["单价"].values[0] if len(current_data) > 0 else 0
        current_amount_ratio = current_data["费用占比"].values[0] if len(current_data) > 0 else 0
        current_weight_ratio = current_data["重量占比"].values[0] if len(current_data) > 0 else 0
        current_price_ratio = current_data["单价占比"].values[0] if len(current_data) > 0 else 0

        # 计算上期数据（环比，从当前筛选后的df_pie）
        period_idx = period_list.index(period)
        prev_amount = 0
        prev_weight = 0
        prev_price = 0
        prev_amount_ratio = 0
        prev_weight_ratio = 0
        prev_price_ratio = 0
        if period_idx > 0:
            prev_period = period_list[period_idx - 1]
            prev_data = df_pie[(df_pie[group_col] == prev_period) & (df_pie["实际物流方式"] == logi)]
            prev_amount = prev_data["总费用"].values[0] if len(prev_data) > 0 else 0
            prev_weight = prev_data["总重量"].values[0] if len(prev_data) > 0 else 0
            prev_price = prev_data["单价"].values[0] if len(prev_data) > 0 else 0
            prev_amount_ratio = prev_data["费用占比"].values[0] if len(prev_data) > 0 else 0
            prev_weight_ratio = prev_data["重量占比"].values[0] if len(prev_data) > 0 else 0
            prev_price_ratio = prev_data["单价占比"].values[0] if len(prev_data) > 0 else 0

        # 同比数据：从全量df_cost加载，不受筛选器限制
        yy_period = get_yy_period(period, view_mode)
        yy_amount = 0
        yy_weight = 0
        yy_price = 0
        yy_amount_ratio = 0
        yy_weight_ratio = 0
        yy_price_ratio = 0
        if yy_period is not None and yy_period in df_cost[group_col].values:
            yy_data = df_cost[(df_cost[group_col] == yy_period) & (df_cost["实际物流方式"] == logi)]
            yy_amount = yy_data["总费用"].sum()
            yy_weight = yy_data["重量"].sum()
            # 同比单价计算：总费用 / 总重量
            yy_price = yy_amount / yy_weight if yy_weight > 0 else 0
            # 同比占比计算：该物流方式费用 / 该周期总费用
            yy_period_total = df_cost[df_cost[group_col] == yy_period]["总费用"].sum()
            yy_amount_ratio = yy_amount / yy_period_total * 100 if yy_period_total > 0 else 0
            yy_period_weight_total = df_cost[df_cost[group_col] == yy_period]["重量"].sum()
            yy_weight_ratio = yy_weight / yy_period_weight_total * 100 if yy_period_weight_total > 0 else 0
            yy_price_period_avg = (df_cost[df_cost[group_col] == yy_period]["总费用"].sum() /
                                   df_cost[df_cost[group_col] == yy_period][
                                       "重量"].sum()) if yy_period_weight_total > 0 else 0
            yy_price_ratio = yy_price / yy_price_period_avg * 100 if yy_price_period_avg > 0 else 0

        # 填充8列数据（带环比+同比）
        row["总费用_金额"] = format_value_with_compare(current_amount, prev_amount, yy_amount, is_ratio=False)
        row["总费用_占比"] = format_value_with_compare(current_amount_ratio, prev_amount_ratio, yy_amount_ratio,
                                                       is_ratio=True)
        row["总重量_重量"] = format_value_with_compare(current_weight, prev_weight, yy_weight, is_ratio=False)
        row["总重量_占比"] = format_value_with_compare(current_weight_ratio, prev_weight_ratio, yy_weight_ratio,
                                                       is_ratio=True)
        row["单价_金额"] = format_value_with_compare(current_price, prev_price, yy_price, is_ratio=False)
        row["单价_占比"] = format_value_with_compare(current_price_ratio, prev_price_ratio, yy_price_ratio,
                                                     is_ratio=True)

        table_data.append(row)

# 4. 转成DataFrame
pv_display = pd.DataFrame(table_data)

# 5. 渲染表格（优化样式）
st.markdown("""
<style>
    /* 表格基础样式 */
    [data-testid="stDataFrame"] div[role="cell"] {
        padding: 12px 6px !important;
        line-height: 1.6 !important;
        vertical-align: middle !important;
    }
    /* 表头样式 */
    [data-testid="stDataFrame"] div[role="columnheader"] {
        font-size: 14px !important;
        font-weight: 600 !important;
        background: #f8f9fa !important;
    }
    /* 冻结前两列 */
    [data-testid="stDataFrame"] div[role="columnheader"][data-colindex="0"],
    [data-testid="stDataFrame"] div[role="cell"][data-colindex="0"] {
        position: sticky !important;
        left: 0px !important;
        z-index: 999 !important;
        background: #f8f9fa !important;
        border-right: 2px solid #ddd !important;
    }
    [data-testid="stDataFrame"] div[role="columnheader"][data-colindex="1"],
    [data-testid="stDataFrame"] div[role="cell"][data-colindex="1"] {
        position: sticky !important;
        left: 120px !important;
        z-index: 999 !important;
        background: #f8f9fa !important;
        border-right: 2px solid #ddd !important;
    }
</style>
""", unsafe_allow_html=True)

# 用HTML表格渲染，完美支持内嵌样式
html_table = pv_display.to_html(escape=False, index=False)
st.markdown(html_table, unsafe_allow_html=True)

st.markdown("---")

# ------------------------------------------------------
# 空运成本分析 - 最终业务版（结构完全对齐）
# ------------------------------------------------------

st.markdown("---")
st.header("📦 空运成本深度分析（红单 + 空派）")

# 1. 读取货件明细
def load_shipment_data():
    url = "https://raw.githubusercontent.com/Jane-zzz-123/Logistics/main/CAE.xlsx"
    use_cols = [
        "年份","月份", "实际物流方式", "成本类型", "开售时间", "出货时间",
        "总重量", "分摊总费用", "货件单号", "MSKU", "品名", "申报量"
    ]
    df = pd.read_excel(url, sheet_name="货件明细", usecols=use_cols)
    df["月份"] = pd.to_numeric(df["月份"], errors="coerce").fillna(0).astype(int)
    df["年份"] = pd.to_numeric(df["年份"], errors="coerce").fillna(0).astype(int)
    df["年月"] = df["年份"].astype(str) + "-" + df["月份"].astype(str).str.zfill(2)
    df["开售时间"] = pd.to_datetime(df["开售时间"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("未开售")
    df["出货时间"] = pd.to_datetime(df["出货时间"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("无记录")
    return df

# 2. 读取主数据（年份+月份+总费用）
def load_main_data():
    url = "https://raw.githubusercontent.com/Jane-zzz-123/Logistics/main/CAE.xlsx"
    df = pd.read_excel(url, sheet_name="数据", usecols=["年份", "月份", "总费用"])
    df["月份"] = pd.to_numeric(df["月份"], errors="coerce").fillna(0).astype(int)
    df["年份"] = pd.to_numeric(df["年份"], errors="coerce").fillna(0).astype(int)
    df["年月"] = df["年份"].astype(str) + "-" + df["月份"].astype(str).str.zfill(2)
    df["总费用"] = pd.to_numeric(df["总费用"], errors="coerce").fillna(0)
    return df

# 加载数据
df_detail = load_shipment_data()
df_main = load_main_data()

# 筛选空运
air_list = ["红单", "空派"]
df_air = df_detail[df_detail["实际物流方式"].isin(air_list)].copy()

# -------------------------- 年月筛选器 ✅ --------------------------
col1, col2 = st.columns(2)

with col1:
    sorted_ym = sorted(df_air["年月"].unique())
    selected_ym = st.selectbox("选择年月", sorted_ym, index=len(sorted_ym)-1)

with col2:
    logistics_options = ["全部"] + sorted(df_air["实际物流方式"].unique())
    selected_log = st.selectbox("实际物流方式", logistics_options)

# 拆分年份、月份
selected_year, selected_month = selected_ym.split("-")
selected_month = str(int(selected_month))

# 筛选当前数据
if selected_log == "全部":
    df_filt = df_air[
        (df_air["年份"].astype(str) == selected_year) &
        (df_air["月份"].astype(str) == selected_month)
    ].copy()
else:
    df_filt = df_air[
        (df_air["年份"].astype(str) == selected_year) &
        (df_air["月份"].astype(str) == selected_month) &
        (df_air["实际物流方式"] == selected_log)
    ].copy()

if df_filt.empty:
    st.warning("⚠️ 无数据")
    st.stop()

# -------------------------- 上月计算（自动跨年）✅ --------------------------
all_ym = sorted(df_air["年月"].unique())
idx = all_ym.index(selected_ym)
last_ym = all_ym[idx-1] if idx > 0 else None
last_year, last_month = last_ym.split("-") if last_ym else (None, None)

# ====================== 核心计算（严格年份+月份）✅ ======================
current_air = df_filt["分摊总费用"].sum()

current_total = df_main[
    (df_main["年份"] == int(selected_year)) &
    (df_main["月份"] == int(selected_month))
]["总费用"].sum()

last_air = 0
last_total = 0
last_df = pd.DataFrame()

if last_ym:
    if selected_log == "全部":
        last_df = df_air[df_air["年月"] == last_ym].copy()
    else:
        last_df = df_air[(df_air["年月"] == last_ym) & (df_air["实际物流方式"] == selected_log)].copy()
    last_air = last_df["分摊总费用"].sum()
    last_total = df_main[df_main["年月"] == last_ym]["总费用"].sum()

air_ratio = round(current_air / current_total * 100, 1) if current_total > 0 else 0

# 成本拆分
curr_gb = df_filt.groupby("成本类型")["分摊总费用"].sum()
last_gb = last_df.groupby("成本类型")["分摊总费用"].sum() if last_ym else pd.Series(dtype=float)

def getv(s, k): return s.get(k, 0)
p1 = getv(curr_gb, "新品首批发货")
p2 = getv(curr_gb, "新品期补货空运")
p3 = getv(curr_gb, "老品应急空运")
l1 = getv(last_gb, "新品首批发货")
l2 = getv(last_gb, "新品期补货空运")
l3 = getv(last_gb, "老品应急空运")

def diff(c, l):
    if l == 0: return "→ 无上月"
    d = c - l
    return f"{'↑' if d>0 else '↓'} {abs(d):,.0f}"

# -------------------------- 指标卡 --------------------------
st.subheader("🎯 空运成本概览")
with st.expander("📖 成本类型说明"):
    st.markdown("""
    | 成本类型 | 定义 |
    |---|---|
    | 新品首批发货 | 发货早于开售 |
    | 新品期补货空运 | 间隔 ≤60天 |
    | 老品应急空运 | 间隔 >60天 |
    """)

c1,c2,c3,c4 = st.columns(4)
with c1:
    t = diff(current_air, last_air)
    st.markdown(f"""
<div style="background:#f8f9fa;padding:20px;border-radius:12px;text-align:center;height:220px">
<div style="font-size:17px">空运总费用</div>
<div style="font-size:30px;font-weight:900">¥{current_air:,.0f}</div>
<div style="font-size:15px">占整体 {air_ratio}%</div>
<div style="color:{'red' if '↑' in t else 'green'}">{t}</div>
</div>""", unsafe_allow_html=True)
with c2:
    t = diff(p1,l1)
    r = round(p1/current_air*100,1) if current_air else 0
    st.markdown(f"""<div style="background:#2a9d8f;color:white;padding:20px;border-radius:12px;text-align:center;height:220px">
<div>新品首批发货</div><div style="font-size:30px">¥{p1:,.0f}</div><div>占空运 {r}%</div><div>{t}</div></div>""", unsafe_allow_html=True)
with c3:
    t = diff(p2,l2)
    r = round(p2/current_air*100,1) if current_air else 0
    st.markdown(f"""<div style="background:#f4a261;color:white;padding:20px;border-radius:12px;text-align:center;height:220px">
<div>新品期补货空运</div><div style="font-size:30px">¥{p2:,.0f}</div><div>占空运 {r}%</div><div>{t}</div></div>""", unsafe_allow_html=True)
with c4:
    t = diff(p3,l3)
    r = round(p3/current_air*100,1) if current_air else 0
    st.markdown(f"""<div style="background:#3498db;color:white;padding:20px;border-radius:12px;text-align:center;height:220px">
<div>老品应急空运</div><div style="font-size:30px">¥{p3:,.0f}</div><div>占空运 {r}%</div><div>{t}</div></div>""", unsafe_allow_html=True)

# -------------------------- 趋势 --------------------------
st.subheader("📊 月度成本趋势")
color_map = {"新品首批发货":"#2a9d8f","新品期补货空运":"#f4a261","老品应急空运":"#3498db"}
if selected_log == "全部":
    tr = df_air.groupby(["年月","成本类型"])["分摊总费用"].sum().reset_index()
else:
    tr = df_air[df_air["实际物流方式"]==selected_log].groupby(["年月","成本类型"])["分摊总费用"].sum().reset_index()

fig = px.bar(tr, x="年月", y="分摊总费用", color="成本类型", color_discrete_map=color_map, barmode="stack")
fig.update_xaxes(type="category", categoryorder="array", categoryarray=sorted(df_air["年月"].unique()))
st.plotly_chart(fig, use_container_width=True)

# -------------------------- 结构分析 --------------------------
st.subheader("📋 成本结构分析")
ch, tb = st.columns(2)
with ch:
    st.markdown("**成本占比**")
    pie = df_filt.groupby("成本类型")["分摊总费用"].sum().reset_index()
    st.plotly_chart(px.pie(pie, values="分摊总费用", names="成本类型", color_discrete_map=color_map, hole=0.4), use_container_width=True)
with tb:
    st.markdown("**成本汇总**")
    sum_tb = df_filt.groupby(["年份","月份","实际物流方式","成本类型"]).agg(总费用=("分摊总费用","sum"),总重量=("总重量","sum")).reset_index()
    st.dataframe(sum_tb.round(2), use_container_width=True, height=450)

# -------------------------- 明细 --------------------------
st.subheader("📦 空运原始明细")
cost_types = ["全部"] + sorted(df_filt["成本类型"].unique())
sel_cost = st.selectbox("筛选成本类型", cost_types)
final = df_filt if sel_cost=="全部" else df_filt[df_filt["成本类型"]==sel_cost]
cols = ["年份","月份","实际物流方式","成本类型","开售时间","出货时间","总重量","分摊总费用","货件单号","MSKU","品名","申报量"]
st.dataframe(final[cols].round(2), use_container_width=True, height=600)