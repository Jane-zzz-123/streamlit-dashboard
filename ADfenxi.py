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
    initial_sidebar_state="expanded"
)
st.title("📊 亚马逊店铺广告花费占比(TACOS)上升归因分析 | 2025.01-2026.05")
st.markdown("""
分析逻辑：店铺月度整体大盘概览 → 月度趋势定位TACOS抬升区间 → 自动归因上涨四大核心原因 → 品类/MSKU单品细分拆解
数据源：ADdata_all.xlsx sheet=源数据，仅读取基础字段，广告效率指标(CTR/CPC/ACOS/TACOS等)代码自动计算
""")


# -------------------------- 缓存加载原始数据 --------------------------
@st.cache_data
def load_raw_data():
    # 读取github线上Excel
    url = "https://github.com/Jane-zzz-123/streamlit-dashboard/raw/main/ADdata_all.xlsx"
    resp = requests.get(url)
    df = pd.read_excel(BytesIO(resp.content), sheet_name="源数据")

    # 时间字段标准化
    df["时间"] = pd.to_datetime(df["时间"])
    df["年月"] = df["时间"].dt.to_period("M").astype(str)

    # 基础数值列转为浮点，防止计算报错
    # 修正后代码
    num_cols = [
        "展示", "点击", "广告花费", "SP广告费", "SB广告费", "SBV广告费",
        "广告销售额", "SP广告销售额", "SB广告销售额", "SBV广告销售额",
        "广告订单量", "SP广告订单量", "SB广告订单量", "SBV广告订单量",
        "销量", "销售额", "订单量"
    ]
    for col in num_cols:
        # errors='coerce'：无法转数字的内容强制变成NaN，后续填充0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


df_raw = load_raw_data()

