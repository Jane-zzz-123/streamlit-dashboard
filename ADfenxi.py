import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from io import BytesIO
import numpy as np

# -------------------------- 页面基础配置 --------------------------
st.set_page_config(
    page_title="亚马逊店铺TACOS广告花费占比归因看板",
    layout="wide",
    initial_sidebar_state="collapsed"  # 彻底隐藏侧边栏
)
st.title("📊 亚马逊店铺广告花费占比(TACOS)上升归因分析 | 2025.01-2026.05")
st.markdown("""
分析逻辑：优先查看选定单月当月完整数据 → 多月份趋势对比定位TACOS抬升区间 → 自动归因上涨五大核心原因 → 品类/新品老品/MSKU单品细分拆解
数据源：ADdata_all.xlsx sheet=源数据，含「开售时间」字段区分新品老品；CTR/CPC/ACOS/TACOS等广告指标代码自动计算
""")


# -------------------------- 缓存加载原始数据 --------------------------
@st.cache_data
def load_raw_data():
    url = "https://github.com/Jane-zzz-123/streamlit-dashboard/raw/main/ADdata_all.xlsx"
    resp = requests.get(url)
    df = pd.read_excel(BytesIO(resp.content), sheet_name="源数据")

    # 标准化时间
    df["时间"] = pd.to_datetime(df["时间"])
    df["年月"] = df["时间"].dt.to_period("M").astype(str)

    # 数值清洗防报错
    num_cols = [
        "展示", "点击", "广告花费", "SP广告费", "SB广告费", "SBV广告费",
        "广告销售额", "SP广告销售额", "SB广告销售额", "SBV广告销售额",
        "广告订单量", "SP广告订单量", "SB广告订单量", "SBV广告订单量",
        "销量", "销售额", "订单量"
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 上架时间转换（新品老品判断用）
    df["开售时间"] = pd.to_datetime(df["开售时间"], errors="coerce")
    return df


df_raw = load_raw_data()

# ===================== 页面顶部筛选区：仅2个单选控件【店铺、单月年月】，无品类筛选 =====================
st.markdown("### 🔍 数据筛选条件（仅单月数据）")
filter_shop_col, filter_month_col = st.columns([1, 2])

# 1、店铺单选下拉
with filter_shop_col:
    shop_list = sorted(df_raw["店铺"].unique())
    select_shop = st.selectbox("选择分析店铺", shop_list)

# 2、年月单选下拉，默认选中最新月份（仅单选单月，无法选区间）
with filter_month_col:
    month_list = sorted(df_raw["年月"].unique())
    latest_month = month_list[-1]  # 自动取最新月份作为默认
    select_month = st.selectbox("选择分析单月", month_list, index=month_list.index(latest_month))

st.divider()

# -------------------------- 筛选数据集：仅匹配【选定店铺+选定单月】 --------------------------
df_filter_single_month = df_raw[
    (df_raw["店铺"] == select_shop) &
    (df_raw["年月"] == select_month)
    ].copy()

if df_filter_single_month.empty:
    st.warning(f"⚠️ {select_shop}店铺 {select_month} 无任何数据，请更换店铺或月份！")
    st.stop()

# ========== 给当月数据打新品/老品标签 ==========
df_filter_single_month["年月日期"] = pd.to_datetime(df_filter_single_month["年月"] + "-01")
df_filter_single_month["上架间隔天数"] = (
            df_filter_single_month["年月日期"] - df_filter_single_month["开售时间"]).dt.days


def tag_product_type(days):
    if pd.isna(days) or days <= 0:
        return "未知上架时间"
    elif days <= 60:
        return "新品(上架≤60天)"
    else:
        return "老品(上架>60天)"


df_filter_single_month["产品类型"] = df_filter_single_month["上架间隔天数"].apply(tag_product_type)

# -------------------------- 当月单月聚合数据 --------------------------
df_month_single = df_filter_single_month.groupby("年月").agg({
    "展示": "sum",
    "点击": "sum",
    "广告花费": "sum",
    "SP广告费": "sum",
    "SB广告费": "sum",
    "SBV广告费": "sum",
    "广告销售额": "sum",
    "广告订单量": "sum",
    "销售额": "sum",
    "订单量": "sum"
}).reset_index()

# 当月衍生指标
df_month_single["CTR"] = np.where(df_month_single["展示"] == 0, 0, df_month_single["点击"] / df_month_single["展示"])
df_month_single["CPC"] = np.where(df_month_single["点击"] == 0, 0,
                                  df_month_single["广告花费"] / df_month_single["点击"])
df_month_single["CVR广告转化率"] = np.where(df_month_single["点击"] == 0, 0,
                                            df_month_single["广告订单量"] / df_month_single["点击"])
df_month_single["ACOS"] = np.where(df_month_single["广告销售额"] == 0, 0,
                                   df_month_single["广告花费"] / df_month_single["广告销售额"])
df_month_single["ROAS"] = np.where(df_month_single["广告花费"] == 0, 0,
                                   df_month_single["广告销售额"] / df_month_single["广告花费"])
df_month_single["TACOS广告花费占比"] = np.where(df_month_single["销售额"] == 0, 0,
                                                df_month_single["广告花费"] / df_month_single["销售额"])
df_month_single["ASoAS广告销售依赖度"] = np.where(df_month_single["销售额"] == 0, 0,
                                                  df_month_single["广告销售额"] / df_month_single["销售额"])
df_month_single["SP广告花费占比"] = np.where(df_month_single["广告花费"] == 0, 0,
                                             df_month_single["SP广告费"] / df_month_single["广告花费"])
df_month_single["SB广告花费占比"] = np.where(df_month_single["广告花费"] == 0, 0,
                                             df_month_single["SB广告费"] / df_month_single["广告花费"])
df_month_single["SBV广告花费占比"] = np.where(df_month_single["广告花费"] == 0, 0,
                                              df_month_single["SBV广告费"] / df_month_single["广告花费"])

# 当月数值
curr_ad_spend = df_month_single["广告花费"].iloc[0]
curr_sales = df_month_single["销售额"].iloc[0]
curr_ad_order = df_month_single["广告订单量"].iloc[0]
curr_all_order = df_month_single["订单量"].iloc[0]
curr_tacos = df_month_single["TACOS广告花费占比"].iloc[0]
curr_acos = df_month_single["ACOS"].iloc[0]
curr_roas = df_month_single["ROAS"].iloc[0]
curr_asoas = df_month_single["ASoAS广告销售依赖度"].iloc[0]
curr_cpc = df_month_single["CPC"].iloc[0]
curr_ctr = df_month_single["CTR"].iloc[0]
curr_cvr = df_month_single["CVR广告转化率"].iloc[0]

# -------------------------- 计算上月数据（用于环比对比） --------------------------
# 转换年月为日期，取上月
curr_period = pd.Period(select_month, freq="M")
last_period = curr_period - 1
last_month_str = str(last_period)
# 筛选同店铺上月数据
df_last_raw = df_raw[(df_raw["店铺"] == select_shop) & (df_raw["年月"] == last_month_str)]
has_last_month = not df_last_raw.empty

# 上月默认空值
last_ad_spend = last_sales = last_ad_order = last_all_order = 0
last_tacos = last_acos = last_roas = last_asoas = last_cpc = last_ctr = last_cvr = 0
delta_ad_spend = delta_sales = delta_ad_order = delta_all_order = 0
delta_tacos = delta_acos = delta_roas = delta_asoas = delta_cpc = delta_ctr = delta_cvr = 0
pct_ad_spend = pct_sales = pct_ad_order = pct_all_order = 0
pct_tacos = pct_acos = pct_roas = pct_asoas = pct_cpc = pct_ctr = pct_cvr = 0

if has_last_month:
    df_last_agg = df_last_raw.groupby("年月").agg({
        "广告花费": "sum", "销售额": "sum", "广告订单量": "sum", "订单量": "sum",
        "展示": "sum", "点击": "sum", "广告销售额": "sum"
    }).reset_index()
    last_ad_spend = df_last_agg["广告花费"].iloc[0]
    last_sales = df_last_agg["销售额"].iloc[0]
    last_ad_order = df_last_agg["广告订单量"].iloc[0]
    last_all_order = df_last_agg["订单量"].iloc[0]
    last_imp = df_last_agg["展示"].iloc[0]
    last_click = df_last_agg["点击"].iloc[0]
    last_ad_sales = df_last_agg["广告销售额"].iloc[0]

    # 上月衍生指标
    last_ctr = last_click / last_imp if last_imp != 0 else 0
    last_cpc = last_ad_spend / last_click if last_click != 0 else 0
    last_cvr = last_ad_order / last_click if last_click != 0 else 0
    last_acos = last_ad_spend / last_ad_sales if last_ad_sales != 0 else 0
    last_roas = last_ad_sales / last_ad_spend if last_ad_spend != 0 else 0
    last_tacos = last_ad_spend / last_sales if last_sales != 0 else 0
    last_asoas = last_ad_sales / last_sales if last_sales != 0 else 0

    # 差值 & 环比
    delta_ad_spend = curr_ad_spend - last_ad_spend
    delta_sales = curr_sales - last_sales
    delta_ad_order = curr_ad_order - last_ad_order
    delta_all_order = curr_all_order - last_all_order
    delta_tacos = curr_tacos - last_tacos
    delta_acos = curr_acos - last_acos
    delta_roas = curr_roas - last_roas
    delta_asoas = curr_asoas - last_asoas
    delta_cpc = curr_cpc - last_cpc
    delta_ctr = curr_ctr - last_ctr
    delta_cvr = curr_cvr - last_cvr

    pct_ad_spend = delta_ad_spend / last_ad_spend if last_ad_spend != 0 else 0
    pct_sales = delta_sales / last_sales if last_sales != 0 else 0
    pct_ad_order = delta_ad_order / last_ad_order if last_ad_order != 0 else 0
    pct_all_order = delta_all_order / last_all_order if last_all_order != 0 else 0
    pct_tacos = delta_tacos / last_tacos if last_tacos != 0 else 0
    pct_acos = delta_acos / last_acos if last_acos != 0 else 0
    pct_roas = delta_roas / last_roas if last_roas != 0 else 0
    pct_asoas = delta_asoas / last_asoas if last_asoas != 0 else 0
    pct_cpc = delta_cpc / last_cpc if last_cpc != 0 else 0
    pct_ctr = delta_ctr / last_ctr if last_ctr != 0 else 0
    pct_cvr = delta_cvr / last_cvr if last_cvr != 0 else 0

# ===================== 一、【当月核心指标卡片】增加环比delta与下方小字上月对比 =====================
st.markdown(f"## 🎯 一、{select_month} 当月店铺整体概况（单月快照）")
if not has_last_month:
    st.info("当前为最早统计月份，无上月对比数据")

# 第一行4卡：广告花费、总销售额、广告订单、总订单
row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
with row1_col1:
    st.metric(label="当月总广告花费", value=f"${curr_ad_spend:,.2f}", delta=f"{delta_ad_spend:,.2f}")
    if has_last_month:
        st.caption(f"上月：${last_ad_spend:,.2f} | 环比：{pct_ad_spend:.1%}")
with row1_col2:
    st.metric(label="当月全店总销售额", value=f"${curr_sales:,.2f}", delta=f"{delta_sales:,.2f}")
    if has_last_month:
        st.caption(f"上月：${last_sales:,.2f} | 环比：{pct_sales:.1%}")
with row1_col3:
    st.metric(label="当月广告订单总数", value=f"{curr_ad_order:,.0f}", delta=f"{delta_ad_order:,.0f}")
    if has_last_month:
        st.caption(f"上月：{last_ad_order:,.0f} | 环比：{pct_ad_order:.1%}")
with row1_col4:
    st.metric(label="当月全店总订单", value=f"{curr_all_order:,.0f}", delta=f"{delta_all_order:,.0f}")
    if has_last_month:
        st.caption(f"上月：{last_all_order:,.0f} | 环比：{pct_all_order:.1%}")

# 第二行4卡：TACOS、ACOS、ROAS、ASoAS
row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
with row2_col1:
    st.metric(label="当月TACOS广告花费占比", value=f"{curr_tacos:.2%}", delta=f"{delta_tacos:.2%}")
    if has_last_month:
        st.caption(f"上月：{last_tacos:.2%} | 环比：{pct_tacos:.1%}")
with row2_col2:
    st.metric(label="当月广告ACOS", value=f"{curr_acos:.2%}", delta=f"{delta_acos:.2%}")
    if has_last_month:
        st.caption(f"上月：{last_acos:.2%} | 环比：{pct_acos:.1%}")
with row2_col3:
    st.metric(label="当月广告ROAS投产比", value=f"{curr_roas:.2f}", delta=f"{delta_roas:.2f}")
    if has_last_month:
        st.caption(f"上月：{last_roas:.2f} | 环比：{pct_roas:.1%}")
with row2_col4:
    st.metric(label="当月广告销售依赖度ASoAS", value=f"{curr_asoas:.2%}", delta=f"{delta_asoas:.2%}")
    if has_last_month:
        st.caption(f"上月：{last_asoas:.2%} | 环比：{pct_asoas:.1%}")

# 第三行3卡：CPC、CTR、CVR
row3_col1, row3_col2, row3_col3 = st.columns(3)
with row3_col1:
    st.metric(label="当月平均单次点击CPC", value=f"${curr_cpc:.2f}", delta=f"{delta_cpc:.2f}")
    if has_last_month:
        st.caption(f"上月：${last_cpc:.2f} | 环比：{pct_cpc:.1%}")
with row3_col2:
    st.metric(label="当月平均点击率CTR", value=f"{curr_ctr:.2%}", delta=f"{delta_ctr:.2%}")
    if has_last_month:
        st.caption(f"上月：{last_ctr:.2%} | 环比：{pct_ctr:.1%}")
with row3_col3:
    st.metric(label="当月平均广告转化率CVR", value=f"{curr_cvr:.2%}", delta=f"{delta_cvr:.2%}")
    if has_last_month:
        st.caption(f"上月：{last_cvr:.2%} | 环比：{pct_cvr:.1%}")

# 当月概况说明文字
st.info(f"""
【{select_month}单月概况说明】
分析店铺：{select_shop} | 分析月份：{select_month}
1. 当月广告投放总额 ${curr_ad_spend:,.2f}，店铺全部总销售额 ${curr_sales:,.2f}，广告花费占营收比重TACOS {curr_tacos:.2%}
2. 当月广告自身转化成本ACOS {curr_acos:.2%}，每投入1美金广告带来 {curr_roas:.2f} 美金广告营收
3. 当月店铺 {curr_asoas:.2%} 的营收来自付费广告，剩余为自然免费流量订单
4. 当月单次点击成本CPC ${curr_cpc:.2f}，广告曝光点击率CTR {curr_ctr:.2%}，点击下单转化率 {curr_cvr:.2%}
""")

# 当月完整明细表格
st.subheader(f"📋 {select_month} 当月完整指标明细表")
show_month_cols = [
    "年月", "展示", "点击", "广告花费", "销售额", "广告销售额",
    "TACOS广告花费占比", "ACOS", "ROAS", "CPC", "CTR", "CVR广告转化率",
    "ASoAS广告销售依赖度", "SP广告花费占比", "SB广告花费占比", "SBV广告花费占比"
]
st.dataframe(df_month_single[show_month_cols], use_container_width=True, height=220)

# ===================== 二、全周期多月份趋势（对比历史变化，分析上涨） =====================
st.markdown("## 📈 二、全周期月度趋势对比（查看历史TACOS涨跌变化）")
# 提取该店铺全部月份数据用于趋势图
df_shop_all_month = df_raw[df_raw["店铺"] == select_shop].copy()
df_all_month_agg = df_shop_all_month.groupby("年月").agg({
    "展示": "sum",
    "点击": "sum",
    "广告花费": "sum",
    "SP广告费": "sum",
    "SB广告费": "sum",
    "SBV广告费": "sum",
    "广告销售额": "sum",
    "广告订单量": "sum",
    "销售额": "sum",
    "订单量": "sum"
}).reset_index()

# 批量计算全周期各月衍生指标
df_all_month_agg["CTR"] = np.where(df_all_month_agg["展示"] == 0, 0,
                                   df_all_month_agg["点击"] / df_all_month_agg["展示"])
df_all_month_agg["CPC"] = np.where(df_all_month_agg["点击"] == 0, 0,
                                   df_all_month_agg["广告花费"] / df_all_month_agg["点击"])
df_all_month_agg["CVR广告转化率"] = np.where(df_all_month_agg["点击"] == 0, 0,
                                             df_all_month_agg["广告订单量"] / df_all_month_agg["点击"])
df_all_month_agg["ACOS"] = np.where(df_all_month_agg["广告销售额"] == 0, 0,
                                    df_all_month_agg["广告花费"] / df_all_month_agg["广告销售额"])
df_all_month_agg["ROAS"] = np.where(df_all_month_agg["广告花费"] == 0, 0,
                                    df_all_month_agg["广告销售额"] / df_all_month_agg["广告花费"])
df_all_month_agg["TACOS广告花费占比"] = np.where(df_all_month_agg["销售额"] == 0, 0,
                                                 df_all_month_agg["广告花费"] / df_all_month_agg["销售额"])
df_all_month_agg["ASoAS广告销售依赖度"] = np.where(df_all_month_agg["销售额"] == 0, 0,
                                                   df_all_month_agg["广告销售额"] / df_all_month_agg["销售额"])
df_all_month_agg["SP广告花费占比"] = np.where(df_all_month_agg["广告花费"] == 0, 0,
                                              df_all_month_agg["SP广告费"] / df_all_month_agg["广告花费"])
df_all_month_agg["SB广告花费占比"] = np.where(df_all_month_agg["广告花费"] == 0, 0,
                                              df_all_month_agg["SB广告费"] / df_all_month_agg["广告花费"])
df_all_month_agg["SBV广告花费占比"] = np.where(df_all_month_agg["广告花费"] == 0, 0,
                                               df_all_month_agg["SBV广告费"] / df_all_month_agg["广告花费"])

# 三个趋势切换标签
tab_tacos_trend, tab_ad_struct_trend, tab_flow_trend = st.tabs([
    "TACOS&ACOS全周期走势",
    "月度SP/SB/SBV广告投放结构",
    "流量效率：CPC&CTR&CVR走势"
])
# Tab1 TACOS+ACOS双轴图
with tab_tacos_trend:
    fig_tacos = go.Figure()
    fig_tacos.add_trace(
        go.Bar(x=df_all_month_agg["年月"], y=df_all_month_agg["TACOS广告花费占比"], name="月度TACOS", yaxis="y1"))
    fig_tacos.add_trace(go.Line(x=df_all_month_agg["年月"], y=df_all_month_agg["ACOS"], name="月度ACOS", yaxis="y2",
                                line_color="#ff4b4b", line_width=3))
    fig_tacos.update_layout(
        title=f"{select_shop}店铺全周期月度TACOS与ACOS变化走势",
        yaxis1=dict(tickformat=".1%", title="TACOS广告花费占比"),
        yaxis2=dict(tickformat=".1%", overlaying="y", side="right", title="ACOS广告成本"),
        height=460
    )
    st.plotly_chart(fig_tacos, use_container_width=True)
# Tab2 广告投放结构堆叠柱状
with tab_ad_struct_trend:
    fig_ad_bar = px.bar(
        df_all_month_agg,
        x="年月",
        y=["SP广告费", "SB广告费", "SBV广告费"],
        title=f"{select_shop}店铺各月SP/SB/SBV广告投放金额",
        labels={"value": "广告花费(美金)", "variable": "广告类型"},
        height=460
    )
    st.plotly_chart(fig_ad_bar, use_container_width=True)
# Tab3 流量效率指标
with tab_flow_trend:
    fig_flow_line = go.Figure()
    fig_flow_line.add_trace(
        go.Line(x=df_all_month_agg["年月"], y=df_all_month_agg["CPC"], name="单次点击CPC", line_color="orange"))
    fig_flow_line.add_trace(
        go.Line(x=df_all_month_agg["年月"], y=df_all_month_agg["CTR"], name="点击率CTR", line_color="#2dd4bf"))
    fig_flow_line.add_trace(
        go.Line(x=df_all_month_agg["年月"], y=df_all_month_agg["CVR广告转化率"], name="广告转化率CVR",
                line_color="#22c55e"))
    fig_flow_line.update_layout(title=f"{select_shop}店铺全周期流量效率指标变化", height=460)
    st.plotly_chart(fig_flow_line, use_container_width=True)

# ===================== 三、TACOS上升自动归因分析（基于店铺全周期历史） =====================
st.markdown("## 🔎 三、广告花费占比(TACOS)上涨自动归因分析")
st.subheader("拆分全周期前半段/后半段，自动识别五大上涨根源")
split_index = len(df_all_month_agg) // 2
df_early_period = df_all_month_agg.iloc[:split_index].copy()
df_late_period = df_all_month_agg.iloc[split_index:].copy()

# 分段均值计算
early_mean_tacos = df_early_period["TACOS广告花费占比"].mean()
late_mean_tacos = df_late_period["TACOS广告花费占比"].mean()
early_mean_acos = df_early_period["ACOS"].mean()
late_mean_acos = df_late_period["ACOS"].mean()
early_mean_asoas = df_early_period["ASoAS广告销售依赖度"].mean()
late_mean_asoas = df_late_period["ASoAS广告销售依赖度"].mean()
early_mean_cpc = df_early_period["CPC"].mean()
late_mean_cpc = df_late_period["CPC"].mean()
early_mean_sp = df_early_period["SP广告花费占比"].mean()
late_mean_sp = df_late_period["SP广告花费占比"].mean()

# 销售额&广告花费总量对比
early_sales_sum = df_early_period["销售额"].sum()
late_sales_sum = df_late_period["销售额"].sum()
early_ad_sum = df_early_period["广告花费"].sum()
late_ad_sum = df_late_period["广告花费"].sum()

delta_tacos_total = late_mean_tacos - early_mean_tacos
st.write(f"""
基准期（前{split_index}个月）平均TACOS：{early_mean_tacos:.2%}
近期期（后{len(df_all_month_agg) - split_index}个月）平均TACOS：{late_mean_tacos:.2%}
整体广告花费占比涨幅：{delta_tacos_total:+.2%}
""")

reason_list = []
# 原因1 广告自身转化变差
if late_mean_acos > early_mean_acos * 1.05:
    r1 = f"1. 广告投放转化效率持续下滑：基准ACOS {early_mean_acos:.2%} → 近期 {late_mean_acos:.2%}，涨幅{(late_mean_acos - early_mean_acos):+.2%}；CPC竞价由${early_mean_cpc:.2f}升至${late_mean_cpc:.2f}，流量成本抬升，同等广告费产出更少广告营收，直接拉高TACOS。"
    reason_list.append(r1)
# 原因2 广告依赖度提升，自然流量萎缩
if late_mean_asoas > early_mean_asoas * 1.05:
    r2 = f"2. 店铺高度依赖付费广告出单：广告营收占总销售比重ASoAS由{early_mean_asoas:.2%}上涨至{late_mean_asoas:.2%}，免费自然订单持续减少，增量销量全部依靠广告拉动，TACOS被动走高。"
    reason_list.append(r2)
# 原因3 投放倾斜高成本SB/SBV广告
if late_mean_sp < early_mean_sp * 0.95:
    r3 = f"3. 广告预算结构变化：高投产SP广告投放占比下降，ACOS更高的SB/SBV品牌广告预算增加，拉高店铺整体平均广告成本，推动TACOS上行。"
    reason_list.append(r3)
# 原因4 广告投放增速远超销售额增长
sales_growth = late_sales_sum / early_sales_sum if early_sales_sum != 0 else 0
ad_growth = late_ad_sum / early_ad_sum if early_ad_sum != 0 else 0
if sales_growth < ad_growth * 0.95:
    r4 = f"4. 全店营收增长跟不上广告扩张速度：基准总销售额${early_sales_sum:,.2f}，近期${late_sales_sum:,.2f}；广告投放大幅加码，总销售额（TACOS分母）增长乏力，被动推高广告占比。"
    reason_list.append(r4)
# 原因5 大量新品集中上新拉高整体TACOS
df_type_all = df_raw[df_raw["店铺"] == select_shop].groupby("产品类型").agg({"广告花费": "sum", "销售额": "sum"})
df_type_all["TACOS"] = np.where(df_type_all["销售额"] == 0, 0, df_type_all["广告花费"] / df_type_all["销售额"])
if "新品(上架≤60天)" in df_type_all.index and "老品(上架>60天)" in df_type_all.index:
    new_tacos_val = df_type_all.loc["新品(上架≤60天)", "TACOS"]
    old_tacos_val = df_type_all.loc["老品(上架>60天)", "TACOS"]
    new_ad_ratio_val = df_type_all.loc["新品(上架≤60天)", "广告花费"] / df_raw[df_raw["店铺"] == select_shop][
        "广告花费"].sum()
    if new_tacos_val > old_tacos_val * 1.2 and new_ad_ratio_val > 0.2:
        r5 = f"5. 大批量新品集中上新拉高全店成本：新品平均TACOS {new_tacos_val:.2%}，远高于老品{old_tacos_val:.2%}；新品广告投放占店铺总广告{new_ad_ratio_val:.1%}，新品天然高广告成本抬升整体TACOS。"
        reason_list.append(r5)

# 输出归因提示
if len(reason_list) == 0:
    st.success("✅ 该店铺全周期TACOS无明显上涨，广告投放与转化效率整体稳定！")
else:
    for text in reason_list:
        st.warning(text)

# 可复制汇报总结
summary_text = f"""
【{select_shop}店铺全周期广告花费占比TACOS上涨综合分析总结】
1. 周期概况：
店铺全周期基准期平均TACOS{early_mean_tacos:.2%}，近期上涨至{late_mean_tacos:.2%}，涨幅{delta_tacos_total:+.2%}。

2. TACOS上涨核心驱动因素：
"""
for item in reason_list:
    summary_text += "\n" + item
summary_text += """
3. 落地优化方向：
① 优化SP关键词，关停高CPC低转化词，降低整体ACOS；
② 优化Listing、积累评论、站外引流，提升自然流量，降低广告依赖度ASoAS；
③ 控制SB/SBV品牌广告预算，优先加大高投产SP投放；
④ 新品前置积累评论，缩短新品高广告成本周期，匹配新品营收增速控制投放预算；
⑤ 搭配促销、新品动作拉升全店总销售额，扩大TACOS分母降低广告占比。
"""
st.text_area("📝 一键复制至Word汇报完整总结", summary_text, height=350)

# ===================== 四、分层数据拆解：品类 / MSKU单品 / 新品老品对比 =====================
st.markdown("## 🧩 四、分层数据拆解：定位拉高TACOS的核心品类/单品/新品")
tab_cat, tab_msku, tab_newold = st.tabs(["按品类汇总分析", "按MSKU单品明细", "新品VS老品投放对比"])

# 4.1 品类汇总（当前选中店铺全周期）
df_cat_all = df_raw[df_raw["店铺"] == select_shop].groupby("品类").agg({
    "广告花费": "sum",
    "销售额": "sum",
    "广告销售额": "sum",
    "点击": "sum"
}).reset_index()
df_cat_all["TACOS品类广告占比"] = np.where(df_cat_all["销售额"] == 0, 0, df_cat_all["广告花费"] / df_cat_all["销售额"])
df_cat_all["ACOS品类广告成本"] = np.where(df_cat_all["广告销售额"] == 0, 0,
                                          df_cat_all["广告花费"] / df_cat_all["广告销售额"])
df_cat_all["品类销售贡献占比"] = df_cat_all["销售额"] / df_cat_all["销售额"].sum()
df_cat_all = df_cat_all.sort_values("TACOS品类广告占比", ascending=False)
with tab_cat:
    st.dataframe(df_cat_all, use_container_width=True, height=360)
    st.caption("按TACOS从高到低排序，重点关注销售贡献高、广告成本异常偏高的品类")

# 4.2 MSKU单品明细（当前店铺全周期）
df_msku_all = df_raw[df_raw["店铺"] == select_shop].groupby(["品类", "MSKU", "品名", "产品类型"]).agg({
    "广告花费": "sum",
    "销售额": "sum",
    "广告销售额": "sum",
    "点击": "sum"
}).reset_index()
df_msku_all["TACOS单品广告占比"] = np.where(df_msku_all["销售额"] == 0, 0,
                                            df_msku_all["广告花费"] / df_msku_all["销售额"])
df_msku_all["ACOS单品广告成本"] = np.where(df_msku_all["广告销售额"] == 0, 0,
                                           df_msku_all["广告花费"] / df_msku_all["广告销售额"])
df_msku_all["单品销售贡献占比"] = df_msku_all["销售额"] / df_msku_all["销售额"].sum()
df_msku_all = df_msku_all.sort_values("单品销售贡献占比", ascending=False)
with tab_msku:
    st.dataframe(df_msku_all, use_container_width=True, height=420)
    st.caption("按单品销售额贡献从高到低排序，区分新品/老品查看爆款广告成本")

# 4.3 新品老品对比
with tab_newold:
    st.subheader("1、全周期新品/老品整体指标对比")
    df_type_compare = df_raw[df_raw["店铺"] == select_shop].groupby("产品类型").agg({
        "广告花费": "sum",
        "销售额": "sum",
        "广告销售额": "sum",
        "点击": "sum"
    }).reset_index()
    df_type_compare["TACOS"] = np.where(df_type_compare["销售额"] == 0, 0,
                                        df_type_compare["广告花费"] / df_type_compare["销售额"])
    df_type_compare["ACOS"] = np.where(df_type_compare["广告销售额"] == 0, 0,
                                       df_type_compare["广告花费"] / df_type_compare["广告销售额"])
    df_type_compare["广告花费占全店比重"] = df_type_compare["广告花费"] / df_raw[df_raw["店铺"] == select_shop][
        "广告花费"].sum()
    df_type_compare["销售贡献占比"] = df_type_compare["销售额"] / df_raw[df_raw["店铺"] == select_shop]["销售额"].sum()
    df_type_compare = df_type_compare.sort_values("广告花费", ascending=False)
    st.dataframe(df_type_compare, use_container_width=True, height=250)

    st.subheader("2、月度新品/老品广告花费堆叠趋势")
    df_month_type_stack = df_raw[df_raw["店铺"] == select_shop].groupby(["年月", "产品类型"]).agg(
        {"广告花费": "sum", "销售额": "sum"}).reset_index()
    fig_stack = px.bar(
        df_month_type_stack,
        x="年月",
        y="广告花费",
        color="产品类型",
        title=f"{select_shop}店铺每月新品/老品广告投放金额",
        labels={"广告花费": "广告花费(美金)"},
        height=420
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    st.subheader("3、新品&老品月度TACOS走势对比")
    df_month_type_tacos = df_month_type_stack.copy()
    df_month_type_tacos["TACOS"] = np.where(df_month_type_tacos["销售额"] == 0, 0,
                                            df_month_type_tacos["广告花费"] / df_month_type_tacos["销售额"])
    fig_line_tacos = px.line(
        df_month_type_tacos,
        x="年月",
        y="TACOS",
        color="产品类型",
        title=f"{select_shop}店铺新品/老品月度TACOS对比",
        labels={"TACOS": "广告花费占比"},
        height=420
    )
    fig_line_tacos.update_layout(yaxis_tickformat=".1%")
    st.plotly_chart(fig_line_tacos, use_container_width=True)