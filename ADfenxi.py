import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from io import BytesIO

# ===================== 页面基础配置 =====================
st.set_page_config(
    page_title="亚马逊广告TACOS归因分析看板",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.title("📊 亚马逊店铺广告花费占比(TACOS)上升归因分析 | 2025.01-2026.05")


# ===================== 缓存加载数据 =====================
@st.cache_data
def load_data():
    # 读取github线上Excel
    url = "https://github.com/Jane-zzz-123/streamlit-dashboard/raw/main/ADdata_all.xlsx"
    resp = requests.get(url)
    df = pd.read_excel(BytesIO(resp.content), sheet_name="源数据")

    # 时间列转为日期格式
    df["时间"] = pd.to_datetime(df["时间"])
    # 新增年月字段，用于按月聚合
    df["年月"] = df["时间"].dt.to_period("M").astype(str)
    return df


df_raw = load_data()

# ===================== 侧边栏筛选器 =====================
with st.sidebar:
    st.header("🔍 数据筛选条件")

    # 店铺筛选
    shop_list = sorted(df_raw["店铺"].unique())
    selected_shop = st.selectbox("选择店铺", shop_list)

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
    selected_cat = st.multiselect("选择品类", cat_list, default=cat_list)

# ===================== 筛选后数据集 =====================
df_filter = df_raw[
    (df_raw["店铺"] == selected_shop) &
    (df_raw["时间"] >= pd.to_datetime(start_dt)) &
    (df_raw["时间"] <= pd.to_datetime(end_dt)) &
    (df_raw["品类"].isin(selected_cat))
    ].copy()

if df_filter.empty:
    st.warning("当前筛选条件下无数据，请重新选择筛选参数！")
    st.stop()

# ===================== 按月聚合大盘数据 =====================
df_month = df_filter.groupby("年月").agg({
    "广告花费": "sum",
    "SP广告费": "sum",
    "SB广告费": "sum",
    "SBV广告费": "sum",
    "广告销售额": "sum",
    "销量": "sum",
    "订单量": "sum",
    "展示": "sum",
    "点击": "sum"
}).reset_index()

# 计算月度衍生指标
df_month["总销售额"] = df_month["销量"]  # 你表中销量字段=总营收，如字段名不同自行替换
df_month["TACOS"] = df_month["广告花费"] / df_month["总销售额"]
df_month["ACOS"] = df_month["广告花费"] / df_month["广告销售额"]
df_month["CPC"] = df_month["广告花费"] / df_month["点击"]
df_month["ROAS"] = df_month["广告销售额"] / df_month["广告花费"]
df_month["广告花费占比_SP"] = df_month["SP广告费"] / df_month["广告花费"]
df_month["广告花费占比_SB"] = df_month["SB广告费"] / df_month["广告花费"]
df_month["广告花费占比_SBV"] = df_month["SBV广告费"] / df_month["广告花费"]

# 全周期汇总指标（顶部卡片使用）
total_ad_spend = df_filter["广告花费"].sum()
total_sales = df_filter["销量"].sum()
total_ad_sales = df_filter["广告销售额"].sum()
total_click = df_filter["点击"].sum()
total_imp = df_filter["展示"].sum()

avg_tacos = total_ad_spend / total_sales
avg_acos = total_ad_spend / total_ad_sales
avg_cpc = total_ad_spend / total_click
avg_roas = total_ad_sales / total_ad_spend
ad_sales_ratio = total_ad_sales / total_sales  # ASoAS 广告销售额占全店销售比重

# ===================== 一、整体概括+核心指标卡片 =====================
st.markdown("## 🎯 一、店铺整体数据概括与核心指标")
# 8个核心指标分两排展示
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("总广告花费", f"${total_ad_spend:,.2f}")
with col2:
    st.metric("全店总销售额", f"${total_sales:,.2f}")
with col3:
    st.metric("整体TACOS(广告花费占比)", f"{avg_tacos:.2%}")
with col4:
    st.metric("广告ACOS", f"{avg_acos:.2%}")

col5, col6, col7, col8 = st.columns(4)
with col5:
    st.metric("平均CPC单次点击成本", f"${avg_cpc:.2f}")
with col6:
    st.metric("广告ROAS投产比", f"{avg_roas:.2f}")
with col7:
    st.metric("广告销售额占全店比重(ASoAS)", f"{ad_sales_ratio:.2%}")
with col8:
    st.metric("总广告点击量", f"{total_click:,.0f}")

# 文字整体概括
st.info(f"""
【整体概况】
分析店铺：{selected_shop} | 分析周期：{start_dt} ~ {end_dt}
1. 周期内总广告投放 ${total_ad_spend:,.2f}，全店总销售额 ${total_sales:,.2f}，整体广告花费占比TACOS均值 {avg_tacos:.2%}
2. 广告自身转化ACOS均值 {avg_acos:.2%}，广告带来销售额占全店总营收 {ad_sales_ratio:.2%}
3. 平均单次点击成本CPC ${avg_cpc:.2f}，广告投产比ROAS {avg_roas:.2f}
""")

# ===================== 二、月度趋势图表（定位TACOS上涨时间段） =====================
st.markdown("## 📈 二、月度趋势分析（定位TACOS抬升区间）")
tab1, tab2, tab3 = st.tabs(["TACOS&ACOS双轴趋势", "广告投放结构变化", "CPC&ROAS流量效率"])

# Tab1：TACOS ACOS趋势
with tab1:
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(x=df_month["年月"], y=df_month["TACOS"], name="TACOS广告花费占比", yaxis="y1"))
    fig1.add_trace(
        go.Line(x=df_month["年月"], y=df_month["ACOS"], name="ACOS广告转化成本", yaxis="y2", line_color="red"))
    fig1.update_layout(
        yaxis1=dict(tickformat=".1%", title="TACOS"),
        yaxis2=dict(tickformat=".1%", overlaying="y", side="right", title="ACOS"),
        title="月度TACOS(全店广告占比)与ACOS(广告单成本)走势",
        height=450
    )
    st.plotly_chart(fig1, use_container_width=True)

