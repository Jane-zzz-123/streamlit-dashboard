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
df_table_show = df_all_month_table[show_month_cols].copy()

# ---------------------- 格式化配置 ----------------------
# 所有需要百分比展示的列
percent_cols = [
    "TACOS广告花费占比", "ACOS", "CTR", "CVR广告转化率",
    "ASoAS广告销售依赖度", "SP广告花费占比", "SB广告花费占比", "SBV广告花费占比"
]
# 金额、单价、ROAS 保留两位小数
float_2_cols = ["广告花费", "销售额", "广告销售额", "CPC", "ROAS"]
# 展示、点击 整数，无小数
int_cols = ["展示", "点击"]

# 表格样式渲染
styled_table = df_table_show.style\
    .format(formatter="{:.2%}", subset=percent_cols)\
    .format(formatter="{:.2f}", subset=float_2_cols)\
    .format(formatter="{:.0f}", subset=int_cols)

st.dataframe(styled_table, use_container_width=True, height=320)
st.caption("表格按月份倒序排列，顶部为最新月份；比率类字段以百分比展示，金额/单价保留两位小数，展示点击为整数，可横向滑动查看全部广告指标历史数据")

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

    # 1. 先计算每个月份店铺整体总额，用来算占比
    df_month_total_all = df_type_group.groupby("年月").agg(
        当月总广告花费=("广告花费", "sum"),
        当月总销售额=("销售额", "sum")
    ).reset_index()
    # 关联回分层表
    df_type_join = df_type_group.merge(df_month_total_all, on="年月", how="left")
    # 计算分层占比
    df_type_join["花费占比"] = df_type_join["广告花费"] / df_type_join["当月总广告花费"]
    df_type_join["销售额占比"] = df_type_join["销售额"] / df_type_join["当月总销售额"]

    df_type_sort = df_type_join.sort_values("年月", ascending=True)

    for tp in type_list:
        sub = df_type_sort[df_type_sort["产品类型"] == tp]
        fig_type_spend.add_trace(go.Bar(
            x=sub["年月中文"],
            y=sub["广告花费"],
            name=tp,
            marker_color=color_map[tp],
            customdata=sub[
                ["销售额","广告销售额","分层TACOS",
                 "花费占比","销售额占比","当月总广告花费","当月总销售额"]
            ].values,
            hovertemplate="""%{x}<br>分层：%{name}
广告花费:$%{y:,.2f}（占当月店铺总广告花费 %{customdata[3]:.2%}）
总销售额:$%{customdata[0]:,.2f}（占当月店铺总销售额 %{customdata[4]:.2%}）
广告销售额:$%{customdata[1]:,.2f}
分层TACOS:%{customdata[2]:.2%}<extra></extra>"""
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

# ---------------------- 单品维度：当月全部单品明细表（TACOS高于店铺均值标红 + 金额2位小数+比率百分比格式化） ----------------------
# ---------------------- 单品维度：当月全部单品明细表（TACOS高于店铺均值标红 + 新增CTR/CPC/CVR） ----------------------
st.subheader(f"📋 {select_month} 全单品广告花费明细表（单品TACOS高于店铺整体TACOS标红）")
# 筛选当前月份单品明细
df_single_item = df_shop_raw[df_shop_raw["年月"] == select_month].copy()

# 计算店铺当月整体TACOS（对比基准）
df_month_total = df_shop_raw[df_shop_raw["年月"] == select_month].agg({
    "广告花费":"sum",
    "销售额":"sum"
})
shop_total_tacos = df_month_total["广告花费"] / df_month_total["销售额"] if df_month_total["销售额"] != 0 else 0

# 计算单品核心指标
df_single_item["单品ACOS"] = df_single_item.apply(
    lambda r: r["广告花费"]/r["广告销售额"] if r["广告销售额"] !=0 else None, axis=1
)
df_single_item["单品TACOS"] = df_single_item.apply(
    lambda r: r["广告花费"]/r["销售额"] if r["销售额"] !=0 else None, axis=1
)
# ========== 新增：CTR点击率、CPC单次点击成本、CVR广告转化率 ==========
df_single_item["CTR"] = df_single_item.apply(
    lambda r: r["点击"]/r["展示"] if r["展示"] !=0 else None, axis=1
)
df_single_item["CPC"] = df_single_item.apply(
    lambda r: r["广告花费"]/r["点击"] if r["点击"] !=0 else None, axis=1
)
df_single_item["CVR"] = df_single_item.apply(
    lambda r: r["广告订单量"]/r["点击"] if r["点击"] !=0 else None, axis=1
)

# 按广告花费倒序（全部数据）
df_all_item = df_single_item.sort_values("广告花费", ascending=False)

# 展示字段（新增CTR/CPC/CVR，按流量→成本→转化→投产逻辑排序）
item_show_cols = [
    "MSKU","品名","产品类型", "开售时间",
    "展示", "点击", "CTR", "CPC", "CVR",
    "广告花费", "广告销售额", "销售额",
    "单品ACOS", "单品TACOS", "广告订单量"
]
df_table = df_all_item[item_show_cols].copy()

# 条件标红函数：单品TACOS > 店铺整体TACOS 文字红色
def highlight_high_tacos(val):
    if pd.isna(val):
        return ""
    if val > shop_total_tacos:
        color = "red"
    else:
        color = "black"
    return f"color: {color}"

# 表格格式化：
# 1. 百分比列：CTR、CVR、ACOS、TACOS
pct_cols = ["CTR", "CVR", "单品ACOS", "单品TACOS"]
# 2. 金额列：CPC、广告花费、广告销售额、销售额（保留2位小数）
money_cols = ["CPC", "广告花费", "广告销售额", "销售额"]
# 3. 整数列：展示、点击、广告订单量
int_cols = ["展示", "点击", "广告订单量"]

styled_df = df_table.style\
    .map(highlight_high_tacos, subset=["单品TACOS"])\
    .format(formatter="{:.2%}", subset=pct_cols)\
    .format(formatter="{:.2f}", subset=money_cols)\
    .format(formatter="{:.0f}", subset=int_cols)

st.dataframe(styled_df, use_container_width=True, height=400)

st.caption(f"本月店铺整体TACOS：{shop_total_tacos:.2%}；红色=单品TACOS高于店铺平均水平；CTR/CVR为百分比，CPC/花费/销售额保留两位小数")

# ===================== 新增：分层TACOS超标数量统计分析 =====================
st.subheader("📊 三类商品单品TACOS超标数量对比分析")

# 筛选有效TACOS数据（排除空值无销售额商品）
df_valid = df_all_item.dropna(subset=["单品TACOS"])

# 初始化统计字典
stat_result = {}
type_name_list = [
    "新品 (开售天数小于等于60)",
    "老品 (开售天数大于60天)",
    "新品未出单"
]

for tag in type_name_list:
    df_type = df_valid[df_valid["产品类型"] == tag]
    total_cnt = len(df_type)
    over_cnt = len(df_type[df_type["单品TACOS"] > shop_total_tacos])
    over_rate = over_cnt / total_cnt if total_cnt > 0 else 0
    stat_result[tag] = {
        "总单品数": total_cnt,
        "TACOS超标单品数": over_cnt,
        "超标占比": over_rate
    }

# 三列展示统计数字
col_a, col_b, col_c = st.columns(3)
col_list = [col_a, col_b, col_c]
for idx, tag in enumerate(type_name_list):
    data = stat_result[tag]
    with col_list[idx]:
        st.markdown(f"**{tag}**")
        st.metric("总SKU数量", value=data["总单品数"])
        st.metric("TACOS超标SKU", value=data["TACOS超标单品数"])
        st.caption(f"超标占比：{data['超标占比']:.2%}")

# 自动生成综合分析文案
st.markdown("### 分层投放成本综合解读")
text_lines = []
text_lines.append(f"本月店铺整体基准TACOS为：**{shop_total_tacos:.2%}**，各分层单品投放超标情况如下：")

for tag in type_name_list:
    d = stat_result[tag]
    if d["总单品数"] == 0:
        line = f"- {tag}：本月无投放SKU"
    else:
        line = f"- {tag}：共{d['总单品数']}个SKU，其中{d['TACOS超标单品数']}个单品TACOS高于店铺均值，超标占比{d['超标占比']:.2%}"
    text_lines.append(line)

# 风险总结
max_over_tag = max(stat_result.items(), key=lambda x: x[1]["超标占比"])
max_tag, max_data = max_over_tag
text_lines.append(f"""
#### 核心风险提示
本月**{max_tag}**分层商品超标占比最高，达到{max_data["超标占比"]:.2%}，是拉高店铺整体TACOS的主要商品来源，建议优先针对该分层内高花费、高TACOS单品削减广告预算，优化关键词与Listing转化。
""")

st.markdown("\n".join(text_lines))
st.divider()

# ===================== 八、二八销售额结构分析（全局TACOS15%管控+修复apply长度报错） =====================
st.markdown("## 📈 八、二八销售额结构分析（全SKU分层+店铺全局目标TACOS15%预算测算）")
# 基础参数
target_tacos = 0.15
shop_total_tacos = df_month_single["TACOS广告花费占比"].iloc[0]

# 过滤有效有销售额SKU
df_8020_raw = df_all_item.dropna(subset=["销售额"]).copy()
df_8020_raw = df_8020_raw[df_8020_raw["销售额"] > 0]

if df_8020_raw.empty:
    st.warning("本月所有SKU均无销售额，无法进行二八结构分析")
else:
    # 1、二八分层标记
    df_8020_sort = df_8020_raw.sort_values("销售额", ascending=False).reset_index(drop=True)
    df_8020_sort["累计销售额"] = df_8020_sort["销售额"].cumsum()
    total_month_sales = df_8020_sort["销售额"].sum()
    df_8020_sort["累计销售额占比"] = df_8020_sort["累计销售额"] / total_month_sales


    def mark_sku_level(row):
        return "核心SKU(贡献前80%营收)" if row["累计销售额占比"] <= 0.8 else "长尾SKU(剩余20%营收)"


    df_8020_sort["SKU层级"] = df_8020_sort.apply(mark_sku_level, axis=1)


    # 2、商品自动标签
    def get_flow_tag(row):
        sales = row["销售额"]
        ad_sales = row["广告销售额"]
        ad_spend = row["广告花费"]
        prod_type = row["产品类型"]
        if "新品" in prod_type:
            return "新品推广款（广告预算刚性，不压降）"
        if ad_sales > sales and sales > 0:
            return "数据异常：广告营收>总销售额（退单/统计错位）"
        if ad_spend > 0 and ad_sales == 0:
            return "纯自然出单：广告无转化，预算浪费"
        if sales > 0 and (ad_sales / sales) >= 0.95:
            return "重度广告依赖：砍广告销量大幅下滑"
        return "正常老品，参与全局预算压降分配"


    df_8020_sort["商品流量标签"] = df_8020_sort.apply(get_flow_tag, axis=1)

    # ========== 全局店铺预算测算核心逻辑 ==========
    # 拆分新品、老品数据集
    df_new = df_8020_sort[df_8020_sort["商品流量标签"].str.contains("新品")]
    df_old = df_8020_sort[~df_8020_sort["商品流量标签"].str.contains("新品")]

    sum_new_ad_spend = df_new["广告花费"].sum()
    sum_old_ad_spend = df_old["广告花费"].sum()
    total_ad_spend = sum_new_ad_spend + sum_old_ad_spend

    # 全店广告总预算上限（目标TACOS15%）
    total_max_ad_allow = total_month_sales * target_tacos
    # 扣除新品刚性花费后，老品可投放总上限
    old_max_total_allow = total_max_ad_allow - sum_new_ad_spend

    # 老品销售额总和（用于按销售额权重分摊预算）
    sum_old_sales = df_old["销售额"].sum() if len(df_old) > 0 else 0

    # 3、初始化4个压降空列
    df_8020_sort["单品压降_销售额不变"] = None
    df_8020_sort["单品压降_销售额跌5%"] = None
    df_8020_sort["单品压降_销售额跌10%"] = None
    df_8020_sort["全局分摊压降额"] = None

    # 循环逐行计算，彻底规避expand长度报错
    for idx, row in df_8020_sort.iterrows():
        S = row["销售额"]
        AdSpend = row["广告花费"]
        tag = row["商品流量标签"]
        # 新品全部置空，不参与压降
        if "新品" in tag:
            continue
        # 场景1：单品独立达标15%
        target_single = S * target_tacos
        reduce_single_same = AdSpend - target_single if AdSpend > target_single else 0
        reduce_single_s95 = AdSpend - (S * 0.95 * target_tacos) if AdSpend > (S * 0.95 * target_tacos) else 0
        reduce_single_s90 = AdSpend - (S * 0.90 * target_tacos) if AdSpend > (S * 0.90 * target_tacos) else 0

        # 场景2：全局分摊压降
        if sum_old_sales <= 0 or old_max_total_allow <= 0:
            reduce_global = None
        else:
            weight = S / sum_old_sales
            single_global_max = old_max_total_allow * weight
            reduce_global = AdSpend - single_global_max if AdSpend > single_global_max else 0

        # 赋值回df
        df_8020_sort.at[idx, "单品压降_销售额不变"] = round(reduce_single_same, 2)
        df_8020_sort.at[idx, "单品压降_销售额跌5%"] = round(reduce_single_s95, 2)
        df_8020_sort.at[idx, "单品压降_销售额跌10%"] = round(reduce_single_s90, 2)
        df_8020_sort.at[idx, "全局分摊压降额"] = round(reduce_global, 2)

    # 统计二八图表数据
    df_head_80 = df_8020_sort[df_8020_sort["累计销售额占比"] <= 0.8]
    df_tail_20 = df_8020_sort[df_8020_sort["累计销售额占比"] > 0.8]
    total_sku_count = len(df_8020_sort)
    head_sku_count = len(df_head_80)
    head_sku_pct = head_sku_count / total_sku_count if total_sku_count > 0 else 0

    # 核心SKU聚合
    head_total_sales = df_head_80["销售额"].sum()
    head_total_ad_spend = df_head_80["广告花费"].sum()

    # ========== 修复新增：补充长尾销售额求和 ==========
    tail_total_sales = df_tail_20["销售额"].sum()
    tail_total_ad_spend = df_tail_20["广告花费"].sum()

    # 分层TACOS计算
    head_tacos = head_total_ad_spend / head_total_sales if head_total_sales > 0 else 0
    tail_tacos = tail_total_ad_spend / tail_total_sales if tail_total_sales > 0 else 0

    # 老品整体可削减总额（全局分摊口径）
    total_old_cut_global = df_8020_sort["全局分摊压降额"].dropna().sum()

    # ---------------------- 1、全局预算指标卡片 ----------------------
    st.subheader("📊 店铺全局TACOS管控核心数据（目标15%）")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    with kpi1:
        st.metric("全店总销售额", f"${total_month_sales:,.2f}")
        st.caption(f"目标总广告上限：${total_max_ad_allow:,.2f}")
    with kpi2:
        st.metric("当前总广告花费", f"${total_ad_spend:,.2f}")
        st.caption(f"店铺当前TACOS：{shop_total_tacos:.2%}")
    with kpi3:
        st.metric("新品刚性广告费", f"${sum_new_ad_spend:,.2f}")
        st.caption("新品不允许压降")
    with kpi4:
        st.metric("老品允许总预算", f"${old_max_total_allow:,.2f}")
        st.caption("总额-新品预算后剩余额度")
    with kpi5:
        st.metric("老品当前广告费", f"${sum_old_ad_spend:,.2f}")
        st.caption("老品实际投放总额")
    with kpi6:
        st.metric("老品全局可削减总额", f"${total_old_cut_global:,.2f}")
        st.caption("按店铺15%目标分摊后可释放预算")

    # 全局预算预警提示
    if old_max_total_allow < 0:
        st.error(f"""
        ⚠️ 严重预警：新品广告花费 ${sum_new_ad_spend:,.2f} 已经超过全店15%TACOS允许全部广告预算 ${total_max_ad_allow:,.2f}
        即使关停所有老品广告，店铺整体TACOS依旧高于15%；短期无解，两种方案：
        1. 降低新品广告投放力度，逐步压缩新品花费；
        2. 等待新品销售额提升，拉高总销售额分母，稀释TACOS。
        """)
    else:
        st.success(f"✅ 新品预算未透支全店广告额度，老品合计投放上限${old_max_total_allow:,.2f}，可通过削减老品广告将店铺整体TACOS控制至15%")

    # ---------------------- 2、二八趋势图表 ----------------------
    chart_80_left, chart_80_right = st.columns([1.2, 1])
    with chart_80_left:
        fig_cum_sales = go.Figure()
        fig_cum_sales.add_trace(go.Scatter(
            x=list(range(1, len(df_8020_sort)+1)),
            y=df_8020_sort["累计销售额占比"],
            mode="lines+markers",
            line=dict(color="#1f77b4", width=3),
            name="销售额累计占比",
            hovertemplate="SKU排名：%{x}<br>累计占比：%{y:.2%}<br>层级：%{customdata[0]}<br>标签：%{customdata[1]}<extra></extra>",
            customdata=df_8020_sort[["SKU层级","商品流量标签"]].values
        ))
        fig_cum_sales.add_hline(y=0.8, line_dash="dash", line_color="red", annotation_text="80%营收分界线")
        fig_cum_sales.update_layout(title="SKU销售额累计占比曲线", xaxis_title="SKU排名", yaxis_tickformat=".1%", height=400)
        st.plotly_chart(fig_cum_sales, use_container_width=True)
    with chart_80_right:
        fig_head_tail_spend = go.Figure()
        fig_head_tail_spend.add_trace(go.Bar(
            x=["核心SKU","长尾SKU"],
            y=[head_total_ad_spend, tail_total_ad_spend],
            marker_color=["#2ca02c", "#d62728"]
        ))
        fig_head_tail_spend.update_layout(title="核心/长尾广告花费对比", yaxis_title="广告花费($)", height=400)
        st.plotly_chart(fig_head_tail_spend, use_container_width=True)

    # ---------------------- 3、全SKU明细表格 ----------------------
    st.subheader(f"🏆 全量出单SKU明细（单品TACOS高于店铺基准标红）")
    full_show_cols = [
        "MSKU","品名","产品类型","SKU层级","商品流量标签",
        "展示","点击","CTR","CPC","CVR",
        "广告花费","广告销售额","销售额","单品ACOS","单品TACOS",
        "单品压降_销售额不变","单品压降_销售额跌5%","单品压降_销售额跌10%","全局分摊压降额"
    ]
    full_table = df_8020_sort[full_show_cols].copy()

    # TACOS单元格标红
    def color_tacos_series(s):
        return [
            "background-color: #ffcccc; color: #c41e3a; font-weight:bold"
            if val > shop_total_tacos else "" for val in s
        ]

    # 格式化
    pct_cols = ["CTR","CVR","单品ACOS","单品TACOS"]
    money_cols = ["CPC","广告花费","广告销售额","销售额","单品压降_销售额不变","单品压降_销售额跌5%","单品压降_销售额跌10%","全局分摊压降额"]
    int_cols = ["展示","点击"]
    full_styled = full_table.style\
        .format(formatter="{:.2%}", subset=pct_cols, na_rep="-")\
        .format(formatter="{:.2f}", subset=money_cols, na_rep="-")\
        .format(formatter="{:.0f}", subset=int_cols, na_rep="-")\
        .apply(color_tacos_series, subset=["单品TACOS"])
    st.dataframe(full_styled, use_container_width=True, height=480)
    st.caption("压降列说明：单品压降=单品独立做到15%；全局分摊压降=扣除新品刚性预算后，店铺整体达标15%需要削减金额，新品统一显示'-'")

    # ---------------------- 4、综合诊断解读 ----------------------
    st.subheader("🔍 全局TACOS管控投放策略解读")
    analysis = []
    # 二八判定
    if head_sku_pct <= 0.2:
        analysis.append(f"✅ 二八健康：仅{head_sku_pct:.1%}SKU贡献80%营收，爆款集中")
    else:
        analysis.append(f"⚠️ 营收分散：需要{head_sku_pct:.1%}SKU才能覆盖80%销售额，缺少头部爆款")
    analysis.append(f"- 店铺目标TACOS：15%；当前TACOS：{shop_total_tacos:.2%}")
    analysis.append(f"- 新品广告费${sum_new_ad_spend:,.2f}为刚性支出，不参与压降，直接占用15%总预算额度")

    if old_max_total_allow < 0:
        analysis.append("""
### 核心问题：新品投放透支全部广告预算
1. 现状：新品广告花费已经超过全店允许广告总额，关停所有老品广告也无法把TACOS压到15%；
2. 短期方案：小幅缩减新品竞价/预算，延缓新品扩张节奏；
3. 中长期方案：持续运营新品提升自然单、提高新品总销售额，放大分母稀释TACOS。
""")
    else:
        analysis.append(f"""
### 优化执行方案（可落地）
1. 老品整体广告投放总额必须控制在 ${old_max_total_allow:,.2f} 以内，才能保证店铺整体TACOS=15%；
2. 表格【全局分摊压降额】为优先级调整依据，按从大到小顺序削减SKU广告预算；
3. 三类压降参考：
   - 单品压降（销量不变）：保守调整，单品自身做到15%；
   - 全局分摊压降：贴合店铺整体目标，优先按此金额削减；
4. 分层调整优先级：
   ① 纯自然出单无广告转化SKU，直接关停广告；
   ② 长尾高TACOS标红老品，大幅削减预算；
   ③ 重度广告依赖爆款小幅下调，同步布局自然流量；
   ④ TACOS低于15%优质老品可保留甚至适度加预算承接释放流量。
""")
    analysis.append("### 新品特殊说明")
    analysis.append("新品推广期允许TACOS高于15%，作为短期投放成本；待开售满60天、稳定出单后，再纳入全局压降管控。")
    st.markdown("\n".join(analysis))

st.divider()