# -------------------------- 侧边栏筛选器 --------------------------
with st.sidebar:
    st.header("🔍 数据筛选条件")
    # 店铺筛选
    shop_list = sorted(df_raw["店铺"].unique())
    selected_shop = st.selectbox("选择分析店铺", shop_list)
    # 时间区间筛选
    min_date = df_raw["时间"].min()
    max_date = df_raw["时间"].max()
    date_range = st.date_input(
        "选择分析时间范围",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    start_dt, end_dt = date_range
    # 品类多选
    cat_list = sorted(df_raw["品类"].unique())
    selected_cat = st.multiselect("筛选品类（默认全选）", cat_list, default=cat_list)

# -------------------------- 筛选后数据集 --------------------------
df_filter = df_raw[
    (df_raw["店铺"] == selected_shop) &
    (df_raw["时间"] >= pd.to_datetime(start_dt)) &
    (df_raw["时间"] <= pd.to_datetime(end_dt)) &
    (df_raw["品类"].isin(selected_cat))
    ].copy()

if df_filter.empty:
    st.warning("⚠️ 当前筛选条件无匹配数据，请重新调整店铺/时间/品类筛选！")
    st.stop()

# -------------------------- 1. 按月聚合店铺大盘数据（核心月度分析层） --------------------------
df_month = df_filter.groupby("年月").agg({
    "展示": "sum",
    "点击": "sum",
    "广告花费": "sum",
    "SP广告费": "sum",
    "SB广告费": "sum",
    "SBV广告费": "sum",
    "广告销售额": "sum",
    "广告订单量": "sum",
    "销售额": "sum",  # 全店总销售额（广告+自然单，TACOS分母）
    "订单量": "sum"
}).reset_index()

# ========== 自动计算全部衍生广告指标（无需要Excel提前导出） ==========
# 1. 流量效率指标
df_month["CTR"] = np.where(df_month["展示"] == 0, 0, df_month["点击"] / df_month["展示"])
df_month["CPC"] = np.where(df_month["点击"] == 0, 0, df_month["广告花费"] / df_month["点击"])
df_month["CVR广告转化率"] = np.where(df_month["点击"] == 0, 0, df_month["广告订单量"] / df_month["点击"])

# 2. 广告投产核心指标
df_month["ACOS"] = np.where(df_month["广告销售额"] == 0, 0, df_month["广告花费"] / df_month["广告销售额"])
df_month["ROAS"] = np.where(df_month["广告花费"] == 0, 0, df_month["广告销售额"] / df_month["广告花费"])

# 3. TACOS（本次分析核心：广告花费占全店总销售额比重）
df_month["TACOS广告花费占比"] = np.where(df_month["销售额"] == 0, 0, df_month["广告花费"] / df_month["销售额"])
# ASoAS 广告销售额占全店总销售比重（店铺广告依赖度）
df_month["ASoAS广告销售依赖度"] = np.where(df_month["销售额"] == 0, 0, df_month["广告销售额"] / df_month["销售额"])
# CPO 单次广告订单成本
df_month["CPO单广告订单成本"] = np.where(df_month["广告订单量"] == 0, 0, df_month["广告花费"] / df_month["广告订单量"])

# 4. 广告投放结构占比
df_month["SP广告花费占比"] = np.where(df_month["广告花费"] == 0, 0, df_month["SP广告费"] / df_month["广告花费"])
df_month["SB广告花费占比"] = np.where(df_month["广告花费"] == 0, 0, df_month["SB广告费"] / df_month["广告花费"])
df_month["SBV广告花费占比"] = np.where(df_month["广告花费"] == 0, 0, df_month["SBV广告费"] / df_month["广告花费"])

# -------------------------- 2. 全周期汇总指标（顶部核心指标卡片） --------------------------
total_ad_spend = df_filter["广告花费"].sum()
total_all_sales = df_filter["销售额"].sum()
total_ad_sales = df_filter["广告销售额"].sum()
total_click = df_filter["点击"].sum()
total_imp = df_filter["展示"].sum()
total_ad_order = df_filter["广告订单量"].sum()

# 周期整体平均指标
avg_tacos = np.where(total_all_sales == 0, 0, total_ad_spend / total_all_sales)
avg_acos = np.where(total_ad_sales == 0, 0, total_ad_spend / total_ad_sales)
avg_cpc = np.where(total_click == 0, 0, total_ad_spend / total_click)
avg_roas = np.where(total_ad_spend == 0, 0, total_ad_sales / total_ad_spend)
avg_asoas = np.where(total_all_sales == 0, 0, total_ad_sales / total_all_sales)
avg_cvr = np.where(total_click == 0, 0, total_ad_order / total_click)

# ===================== 第一部分：店铺整体月度概况与核心指标 =====================
st.markdown("## 🎯 一、店铺整体数据月度概况（筛选周期大盘）")
# 两行8个核心指标卡片
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("周期总广告花费", f"${total_ad_spend:,.2f}")
with col2:
    st.metric("周期全店总销售额", f"${total_all_sales:,.2f}")
with col3:
    st.metric("整体TACOS广告花费占比", f"{avg_tacos:.2%}")
with col4:
    st.metric("广告ACOS", f"{avg_acos:.2%}")

col5, col6, col7, col8 = st.columns(4)
with col5:
    st.metric("平均单次点击CPC", f"${avg_cpc:.2f}")
with col6:
    st.metric("广告ROAS投产比", f"{avg_roas:.2f}")
with col7:
    st.metric("广告销售依赖度ASoAS", f"{avg_asoas:.2%}")
with col8:
    st.metric("平均广告转化率CVR", f"{avg_cvr:.2%}")

# 整体概况文字总结
st.info(f"""
【店铺整体概况说明】
分析店铺：{selected_shop} | 分析时间区间：{start_dt} ~ {end_dt}
1. 筛选周期内广告总投放金额 ${total_ad_spend:,.2f}，店铺全部总销售额 ${total_all_sales:,.2f}，广告花费占全店营收比重TACOS均值 {avg_tacos:.2%}（本次核心分析指标）
2. 广告自身转化成本ACOS均值 {avg_acos:.2%}，每投入1美金广告带来 {avg_roas:.2f} 美金广告订单营收
3. 店铺营收中 {avg_asoas:.2%} 来自广告付费流量，剩余为自然免费流量订单
4. 广告平均单次点击成本CPC ${avg_cpc:.2f}，广告点击下单转化率 {avg_cvr:.2%}
""")

# 展示完整月度明细表格（单月整体情况查看）
st.subheader("📋 店铺单月完整指标明细表")
show_month_cols = [
    "年月", "展示", "点击", "广告花费", "销售额", "广告销售额",
    "TACOS广告花费占比", "ACOS", "ROAS", "CPC", "CTR", "CVR广告转化率",
    "ASoAS广告销售依赖度", "SP广告花费占比", "SB广告花费占比", "SBV广告花费占比"
]
st.dataframe(df_month[show_month_cols], use_container_width=True, height=320)

# ===================== 第二部分：月度趋势图表（定位TACOS抬升时间段） =====================
st.markdown("## 📈 二、月度趋势分析（定位广告花费占比TACOS持续上涨区间）")
tab_tacos, tab_ad_struct, tab_efficiency = st.tabs([
    "TACOS&ACOS双轴趋势",
    "月度SP/SB/SBV广告投放结构",
    "流量效率：CPC & CTR & CVR"
])

# Tab1 TACOS与ACOS走势（判断是广告变差带动TACOS上涨）
with tab_tacos:
    fig_tacos = go.Figure()
    fig_tacos.add_trace(
        go.Bar(x=df_month["年月"], y=df_month["TACOS广告花费占比"], name="月度TACOS广告花费占比", yaxis="y1")
    )
    fig_tacos.add_trace(
        go.Line(x=df_month["年月"], y=df_month["ACOS"], name="月度广告ACOS", yaxis="y2", line_color="#ff4b4b",
                line_width=3)
    )
    fig_tacos.update_layout(
        title="月度TACOS(全店广告占比)与ACOS(广告自身转化成本)走势",
        yaxis1=dict(tickformat=".1%", title="TACOS广告花费占比"),
        yaxis2=dict(tickformat=".1%", overlaying="y", side="right", title="ACOS广告成本"),
        height=460
    )
    st.plotly_chart(fig_tacos, use_container_width=True)

# Tab2 广告投放结构堆叠柱状（判断是否高成本SB/SBV预算增加拉高整体成本）
with tab_ad_struct:
    fig_ad_struct = px.bar(
        df_month,
        x="年月",
        y=["SP广告费", "SB广告费", "SBV广告费"],
        title="每月SP商品广告 / SB品牌广告 / SBV视频广告投放金额分布",
        labels={"value": "广告花费(美金)", "variable": "广告类型"},
        height=460
    )
    st.plotly_chart(fig_ad_struct, use_container_width=True)

# Tab3 流量效率指标走势（CPC、CTR、转化率判断广告流量质量变化）
with tab_efficiency:
    fig_eff = go.Figure()
    fig_eff.add_trace(go.Line(x=df_month["年月"], y=df_month["CPC"], name="单次点击CPC", line_color="orange"))
    fig_eff.add_trace(go.Line(x=df_month["年月"], y=df_month["CTR"], name="点击率CTR", line_color="#2dd4bf"))
    fig_eff.add_trace(
        go.Line(x=df_month["年月"], y=df_month["CVR广告转化率"], name="广告转化率CVR", line_color="#22c55e"))
    fig_eff.update_layout(title="月度广告流量效率指标变化", height=460)
    st.plotly_chart(fig_eff, use_container_width=True)

# ===================== 第三部分：TACOS广告花费占比上升自动归因（核心分析模块） =====================
st.markdown("## 🔎 三、广告花费占比(TACOS)上升原因自动归因分析")
st.subheader("对比基准期(前半周期) vs 近期期(后半周期)指标变化，自动识别4大类上涨根源")

# 拆分前后两段周期对比
split_point = len(df_month) // 2
df_early = df_month.iloc[:split_point].copy()
df_late = df_month.iloc[split_point:].copy()

# 计算两段周期均值
early_tacos = df_early["TACOS广告花费占比"].mean()
late_tacos = df_late["TACOS广告花费占比"].mean()
early_acos = df_early["ACOS"].mean()
late_acos = df_late["ACOS"].mean()
early_asoas = df_early["ASoAS广告销售依赖度"].mean()
late_asoas = df_late["ASoAS广告销售依赖度"].mean()
early_cpc = df_early["CPC"].mean()
late_cpc = df_late["CPC"].mean()
early_sp_ratio = df_early["SP广告花费占比"].mean()
late_sp_ratio = df_late["SP广告花费占比"].mean()

# 全店销售额、广告花费总量对比
early_total_sales = df_early["销售额"].sum()
late_total_sales = df_late["销售额"].sum()
early_total_ad = df_early["广告花费"].sum()
late_total_ad = df_late["广告花费"].sum()

# 输出两段周期对比数据
delta_tacos = late_tacos - early_tacos
st.write(f"""
基准期（前{split_point}个月）平均TACOS：{early_tacos:.2%}
近期期（后{len(df_month) - split_point}个月）平均TACOS：{late_tacos:.2%}
整体广告花费占比变化幅度：{delta_tacos:+.2%}
""")

# 自动判定四大类上涨原因
reason_list = []
# 原因1：广告自身转化效率变差（ACOS上行、CPC竞价抬升）
if late_acos > early_acos * 1.05:
    r1 = f"1. 广告投放自身转化效率持续下滑：基准ACOS {early_acos:.2%} → 近期 {late_acos:.2%}，涨幅{(late_acos - early_acos):+.2%}；单次点击成本CPC由${early_cpc:.2f}升至${late_cpc:.2f}，竞价成本抬升，同等广告费带来的广告营收减少，直接拉高TACOS。"
    reason_list.append(r1)

# 原因2：店铺对广告流量依赖加重，自然流量萎缩（ASoAS上涨）
if late_asoas > early_asoas * 1.05:
    r2 = f"2. 店铺营收高度依赖付费广告：广告营收占全店总销售比重ASoAS由{early_asoas:.2%}上涨至{late_asoas:.2%}，免费自然流量、自然订单持续萎缩，更多销量必须依靠广告付费撬动，即使广告转化不变，TACOS也会被动走高。"
    reason_list.append(r2)

# 原因3：广告投放结构倾斜高成本品牌广告SB/SBV
if late_sp_ratio < early_sp_ratio * 0.95:
    r3 = f"3. 广告预算投放结构发生变化：低成本高转化SP搜索广告投放占比下降，ACOS普遍更高的SB品牌广告、SBV视频广告预算持续增加，拉高店铺整体平均广告成本，带动TACOS上行。"
    reason_list.append(r3)

# 原因4：全店总销售额增速低于广告投放增速，分母收缩推高TACOS
sales_grow_rate = late_total_sales / early_total_sales if early_total_sales != 0 else 0
ad_grow_rate = late_total_ad / early_total_ad if early_total_ad != 0 else 0
if sales_grow_rate < ad_grow_rate * 0.95:
    r4 = f"4. 全店总营收增长跟不上广告投放扩张速度：基准期总销售额${early_total_sales:,.2f}，近期${late_total_sales:,.2f}；广告投放同步大幅增加，全店总销售额（TACOS分母）收缩，被动推高广告花费占比。"
    reason_list.append(r4)

# 输出归因结论
if len(reason_list) == 0:
    st.success("✅ 当前分析周期内TACOS无明显上涨，广告投放结构、转化效率保持稳定！")
else:
    for text in reason_list:
        st.warning(text)

# 可直接复制进工作报告的综合总结文案
summary_text = f"""
【{selected_shop}店铺2025.01-2026.05广告花费占比TACOS上涨综合分析总结】
1. 周期整体概况：
分析区间{start_dt}至{end_dt}，总广告投放${total_ad_spend:,.2f}，全店总销售额${total_all_sales:,.2f}，整体TACOS均值{avg_tacos:.2%}；基准期平均TACOS{early_tacos:.2%}，近期上涨至{late_tacos:.2%}，涨幅{delta_tacos:+.2%}。

2. TACOS上涨核心驱动因素：
"""
for item in reason_list:
    summary_text += "\n" + item
summary_text += """
3. 针对性优化方向参考：
① 优化SP关键词竞价，筛选高CPC低转化关键词降价/关停，降低整体ACOS；
② 挖掘自然流量增长点（优化Listing、积累评论、站外引流），降低店铺广告销售依赖度ASoAS；
③ 控制SB/SBV高成本品牌广告预算，优先加大高投产SP广告投放；
④ 通过新品、促销、价格策略拉升全店总销售额，扩大TACOS分母，降低广告花费占比。
"""
st.text_area("📝 一键复制至Word汇报的完整总结文本", summary_text, height=350)

# ===================== 第四部分：分层下钻拆解（品类 / MSKU单品） =====================
st.markdown("## 🧩 四、分层数据拆解：定位拉高整体TACOS的核心品类/单品")
tab_category, tab_msku = st.tabs(["按品类汇总分析", "按MSKU单品明细分析"])

# 4.1 品类聚合表
df_cat = df_filter.groupby("品类").agg({
    "广告花费": "sum",
    "销售额": "sum",
    "广告销售额": "sum",
    "点击": "sum"
}).reset_index()
# 品类衍生指标
df_cat["TACOS品类广告占比"] = np.where(df_cat["销售额"] == 0, 0, df_cat["广告花费"] / df_cat["销售额"])
df_cat["ACOS品类广告成本"] = np.where(df_cat["广告销售额"] == 0, 0, df_cat["广告花费"] / df_cat["广告销售额"])
df_cat["品类销售贡献占比"] = df_cat["销售额"] / df_cat["销售额"].sum()
df_cat = df_cat.sort_values("TACOS品类广告占比", ascending=False)

with tab_category:
    st.dataframe(df_cat, use_container_width=True, height=360)
    st.caption("排序规则：TACOS从高到低，优先关注「销售贡献占比高+TACOS显著偏高」的品类，是拉高全店广告占比的核心板块")

# 4.2 MSKU单品聚合表
df_msku = df_filter.groupby(["品类", "MSKU", "品名"]).agg({
    "广告花费": "sum",
    "销售额": "sum",
    "广告销售额": "sum",
    "点击": "sum"
}).reset_index()
# MSKU衍生指标
df_msku["TACOS单品广告占比"] = np.where(df_msku["销售额"] == 0, 0, df_msku["广告花费"] / df_msku["销售额"])
df_msku["ACOS单品广告成本"] = np.where(df_msku["广告销售额"] == 0, 0, df_msku["广告花费"] / df_msku["广告销售额"])
df_msku["单品销售贡献占比"] = df_msku["销售额"] / df_msku["销售额"].sum()
df_msku = df_msku.sort_values("单品销售贡献占比", ascending=False)

with tab_msku:
    st.dataframe(df_msku, use_container_width=True, height=420)
    st.caption("排序规则：单品销售额贡献从高到低，重点查看头部爆款MSKU的TACOS是否异常抬升")