# Tab2：SP/SB/SBV广告花费结构堆叠柱状
with tab2:
    fig2 = px.bar(
        df_month, x="年月",
        y=["SP广告费", "SB广告费", "SBV广告费"],
        title="每月SP/SB/SBV广告投放金额分布",
        labels={"value": "广告花费", "variable": "广告类型"},
        height=450
    )
    st.plotly_chart(fig2, use_container_width=True)

# Tab3：CPC与ROAS变化
with tab3:
    fig3 = go.Figure()
    fig3.add_trace(go.Line(x=df_month["年月"], y=df_month["CPC"], name="平均CPC", line_color="orange"))
    fig3.add_trace(go.Line(x=df_month["年月"], y=df_month["ROAS"], name="广告ROAS", line_color="green"))
    fig3.update_layout(title="月度CPC点击成本 & ROAS投产比走势", height=450)
    st.plotly_chart(fig3, use_container_width=True)

# ===================== 三、TACOS上涨自动归因分析（核心模块） =====================
st.markdown("## 🔎 三、广告花费占比(TACOS)上升原因自动归因")
st.subheader("四大核心上涨逻辑判断")

# 拆分前期/后期两段对比，判断涨跌
mid_idx = len(df_month) // 2
df_early = df_month.iloc[:mid_idx]
df_late = df_month.iloc[mid_idx:]

early_tacos = df_early["TACOS"].mean()
late_tacos = df_late["TACOS"].mean()
early_acos = df_early["ACOS"].mean()
late_acos = df_late["ACOS"].mean()
early_asoas = df_early["广告销售额"].sum() / df_early["总销售额"].sum()
late_asoas = df_late["广告销售额"].sum() / df_late["总销售额"].sum()
early_cpc = df_early["CPC"].mean()
late_cpc = df_late["CPC"].mean()
early_sp_ratio = df_early["SP广告费"].sum() / df_early["广告花费"].sum()
late_sp_ratio = df_late["SP广告费"].sum() / df_late["广告花费"].sum()

reason_list = []
st.write(
    f"对比基准期(前半段)平均TACOS：{early_tacos:.2%}，近期(后半段)平均TACOS：{late_tacos:.2%}，整体变化：{(late_tacos - early_tacos):+.2%}")

# 原因1：广告转化变差（ACOS上行）
if late_acos > early_acos * 1.05:
    r1 = f"1. 广告自身转化效率下滑：基准ACOS {early_acos:.2%} → 近期 {late_acos:.2%}，涨幅{(late_acos - early_acos):+.2%}；CPC从{early_cpc:.2f}升至{late_cpc:.2f}，单次点击成本抬升，同等花费带来广告销售额减少，直接拉高TACOS。"
    reason_list.append(r1)

