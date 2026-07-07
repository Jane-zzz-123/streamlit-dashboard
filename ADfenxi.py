import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from io import BytesIO
import numpy as np

# -------------------------- 页面基础配置 --------------------------
st.set_page_config(
    page_title="广告分析看板",
    layout="wide",
    initial_sidebar_state="collapsed"
)
st.title("📊 广告分析看板")

# -------------------------- 缓存加载原始数据 --------------------------
@st.cache_data
def load_raw_data():
    url = "https://github.com/Jane-zzz-123/streamlit-dashboard/raw/main/ADdata_all.xlsx"
    resp = requests.get(url)
    df = pd.read_excel(BytesIO(resp.content), sheet_name="源数据")

    # 标准化时间
    df["时间"] = pd.to_datetime(df["时间"])
    df["年月"] = df["时间"].dt.to_period("M").astype(str)
    df["年月日期"] = pd.to_datetime(df["年月"] + "-01")

    # 数值清洗
    num_cols = [
        "展示", "点击", "广告花费", "SP广告费", "SB广告费", "SBV广告费",
        "广告销售额", "SP广告销售额", "SB广告销售额", "SBV广告销售额",
        "广告订单量", "SP广告订单量", "SB广告订单量", "SBV广告订单量",
        "销量", "销售额", "订单量"
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 上架时间转换
    df["开售时间"] = pd.to_datetime(df["开售时间"], errors="coerce")
    # 校验产品类型是否存在，不存在抛提示
    if "产品类型" not in df.columns:
        st.error("❌ 远程Excel未包含【产品类型】字段，请先上传更新后的文件到GitHub！")
    return df


df_raw = load_raw_data()

# ===================== 页面顶部筛选区：仅2个单选控件【店铺、单月年月】 =====================
st.markdown("### 🔍 数据筛选条件（仅单月数据）")
filter_shop_col, filter_month_col = st.columns([1, 2])

# 1、店铺单选下拉
with filter_shop_col:
    shop_list = sorted(df_raw["店铺"].unique())
    select_shop = st.selectbox("选择分析店铺", shop_list)

# 2、年月单选下拉，默认最新月份
with filter_month_col:
    month_list = sorted(df_raw["年月"].unique())
    latest_month = month_list[-1]
    select_month = st.selectbox("选择分析单月", month_list, index=month_list.index(latest_month))

st.divider()

# ===================== 新增：指标释义&计算公式折叠面板（放在筛选下方、当月卡片上方） =====================
with st.expander("📖 全部指标释义 & 计算公式（点击展开查看）", expanded=False):
    st.markdown("""
### 一、基础金额/订单指标
1. **当月总广告花费**
    - 含义：当月SP+SB+SBV全部广告扣费总和
    - 公式：广告花费 = SP广告费 + SB广告费 + SBV广告费
2. **当月广告销售额**
    - 含义：当月所有广告渠道点击成交的订单总金额（仅广告单营收）
    - 公式：广告销售额 = SP广告销售额 + SB广告销售额 + SBV广告销售额
3. **当月全店总销售额**
    - 含义：店铺当月所有订单（广告单+自然单）总成交金额
    - 公式：全店销售额 = 全部订单对应销售额总和
4. **当月广告订单总数**
    - 含义：当月通过广告点击成交的订单数量
    - 公式：广告订单数 = 所有广告渠道订单数量求和
5. **当月全店总订单**
    - 含义：店铺当月全部成交订单（广告+自然流量）
    - 公式：总订单 = 广告订单 + 自然流量订单

### 二、广告成本核心指标
6. **TACOS 广告花费占比**
    - 含义：广告花费占全店总销售额的比例，衡量整体广告投入力度
    - 公式：TACOS = 当月广告花费 ÷ 当月全店总销售额
7. **ACOS 广告销售成本**
    - 含义：广告花费占广告自身销售额的比例，广告投放内部转化成本
    - 公式：ACOS = 当月广告花费 ÷ 当月广告销售额
8. **ROAS 广告投产比**
    - 含义：每1美金广告花费带来多少广告销售额，反向ACOS
    - 公式：ROAS = 当月广告销售额 ÷ 当月广告花费
9. **ASoAS 广告销售依赖度**
    - 含义：广告成交销售额占店铺全店总销售额的比重，店铺流量依赖度
    - 公式：ASoAS = 当月广告销售额 ÷ 当月全店总销售额

### 三、流量效率指标
10. **CPC 单次点击成本**
    - 含义：广告平均单次点击扣费
    - 公式：CPC = 当月广告总花费 ÷ 当月广告总点击量
11. **CTR 点击率**
    - 含义：广告曝光后产生点击的比例，主图/标题吸引力
    - 公式：CTR = 当月广告点击量 ÷ 当月广告曝光（展示）量
12. **CVR 广告转化率**
    - 含义：广告点击后下单成交比例，落地页/价格/评价转化能力
    - 公式：CVR = 当月广告订单数 ÷ 当月广告点击量

### 补充说明
- 环比差值：当月指标 − 上月同期指标
- 环比百分比：(当月 − 上月) ÷ 上月绝对值，正数上涨（红色），负数下降（绿色）
- 新品判定：MSKU上架≤60天=新品；无开售时间/上架超60天=老品
""")
st.divider()

# -------------------------- 筛选当月数据集 --------------------------
df_filter_single_month = df_raw[
    (df_raw["店铺"] == select_shop) &
    (df_raw["年月"] == select_month)
    ].copy()

if df_filter_single_month.empty:
    st.warning(f"⚠️ {select_shop}店铺 {select_month} 无任何数据，请更换店铺或月份！")
    st.stop()

# -------------------------- 当月单月聚合 --------------------------
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

# -------------------------- 当月数值提取（新增广告销售额）
curr_ad_spend = df_month_single["广告花费"].iloc[0]
curr_sales = df_month_single["销售额"].iloc[0]
curr_ad_sales = df_month_single["广告销售额"].iloc[0] # 新增当月广告销售额
curr_ad_order = df_month_single["广告订单量"].iloc[0]
curr_all_order = df_month_single["订单量"].iloc[0]
curr_tacos = df_month_single["TACOS广告花费占比"].iloc[0]
curr_acos = df_month_single["ACOS"].iloc[0]
curr_roas = df_month_single["ROAS"].iloc[0]
curr_asoas = df_month_single["ASoAS广告销售依赖度"].iloc[0]
curr_cpc = df_month_single["CPC"].iloc[0]
curr_ctr = df_month_single["CTR"].iloc[0]
curr_cvr = df_month_single["CVR广告转化率"].iloc[0]

# -------------------------- 计算上月环比数据（补充广告销售额环比）
curr_period = pd.Period(select_month, freq="M")
last_period = curr_period - 1
last_month_str = str(last_period)
df_last_raw = df_raw[(df_raw["店铺"] == select_shop) & (df_raw["年月"] == last_month_str)]
has_last_month = not df_last_raw.empty

# 上月默认0 新增广告销售额变量
last_ad_spend = last_sales = last_ad_sales = last_ad_order = last_all_order = 0
last_tacos = last_acos = last_roas = last_asoas = last_cpc = last_ctr = last_cvr = 0
delta_ad_spend = delta_sales = delta_ad_sales = delta_ad_order = delta_all_order = 0
delta_tacos = delta_acos = delta_roas = delta_asoas = delta_cpc = delta_ctr = delta_cvr = 0
pct_ad_spend = pct_sales = pct_ad_sales = pct_ad_order = pct_all_order = 0
pct_tacos = pct_acos = pct_roas = pct_asoas = pct_cpc = pct_ctr = pct_cvr = 0

if has_last_month:
    df_last_agg = df_last_raw.groupby("年月").agg({
        "广告花费":"sum","销售额":"sum","广告订单量":"sum","订单量":"sum",
        "展示":"sum","点击":"sum","广告销售额":"sum"
    }).reset_index()
    last_ad_spend = df_last_agg["广告花费"].iloc[0]
    last_sales = df_last_agg["销售额"].iloc[0]
    last_ad_sales = df_last_agg["广告销售额"].iloc[0] # 上月广告销售额
    last_ad_order = df_last_agg["广告订单量"].iloc[0]
    last_all_order = df_last_agg["订单量"].iloc[0]
    last_imp = df_last_agg["展示"].iloc[0]
    last_click = df_last_agg["点击"].iloc[0]
    last_ad_sales_base = df_last_agg["广告销售额"].iloc[0]

    last_ctr = last_click / last_imp if last_imp !=0 else 0
    last_cpc = last_ad_spend / last_click if last_click !=0 else 0
    last_cvr = last_ad_order / last_click if last_click !=0 else 0
    last_acos = last_ad_spend / last_ad_sales_base if last_ad_sales_base !=0 else 0
    last_roas = last_ad_sales_base / last_ad_spend if last_ad_spend !=0 else 0
    last_tacos = last_ad_spend / last_sales if last_sales !=0 else 0
    last_asoas = last_ad_sales_base / last_sales if last_sales !=0 else 0

    # 广告销售额差值&环比
    delta_ad_spend = curr_ad_spend - last_ad_spend
    delta_sales = curr_sales - last_sales
    delta_ad_sales = curr_ad_sales - last_ad_sales
    delta_ad_order = curr_ad_order - last_ad_order
    delta_all_order = curr_all_order - last_all_order
    delta_tacos = curr_tacos - last_tacos
    delta_acos = curr_acos - last_acos
    delta_roas = curr_roas - last_roas
    delta_asoas = curr_asoas - last_asoas
    delta_cpc = curr_cpc - last_cpc
    delta_ctr = curr_ctr - last_ctr
    delta_cvr = curr_cvr - last_cvr

    pct_ad_spend = delta_ad_spend / last_ad_spend if last_ad_spend !=0 else 0
    pct_sales = delta_sales / last_sales if last_sales !=0 else 0
    pct_ad_sales = delta_ad_sales / last_ad_sales if last_ad_sales !=0 else 0
    pct_ad_order = delta_ad_order / last_ad_order if last_ad_order !=0 else 0
    pct_all_order = delta_all_order / last_all_order if last_all_order !=0 else 0
    pct_tacos = delta_tacos / last_tacos if last_tacos !=0 else 0
    pct_acos = delta_acos / last_acos if last_acos !=0 else 0
    pct_roas = delta_roas / last_roas if last_roas !=0 else 0
    pct_asoas = delta_asoas / last_asoas if last_asoas !=0 else 0
    pct_cpc = delta_cpc / last_cpc if last_cpc !=0 else 0
    pct_ctr = delta_ctr / last_ctr if last_ctr !=0 else 0
    pct_cvr = delta_cvr / last_cvr if last_cvr !=0 else 0

# ===================== 一、当月指标卡片（第一行新增广告销售额，5列布局） =====================
st.markdown(f"## 🎯 一、{select_month} 当月店铺整体概况（单月快照）")
if not has_last_month:
    st.info("当前为最早统计月份，无上月对比数据")

# 第一行：5列 广告花费、总销售额、广告销售额、广告订单、总订单
row1_col1, row1_col2, row1_col3, row1_col4, row1_col5 = st.columns(5)
with row1_col1:
    st.metric(label="当月总广告花费", value=f"${curr_ad_spend:,.2f}", delta=f"{delta_ad_spend:,.2f}")
    if has_last_month:
        st.caption(f"上月：${last_ad_spend:,.2f} | 环比：{pct_ad_spend:.1%}")
with row1_col2:
    st.metric(label="当月全店总销售额", value=f"${curr_sales:,.2f}", delta=f"{delta_sales:,.2f}")
    if has_last_month:
        st.caption(f"上月：${last_sales:,.2f} | 环比：{pct_sales:.1%}")
with row1_col3:
    st.metric(label="当月广告销售额", value=f"${curr_ad_sales:,.2f}", delta=f"{delta_ad_sales:,.2f}")
    if has_last_month:
        st.caption(f"上月：${last_ad_sales:,.2f} | 环比：{pct_ad_sales:.1%}")
with row1_col4:
    st.metric(label="当月广告订单总数", value=f"{curr_ad_order:,.0f}", delta=f"{delta_ad_order:,.0f}")
    if has_last_month:
        st.caption(f"上月：{last_ad_order:,.0f} | 环比：{pct_ad_order:.1%}")
with row1_col5:
    st.metric(label="当月全店总订单", value=f"{curr_all_order:,.0f}", delta=f"{delta_all_order:,.0f}")
    if has_last_month:
        st.caption(f"上月：{last_all_order:,.0f} | 环比：{pct_all_order:.1%}")

# 第二行4卡：TACOS、ACOS、ROAS、ASoAS（不变）
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

# 第三行3卡：CPC、CTR、CVR（不变）
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

# 当月文字说明同步补充广告销售额
st.info(f"""
【{select_month}单月概况说明】
分析店铺：{select_shop} | 分析月份：{select_month}
1. 当月广告投放总额 ${curr_ad_spend:,.2f}，广告成交销售额 ${curr_ad_sales:,.2f}，店铺全部总销售额 ${curr_sales:,.2f}，广告花费占营收比重TACOS {curr_tacos:.2%}
2. 当月广告自身转化成本ACOS {curr_acos:.2%}，每投入1美金广告带来 {curr_roas:.2f} 美金广告营收
3. 当月店铺 {curr_asoas:.2%} 的营收来自付费广告，剩余为自然免费流量订单
4. 当月单次点击成本CPC ${curr_cpc:.2f}，广告曝光点击率CTR {curr_ctr:.2%}，点击下单转化率 {curr_cvr:.2%}
""")
# -------------------------- 全店铺所有月份完整指标明细表（修改后） --------------------------
st.subheader(f"📋 {select_shop}店铺 全月份完整指标明细表")
# 取当前选中店铺全部月份数据
df_all_month_table = df_raw[df_raw["店铺"] == select_shop].groupby("年月").agg({
    "展示": "sum",
    "点击": "sum",
    "广告花费": "sum",
    "SP广告费": "sum",
    "SB广告费": "sum",
    "SBV广告费": "sum",
    "SP广告销售额": "sum",
    "SB广告销售额": "sum",
    "SBV广告销售额": "sum",
    "广告销售额": "sum",
    "广告订单量": "sum",
    "销售额": "sum",
    "订单量": "sum"
}).reset_index()

# 批量计算所有月份衍生指标
df_all_month_table["CTR"] = np.where(df_all_month_table["展示"] == 0, 0, df_all_month_table["点击"] / df_all_month_table["展示"])
df_all_month_table["CPC"] = np.where(df_all_month_table["点击"] == 0, 0, df_all_month_table["广告花费"] / df_all_month_table["点击"])
df_all_month_table["CVR广告转化率"] = np.where(df_all_month_table["点击"] == 0, 0, df_all_month_table["广告订单量"] / df_all_month_table["点击"])
df_all_month_table["ACOS"] = np.where(df_all_month_table["广告销售额"] == 0, 0, df_all_month_table["广告花费"] / df_all_month_table["广告销售额"])
df_all_month_table["ROAS"] = np.where(df_all_month_table["广告花费"] == 0, 0, df_all_month_table["广告销售额"] / df_all_month_table["广告花费"])
df_all_month_table["TACOS广告花费占比"] = np.where(df_all_month_table["销售额"] == 0, 0, df_all_month_table["广告花费"] / df_all_month_table["销售额"])
df_all_month_table["ASoAS广告销售依赖度"] = np.where(df_all_month_table["销售额"] == 0, 0, df_all_month_table["广告销售额"] / df_all_month_table["销售额"])
df_all_month_table["SP广告花费占比"] = np.where(df_all_month_table["广告花费"] == 0, 0, df_all_month_table["SP广告费"] / df_all_month_table["广告花费"])
df_all_month_table["SB广告花费占比"] = np.where(df_all_month_table["广告花费"] == 0, 0, df_all_month_table["SB广告费"] / df_all_month_table["广告花费"])
df_all_month_table["SBV广告花费占比"] = np.where(df_all_month_table["广告花费"] == 0, 0, df_all_month_table["SBV广告费"] / df_all_month_table["广告花费"])

# 固定展示列不变
show_month_cols = [
    "年月", "展示", "点击", "广告花费", "销售额", "广告销售额",
    "TACOS广告花费占比", "ACOS", "ROAS", "CPC", "CTR", "CVR广告转化率",
    "ASoAS广告销售依赖度", "SP广告花费占比", "SB广告花费占比", "SBV广告花费占比"
]
# 按年月倒序，最新月份排在最上方
df_all_month_table = df_all_month_table.sort_values("年月", ascending=False).reset_index(drop=True)
st.dataframe(df_all_month_table[show_month_cols], use_container_width=True, height=320)
st.caption("表格按月份倒序排列，顶部为最新月份，可横向滑动查看全部广告指标历史数据")

# ===================== 新增：TACOS走势与归因分析 =====================
st.markdown(f"## 📈 二、{select_shop}店铺 TACOS走势与上涨归因分析")

# 复用全月数据并按时间正序排列（画图用）
df_trend = df_all_month_table.sort_values("年月", ascending=True).reset_index(drop=True)
# 生成中文年月格式：2026年6月
df_trend["年月中文"] = df_trend["年月"].apply(lambda x: f"{x.split('-')[0]}年{int(x.split('-')[1])}月")

# 同一行两列布局
trend_col1, trend_col2 = st.columns([1.3, 1])

# 左图：销售额柱形 + 广告花费折线 组合图（双Y轴）
with trend_col1:
    fig_combo = go.Figure()
    # 柱形：全店总销售额
    fig_combo.add_trace(go.Bar(
        x=df_trend["年月中文"],
        y=df_trend["销售额"],
        name="全店总销售额",
        yaxis="y",
        marker_color="#4C78A8",
        opacity=0.7,
        hovertemplate="%{x}<br>全店销售额：$%{y:,.2f}<extra></extra>"
    ))
    # 折线：广告花费
    fig_combo.add_trace(go.Scatter(
        x=df_trend["年月中文"],
        y=df_trend["广告花费"],
        name="广告总花费",
        yaxis="y2",
        mode="lines+markers",
        line=dict(color="#E45756", width=3),
        marker=dict(size=8),
        hovertemplate="%{x}<br>广告花费：$%{y:,.2f}<extra></extra>"
    ))
    fig_combo.update_layout(
        title="销售额（柱形）vs 广告花费（折线）",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis=dict(title="全店总销售额 ($)", side="left"),
        yaxis2=dict(title="广告总花费 ($)", side="right", overlaying="y"),
        hovermode="x unified",
        height=420,
        margin=dict(l=10, r=10, t=50, b=10)
    )
    st.plotly_chart(fig_combo, use_container_width=True)

# 右图：TACOS 折线图
with trend_col2:
    fig_tacos = go.Figure()
    fig_tacos.add_trace(go.Scatter(
        x=df_trend["年月中文"],
        y=df_trend["TACOS广告花费占比"],
        name="TACOS",
        mode="lines+markers+text",
        line=dict(color="#F58518", width=3),
        marker=dict(size=9),
        text=[f"{v:.1%}" for v in df_trend["TACOS广告花费占比"]],
        textposition="top center",
        hovertemplate="%{x}<br>TACOS：%{y:.2%}<extra></extra>"
    ))
    fig_tacos.update_layout(
        title="TACOS 月度走势",
        yaxis=dict(title="TACOS（广告花费/总销售额）", tickformat=".1%"),
        height=420,
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode="x unified"
    )
    st.plotly_chart(fig_tacos, use_container_width=True)

# ---- 自动生成归因分析文本 ----
# 取最新月与上月对比
latest_idx = df_trend.index[-1]
curr_tacos_val = df_trend["TACOS广告花费占比"].iloc[latest_idx]
curr_spend_val = df_trend["广告花费"].iloc[latest_idx]
curr_sales_val = df_trend["销售额"].iloc[latest_idx]

if latest_idx >= 1:
    prev_tacos_val = df_trend["TACOS广告花费占比"].iloc[latest_idx - 1]
    prev_spend_val = df_trend["广告花费"].iloc[latest_idx - 1]
    prev_sales_val = df_trend["销售额"].iloc[latest_idx - 1]
    tacos_change = curr_tacos_val - prev_tacos_val
    spend_pct = (curr_spend_val - prev_spend_val) / prev_spend_val if prev_spend_val != 0 else 0
    sales_pct = (curr_sales_val - prev_sales_val) / prev_sales_val if prev_sales_val != 0 else 0

    # 判断归因方向
    if tacos_change > 0:
        direction = "上涨"
        direction_color = "🔴"
    elif tacos_change < 0:
        direction = "下降"
        direction_color = "🟢"
    else:
        direction = "持平"
        direction_color = "⚪"

    # 拆解原因
    reason_list = []
    if spend_pct > 0 and sales_pct <= 0:
        reason_list.append(f"广告花费环比**上升 {spend_pct:.1%}**，而全店销售额反而**下降 {sales_pct:.1%}**，一增一减共同推高TACOS")
    elif spend_pct > sales_pct and sales_pct > 0:
        reason_list.append(f"广告花费增速（{spend_pct:.1%}）**快于**销售额增速（{sales_pct:.1%}），投入扩张但营收未同步跟上")
    elif spend_pct >= 0 and sales_pct < 0:
        reason_list.append(f"销售额环比下滑 {sales_pct:.1%}，分母收缩导致TACOS被动抬升")
    elif spend_pct < 0 and sales_pct < 0 and abs(sales_pct) > abs(spend_pct):
        reason_list.append(f"广告花费虽下降 {abs(spend_pct):.1%}，但销售额下滑更快（{abs(sales_pct):.1%}），整体TACOS仍走高")
    else:
        reason_list.append("广告花费与销售额变动幅度接近，TACOS基本稳定")

    # 补充建议
    suggestions = []
    if tacos_change > 0.02:  # 上涨超2个百分点
        suggestions.append("建议排查广告投放效率：检查ACOS是否同步恶化，重点优化高花费低产出的SP广告活动")
        suggestions.append("关注自然流量与自然单占比：若ASoAS同步上升，说明店铺对广告依赖度在增加，需布局自然流量")
    elif tacos_change < -0.01:
        suggestions.append("TACOS改善明显，可评估是否有进一步加预算扩大规模的空间")
    suggestions.append("可结合SP/SB/SBV分渠道花费占比，定位是哪类广告拉动了整体花费上涨")

    analysis_text = f"""
### {direction_color} {select_month} TACOS {direction}归因分析

**核心数据对比（环比上月）：**
- TACOS：{prev_tacos_val:.2%} → {curr_tacos_val:.2%}，**{direction} {abs(tacos_change):.2%}**
- 广告花费：${prev_spend_val:,.2f} → ${curr_spend_val:,.2f}，环比 {spend_pct:+.1%}
- 全店销售额：${prev_sales_val:,.2f} → ${curr_sales_val:,.2f}，环比 {sales_pct:+.1%}

**主要原因判断：**
"""
    for i, r in enumerate(reason_list, 1):
        analysis_text += f"{i}. {r}\n"

    analysis_text += "\n**优化建议：**\n"
    for i, s in enumerate(suggestions, 1):
        analysis_text += f"{i}. {s}\n"

    st.markdown(analysis_text)
else:
    st.info("仅有单月数据，暂无法进行环比归因分析，请等待更多月份数据积累。")

st.divider()

# ===================== 新增：渠道拆分 SP/SB/SBV 深度拆解（修复字段缺失） =====================
st.markdown("## 📊 三、分广告渠道(SP/SB/SBV)TACOS&ACOS拆解分析")
# 复用按月汇总数据集，时间正序绘图
df_channel = df_all_month_table.sort_values("年月", ascending=True).reset_index(drop=True)
df_channel["年月中文"] = df_channel["年月"].apply(lambda x: f"{x.split('-')[0]}年{int(x.split('-')[1])}月")

# 双列布局：左=渠道花费堆叠柱状，右=分渠道TACOS折线
chan_col1, chan_col2 = st.columns([1.2, 1])

# 左图：SP/SB/SBV月度花费堆叠柱状图
# 左图：SP/SB/SBV月度花费堆叠柱状图（新增占比悬浮提示）
with chan_col1:
    # 先计算每月总花费，用于算占比
    df_channel["总广告花费"] = df_channel["SP广告费"] + df_channel["SB广告费"] + df_channel["SBV广告费"]
    df_channel["SP占比"] = (df_channel["SP广告费"] / df_channel["总广告花费"]).apply(lambda x: f"{x:.1%}")
    df_channel["SB占比"] = (df_channel["SB广告费"] / df_channel["总广告花费"]).apply(lambda x: f"{x:.1%}")
    df_channel["SBV占比"] = (df_channel["SBV广告费"] / df_channel["总广告花费"]).apply(lambda x: f"{x:.1%}")

    fig_spend_stack = go.Figure()
    fig_spend_stack.add_trace(go.Bar(
        x=df_channel["年月中文"],
        y=df_channel["SP广告费"],
        name="SP搜索广告",
        marker_color="#E45756",
        hovertemplate="%{x}<br>SP花费：$%{y:,.2f}<br>当月广告占比：%{customdata}<extra></extra>",
        customdata=df_channel["SP占比"]
    ))
    fig_spend_stack.add_trace(go.Bar(
        x=df_channel["年月中文"],
        y=df_channel["SB广告费"],
        name="SB品牌广告",
        marker_color="#4C78A8",
        hovertemplate="%{x}<br>SB花费：$%{y:,.2f}<br>当月广告占比：%{customdata}<extra></extra>",
        customdata=df_channel["SB占比"]
    ))
    fig_spend_stack.add_trace(go.Bar(
        x=df_channel["年月中文"],
        y=df_channel["SBV广告费"],
        name="SBV视频展示广告",
        marker_color="#59A14F",
        hovertemplate="%{x}<br>SBV花费：$%{y:,.2f}<br>当月广告占比：%{customdata}<extra></extra>",
        customdata=df_channel["SBV占比"]
    ))
    fig_spend_stack.update_layout(
        title="各渠道月度广告花费堆叠（hover查看渠道当月花费占比）",
        barmode="stack",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis_title="广告花费 ($)",
        height=420,
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode="x unified"
    )
    st.plotly_chart(fig_spend_stack, use_container_width=True)

# 计算指标：渠道TACOS、渠道ACOS
# 渠道TACOS = 渠道广告费 / 全店总销售额
df_channel["SP_TACOS"] = np.where(df_channel["销售额"] == 0, 0, df_channel["SP广告费"] / df_channel["销售额"])
df_channel["SB_TACOS"] = np.where(df_channel["销售额"] == 0, 0, df_channel["SB广告费"] / df_channel["销售额"])
df_channel["SBV_TACOS"] = np.where(df_channel["销售额"] == 0, 0, df_channel["SBV广告费"] / df_channel["销售额"])

# 渠道ACOS = 渠道广告费 / 渠道自身广告销售额
df_channel["SP_ACOS"] = np.where(df_channel["SP广告销售额"] == 0, 0, df_channel["SP广告费"] / df_channel["SP广告销售额"])
df_channel["SB_ACOS"] = np.where(df_channel["SB广告销售额"] == 0, 0, df_channel["SB广告费"] / df_channel["SB广告销售额"])
df_channel["SBV_ACOS"] = np.where(df_channel["SBV广告销售额"] == 0, 0, df_channel["SBV广告费"] / df_channel["SBV广告销售额"])

# 右图：分渠道独立TACOS折线对比
with chan_col2:
    fig_channel_tacos = go.Figure()
    # 整体总TACOS基准虚线
    fig_channel_tacos.add_trace(go.Scatter(
        x=df_channel["年月中文"],
        y=df_channel["TACOS广告花费占比"],
        name="整体总TACOS",
        mode="lines+markers",
        line=dict(color="#F58518", width=4, dash="dash"),
        marker=dict(size=7),
        hovertemplate="%{x}<br>整体TACOS：%{y:.2%}<extra></extra>"
    ))
    fig_channel_tacos.add_trace(go.Scatter(
        x=df_channel["年月中文"],
        y=df_channel["SP_TACOS"],
        name="SP渠道TACOS",
        mode="lines+markers",
        line=dict(color="#E45756", width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br>SP-TACOS：%{y:.2%}<extra></extra>"
    ))
    fig_channel_tacos.add_trace(go.Scatter(
        x=df_channel["年月中文"],
        y=df_channel["SB_TACOS"],
        name="SB渠道TACOS",
        mode="lines+markers",
        line=dict(color="#4C78A8", width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br>SB-TACOS：%{y:.2%}<extra></extra>"
    ))
    fig_channel_tacos.add_trace(go.Scatter(
        x=df_channel["年月中文"],
        y=df_channel["SBV_TACOS"],
        name="SBV渠道TACOS",
        mode="lines+markers",
        line=dict(color="#59A14F", width=2),
        marker=dict(size=6),
        hovertemplate="%{x}<br>SBV-TACOS：%{y:.2%}<extra></extra>"
    ))
    fig_channel_tacos.update_layout(
        title="分渠道TACOS vs 店铺整体TACOS",
        yaxis_title="TACOS占比",
        yaxis_tickformat=".1%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode="x unified"
    )
    st.plotly_chart(fig_channel_tacos, use_container_width=True)

# ===================== 新增：四、广告底层投放效率深度拆解 =====================
st.markdown("## 📉 四、广告底层投放效率（CPC/CTR/CVR/整体ACOS）根源分析")
df_eff = df_all_month_table.sort_values("年月", ascending=True).reset_index(drop=True)
df_eff["年月中文"] = df_eff["年月"].apply(lambda x: f"{x.split('-')[0]}年{int(x.split('-')[1])}月")

# 预先计算四大核心效率指标（兜底除0防报错）
# CTR 点击率 = 点击 / 展示
df_eff["CTR"] = np.where(df_eff["展示"] == 0, 0, df_eff["点击"] / df_eff["展示"])
# CPC 单次点击成本 = 广告花费 / 点击
df_eff["CPC"] = np.where(df_eff["点击"] == 0, 0, df_eff["广告花费"] / df_eff["点击"])
# CVR 广告转化率 = 广告订单量 / 点击
df_eff["CVR"] = np.where(df_eff["点击"] == 0, 0, df_eff["广告订单量"] / df_eff["点击"])
# ACOS 整体广告投产 = 广告花费 / 广告销售额
df_eff["整体ACOS"] = np.where(df_eff["广告销售额"] == 0, 0, df_eff["广告花费"] / df_eff["广告销售额"])

# 布局：上下两组图表，第一行双列，第二行单列全宽
eff_row1_col1, eff_row1_col2 = st.columns([1, 1])

# 左图1：CPC & CTR 双折线（流量成本+点击精准度）
with eff_row1_col1:
    fig_cost_click = go.Figure()
    # CPC 折线
    fig_cost_click.add_trace(go.Scatter(
        x=df_eff["年月中文"],
        y=df_eff["CPC"],
        name="CPC单次点击成本($)",
        mode="lines+markers",
        line=dict(color="#E45756", width=3),
        hovertemplate="%{x}<br>CPC：$%{y:.2f}<extra></extra>"
    ))
    # CTR 次坐标轴
    fig_cost_click.add_trace(go.Scatter(
        x=df_eff["年月中文"],
        y=df_eff["CTR"],
        name="CTR点击率",
        mode="lines+markers",
        line=dict(color="#4C78A8", width=3),
        yaxis="y2",
        hovertemplate="%{x}<br>CTR：%{y:.2%}<extra></extra>"
    ))
    fig_cost_click.update_layout(
        title="CPC单次点击成本 & CTR点击率走势",
        yaxis=dict(title="CPC ($)", side="left"),
        yaxis2=dict(title="CTR 占比", side="right", overlaying="y", tickformat=".1%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=400,
        margin=dict(l=10, r=10, t=45, b=10),
        hovermode="x unified"
    )
    st.plotly_chart(fig_cost_click, use_container_width=True)

# 右图2：CVR转化率 & 整体ACOS双折线（转化&广告投产）
with eff_row1_col2:
    fig_conv_acos = go.Figure()
    # CVR 转化率
    fig_conv_acos.add_trace(go.Scatter(
        x=df_eff["年月中文"],
        y=df_eff["CVR"],
        name="CVR广告转化率",
        mode="lines+markers",
        line=dict(color="#59A14F", width=3),
        hovertemplate="%{x}<br>CVR：%{y:.2%}<extra></extra>"
    ))
    # ACOS 次坐标轴
    fig_conv_acos.add_trace(go.Scatter(
        x=df_eff["年月中文"],
        y=df_eff["整体ACOS"],
        name="店铺整体ACOS",
        mode="lines+markers",
        line=dict(color="#F58518", width=3),
        yaxis="y2",
        hovertemplate="%{x}<br>ACOS：%{y:.2%}<extra></extra>"
    ))
    fig_conv_acos.update_layout(
        title="CVR广告转化率 & 整体ACOS走势",
        yaxis=dict(title="CVR 转化率", side="left", tickformat=".1%"),
        yaxis2=dict(title="ACOS广告成本占比", side="right", overlaying="y", tickformat=".1%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=400,
        margin=dict(l=10, r=10, t=45, b=10),
        hovermode="x unified"
    )
    st.plotly_chart(fig_conv_acos, use_container_width=True)

# 下方：自动底层效率归因文本
st.subheader("🔍 底层投放效率自动归因分析")
if len(df_eff) >= 2:
    curr_eff = df_eff.iloc[-1]
    prev_eff = df_eff.iloc[-2]
    curr_month = curr_eff["年月中文"]

    # 环比差值计算
    cpc_diff = curr_eff["CPC"] - prev_eff["CPC"]
    ctr_diff = curr_eff["CTR"] - prev_eff["CTR"]
    cvr_diff = curr_eff["CVR"] - prev_eff["CVR"]
    acos_diff = curr_eff["整体ACOS"] - prev_eff["整体ACOS"]

    # 三列并排展示核心指标环比
    eff_col1, eff_col2, eff_col3 = st.columns(3)
    with eff_col1:
        st.markdown("#### 流量成本指标")
        st.markdown(f"""
- CPC环比变动：${cpc_diff:+.2f}
- 当月CPC：${curr_eff["CPC"]:.2f}
- CTR环比变动：{ctr_diff:+.2%}
- 当月CTR：{curr_eff["CTR"]:.2%}
""")
    with eff_col2:
        st.markdown("#### 转化效率指标")
        st.markdown(f"""
- CVR环比变动：{cvr_diff:+.2%}
- 当月CVR：{curr_eff["CVR"]:.2%}
""")
    with eff_col3:
        st.markdown("#### 广告投产指标")
        st.markdown(f"""
- ACOS环比变动：{acos_diff:+.2%}
- 当月整体ACOS：{curr_eff["整体ACOS"]:.2%}
""")
else:
    st.info("效率环比对比至少需要2个月历史数据，当前数据不足无法拆解底层变动。")

st.divider()


# ===================== 五、新品老品分层投放拆解（修复TACOS归零+hover明细） =====================
# ===================== 五、新品老品分层投放拆解（适配Excel完整产品类型标签） =====================
st.markdown("## 🧩 五、新品老品分层投放拆解（定位拖垮TACOS的商品层级）")

# 1、筛选当前店铺全量明细，按年月+产品类型聚合分层数据
df_shop_raw = df_raw[df_raw["店铺"] == select_shop].copy()
df_type_group = df_shop_raw.groupby(["年月", "产品类型"]).agg({
    "SP广告费":"sum",
    "SB广告费":"sum",
    "SBV广告费":"sum",
    "广告花费":"sum",
    "广告销售额":"sum",
    "销售额":"sum",
    "广告订单量":"sum",
    "订单量":"sum",
    "展示":"sum",
    "点击":"sum"
}).reset_index()

# 生成中文年月
df_type_group["年月中文"] = df_type_group["年月"].apply(lambda x: f"{x.split('-')[0]}年{int(x.split('-')[1])}月")

# ========== 修复1：重写分层TACOS/ACOS计算，销售额为0不强制归零 ==========
df_type_group["分层TACOS"] = df_type_group.apply(
    lambda row: row["广告花费"] / row["销售额"] if row["销售额"] != 0 else None, axis=1
)
df_type_group["分层ACOS"] = df_type_group.apply(
    lambda row: row["广告花费"] / row["广告销售额"] if row["广告销售额"] != 0 else None, axis=1
)

# 排序绘图数据
df_type_sort = df_type_group.sort_values("年月", ascending=True)
st.subheader("📈 各分层月度花费 & 分层TACOS全周期走势")
t1, t2 = st.columns([1.2, 1])

# 左图：三层商品广告花费堆叠柱状
with t1:
    fig_type_spend = go.Figure()
    # 【重点修改】key和Excel完整标签一字不差
    color_map = {
        "新品 (开售天数小于等于60)": "#ff7f0e",
        "老品 (开售天数大于60天)": "#2ca02c",
        "新品未出单": "#d62728"
    }
    type_list = [
        "新品 (开售天数小于等于60)",
        "老品 (开售天数大于60天)",
        "新品未出单"
    ]
    for tp in type_list:
        sub = df_type_sort[df_type_sort["产品类型"] == tp]
        fig_type_spend.add_trace(go.Bar(
            x=sub["年月中文"],
            y=sub["广告花费"],
            name=tp,
            marker_color=color_map[tp],
            customdata=sub[["销售额","广告销售额","分层TACOS"]].values,
            hovertemplate="%{x}<br>分层：%{name}<br>广告花费:$%{y:,.2f}<br>总销售额:$%{customdata[0]:,.2f}<br>广告销售额:$%{customdata[1]:,.2f}<br>分层TACOS:%{customdata[2]:.2%}<extra></extra>"
        ))
    fig_type_spend.update_layout(
        title="各商品分层月度广告花费堆叠",
        barmode="stack",
        height=420,
        yaxis_title="广告花费($)",
        legend=dict(orientation="h", y=1.02, x=0),
        hovermode="x unified"
    )
    st.plotly_chart(fig_type_spend, use_container_width=True)

# 右图：三层商品分层TACOS折线对比
with t2:
    fig_type_tacos = go.Figure()
    for tp in type_list:
        sub = df_type_sort[df_type_sort["产品类型"] == tp]
        fig_type_tacos.add_trace(go.Scatter(
            x=sub["年月中文"],
            y=sub["分层TACOS"],
            name=f"{tp} TACOS",
            mode="lines+markers",
            line=dict(color=color_map[tp], width=2),
            marker=dict(size=6),
            customdata=sub[["广告花费","分层ACOS"]].values,
            hovertemplate="%{x}<br>分层：%{name}<br>TACOS:%{y:.2%}<br>广告花费:$%{customdata[0]:,.2f}<br>分层ACOS:%{customdata[1]:.2%}<extra></extra>"
        ))
    fig_type_tacos.update_layout(
        title="各商品分层TACOS走势对比",
        height=420,
        yaxis_title="分层TACOS",
        yaxis_tickformat=".1%",
        legend=dict(orientation="h", y=1.02, x=0),
        hovermode="x unified"
    )
    st.plotly_chart(fig_type_tacos, use_container_width=True)

st.divider()

# ---------------------- 单品维度：当月广告花费TOP20明细表 ----------------------
st.subheader(f"📋 {select_month} 单品广告花费TOP20明细表（定位低效ASIN）")
df_single_item = df_shop_raw[df_shop_raw["年月"] == select_month].copy()
# 单品指标计算
df_single_item["单品ACOS"] = df_single_item.apply(lambda r: r["广告花费"]/r["广告销售额"] if r["广告销售额"] !=0 else None, axis=1)
df_single_item["单品TACOS"] = df_single_item.apply(lambda r: r["广告花费"]/r["销售额"] if r["销售额"] !=0 else None, axis=1)

df_top_item = df_single_item.sort_values("广告花费", ascending=False).head(20)
item_show_cols = [
    "MSKU","品名","产品类型", "开售时间", "广告花费", "广告销售额", "销售额",
    "单品ACOS", "单品TACOS", "展示", "点击", "广告订单量"
]
st.dataframe(df_top_item[item_show_cols], use_container_width=True, height=350)
st.caption("按广告花费从高到低排序；重点关注「新品未出单」高花费SKU，无成交纯消耗广告费，优先削减预算")

st.divider()