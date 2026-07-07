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

    # 全局计算上架间隔、生成新品老品标签
    df["上架间隔天数"] = (df["年月日期"] - df["开售时间"]).dt.days

    def tag_product_type(days):
        if pd.isna(days) or days <= 0:
            return "未知上架时间"
        elif days <= 60:
            return "新品(上架≤60天)"
        else:
            return "老品(上架>60天)"

    df["产品类型"] = df["上架间隔天数"].apply(tag_product_type)
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