# 原因2：广告销售依赖度提升（ASoAS上涨，广告单占总销售变多）
if late_asoas > early_asoas * 1.05:
    r2 = f"2. 店铺销售高度依赖广告流量：广告营收占全店比重ASoAS由{early_asoas:.2%}升至{late_asoas:.2%}，自然流量/自然单萎缩，更多销量需要广告付费撬动，推高整体广告花费占比。"
    reason_list.append(r2)

# 原因3：投放结构倾斜高成本广告(SB/SBV)
if late_sp_ratio < early_sp_ratio * 0.95:
    r3 = f"3. 广告投放结构变化：低成本SP搜索广告投放占比下降，品牌广告SB/SBV预算提升；品牌广告普遍ACOS更高，拉高整体平均广告成本，带动TACOS上行。"
    reason_list.append(r3)

# 原因4：总销售额分母萎缩（全店大盘下滑）
total_early_sales = df_early["总销售额"].sum()
total_late_sales = df_late["总销售额"].sum()
total_early_ad = df_early["广告花费"].sum()
total_late_ad = df_late["广告花费"].sum()
sales_change = total_late_sales / total_early_sales
ad_change = total_late_ad / total_early_ad

if sales_change < ad_change * 0.95:
    r4 = f"4. 全店总销售额增速低于广告投放增速：前半段总销售额{total_early_sales:,.0f}，后半段{total_late_sales:,.0f}；广告花费同步扩张，总销售额分母收缩，被动抬升TACOS数值。"
    reason_list.append(r4)

# 输出归因结论
if len(reason_list) == 0:
    st.success("当前周期TACOS无明显上涨，广告投放结构与转化保持稳定！")
else:
    for r in reason_list:
        st.warning(r)

# 综合总结文案（可直接复制进汇报）
summary_text = f"""
【TACOS上涨综合总结】
店铺：{selected_shop}，周期{start_dt}至{end_dt}，整体广告花费占比均值{avg_tacos:.2%}，后期相对前期上涨{(late_tacos - early_tacos):+.2%}。
核心驱动因素：
"""
for s in reason_list:
    summary_text += "\n" + s
summary_text += """
优化方向参考：
1. 优化SP关键词竞价，降低CPC，提升广告转化ROAS，压低单品ACOS；
2. 挖掘自然流量增长点，减少店铺对付费广告的销量依赖；
3. 控制高ACOS品牌广告SB/SBV预算，调整投放结构；
4. 通过促销、新品拉升全店总销售额，扩大TACOS分母。
"""
st.text_area("📝 可直接复制至报告的总结文本", summary_text, height=300)

# ===================== 四、分层拆解：品类&MSKU明细 =====================
st.markdown("## 🧩 四、分层数据拆解（定位拖后腿单品/品类）")
tab_cat, tab_msku = st.tabs(["品类汇总表", "MSKU单品明细"])

# 品类聚合
df_cat = df_filter.groupby("品类").agg({
    "广告花费": "sum", "销量": "sum", "广告销售额": "sum"
}).reset_index()
df_cat["TACOS"] = df_cat["广告花费"] / df_cat["销量"]
df_cat["ACOS"] = df_cat["广告花费"] / df_cat["广告销售额"]
df_cat["销售贡献占比"] = df_cat["销量"] / df_cat["销量"].sum()
df_cat = df_cat.sort_values("TACOS", ascending=False)

with tab_cat:
    st.dataframe(df_cat, use_container_width=True, height=350)
    st.caption("按品类汇总，TACOS越高代表该品类是拉高全店广告占比的核心板块")

# MSKU单品聚合
df_msku = df_filter.groupby(["品类", "MSKU", "品名"]).agg({
    "广告花费": "sum", "销量": "sum", "广告销售额": "sum", "点击": "sum"
}).reset_index()
df_msku["TACOS"] = df_msku["广告花费"] / df_msku["销量"]
df_msku["ACOS"] = df_msku["广告花费"] / df_msku["广告销售额"]
df_msku["CPC"] = df_msku["广告花费"] / df_msku["点击"]
df_msku["单品销售贡献"] = df_msku["销量"] / df_msku["销量"].sum()
df_msku = df_msku.sort_values("单品销售贡献", ascending=False)

with tab_msku:
    st.dataframe(df_msku, use_container_width=True, height=400)
    st.caption("按MSKU单品汇总，优先关注「销售贡献高+TACOS大幅偏高」的爆款单品")