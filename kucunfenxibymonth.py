import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板")

# ----------------------
# 1. 加载数据
# ----------------------
@st.cache_data
def load_data():
    file = "moon-date.xlsx"
    df_snap = pd.read_excel(file, sheet_name="补货建议-每月快照")
    df_prod = pd.read_excel(file, sheet_name="商品信息")
    df_sale = pd.read_excel(file, sheet_name="销量数据-每月")
    df_pur = pd.read_excel(file, sheet_name="采购数据-每月")
    # 清理列名空格
    for df in [df_snap, df_prod, df_sale, df_pur]:
        df.columns = [c.strip() for c in df.columns]
    return df_snap, df_prod, df_sale, df_pur

df_snap, df_prod, df_sale, df_pur = load_data()

# ----------------------
# 2. 时间安全转换
# ----------------------
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")
df_pur["采购日期"] = pd.to_datetime(df_pur["采购日期"], errors="coerce")

# ----------------------
# 3. 合并：补货 + 销量
# ----------------------
df = df_snap.merge(df_sale, on=["MSKU", "时间"], how="left")
df["销量"] = df["销量"].fillna(0)

# ----------------------
# 4. 合并商品信息
# ----------------------
df_prod_use = df_prod[["MSKU", "是否年份", "类别", "岁数"]].drop_duplicates(subset=["MSKU"])
df = df.merge(df_prod_use, on="MSKU", how="left")

# ----------------------
# 5. 修复：按【采购类型】分组统计 年前/年后采购量
# ----------------------
# 透视：行MSKU，列采购类型，值采购量求和
pur_pivot = df_pur.pivot_table(
    index="MSKU",
    columns="采购类型",
    values="采购量",
    aggfunc="sum",
    fill_value=0
).reset_index()

# 统一列名，防止空格
pur_pivot.columns = [c.strip() for c in pur_pivot.columns]

# 确保列存在，不存在补0
if "年前采购" not in pur_pivot.columns:
    pur_pivot["年前采购"] = 0
if "年后采购" not in pur_pivot.columns:
    pur_pivot["年后采购"] = 0

pur_pivot.rename(columns={
    "年前采购": "年前采购总量",
    "年后采购": "年后采购总量"
}, inplace=True)

# 合并回主表
df = df.merge(pur_pivot[["MSKU","年前采购总量","年后采购总量"]], on="MSKU", how="left")
df[["年前采购总量","年后采购总量"]] = df[["年前采购总量","年后采购总量"]].fillna(0)

# 年前剩余库存
df["年前剩余库存"] = np.maximum(0, df["总库存"] - df["年后采购总量"])

# ----------------------
# 6. 库存 & 滞销金额
# ----------------------
df["海外库存"] = df["FBA库存"] + df["FBA在途"] + df["海外仓可用"] + df["海外仓在途"]
df["本地库存"] = df["本地可用"] + df["待检待上架量"] + df["待交付"]
df["总库存"] = df["海外库存"] + df["本地库存"]

df["海外滞销金额"] = df["海外库存"] * (df["采购成本"] + df["头程费用"])
df["本地滞销金额"] = df["本地库存"] * df["采购成本"]
df["总滞销金额"] = df["海外滞销金额"] + df["本地滞销金额"]

# 日均 & 周转天数
df["日均销量"] = df["销量"] / 30
df["周转天数"] = np.where(
    df["日均销量"] > 0,
    df["总库存"] / df["日均销量"],
    np.nan
)

# ----------------------
# 顶部：年份品口径选择器
# ----------------------
st.divider()
st.subheader("⚙️ 年份品滞销分析口径选择")
year_type_option = st.radio(
    "请选择年份品计算方式",
    options=["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"],
    horizontal=True
)

# 目标清仓日 2026-10-31
TARGET_CLEAR_DATE = datetime(2026, 10, 31)

# ----------------------
# 滞销风险判定逻辑（按你新规则）
# ----------------------
def get_stock_risk(row):
    is_year_product = str(row["是否年份"]).strip() == "是"
    turn_days = row["周转天数"]
    total_stock = row["总库存"]
    avg_sale = row["日均销量"]
    current_date = row["时间"]

    if pd.isna(turn_days) or avg_sale <= 0 or total_stock <= 0:
        return "无日均/库存数据"

    # 非年份品：固定周转分级
    if not is_year_product:
        if turn_days <= 100:
            return "健康"
        elif 100 < turn_days <= 150:
            return "轻度滞销风险"
        elif 150 < turn_days <= 180:
            return "中度滞销风险"
        else:
            return "严重滞销风险"

    # 年份品
    if year_type_option == "按照清库存口径（预计售罄时间）":
        need_days = total_stock / avg_sale
        sell_out_date = current_date + timedelta(days=need_days)
        over_days = (sell_out_date - TARGET_CLEAR_DATE).days

        if sell_out_date <= TARGET_CLEAR_DATE:
            return "健康"
        elif 0 < over_days <= 10:
            return "低滞销风险"
        elif 10 < over_days <= 20:
            return "中滞销风险"
        else:
            return "高滞销风险"
    else:
        # 年份品按周转天数口径，和非年份品一致
        if turn_days <= 100:
            return "健康"
        elif 100 < turn_days <= 150:
            return "轻度滞销风险"
        elif 150 < turn_days <= 180:
            return "中度滞销风险"
        else:
            return "严重滞销风险"

df["滞销风险等级"] = df.apply(get_stock_risk, axis=1)

# ----------------------
# 筛选
# ----------------------
st.divider()
time_list = sorted(df["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
sel_time = st.selectbox("选择时间", time_list)
df_view = df[df["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()

shop_list = df_view["店铺"].dropna().unique()
sel_shop = st.multiselect("选择店铺", shop_list, default=shop_list)
df_view = df_view[df_view["店铺"].isin(sel_shop)]

# ----------------------
# 看板展示
# ----------------------
st.divider()
st.markdown("## 🎯 核心概览")
c1, c2, c3, c4 = st.columns(4)
c1.metric("总库存", f"{df_view['总库存'].sum():,.0f}")
c2.metric("总滞销金额", f"{df_view['总滞销金额'].sum():,.0f} 元")
c3.metric("年前遗留库存", f"{df_view['年前剩余库存'].sum():,.0f}")
c4.metric("当月销量", f"{df_view['销量'].sum():,.0f}")

st.divider()
st.markdown("## 按店铺滞销")
shop_agg = df_view.groupby("店铺")[["总库存", "总滞销金额", "年前剩余库存", "销量"]].sum().reset_index()
st.dataframe(shop_agg, use_container_width=True)

st.divider()
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 按类别滞销金额")
    st.dataframe(df_view.groupby("类别")["总滞销金额"].sum().reset_index())
with col2:
    st.markdown("### 按岁数滞销金额")
    st.dataframe(df_view.groupby("岁数")["总滞销金额"].sum().reset_index())

st.divider()
st.markdown("## 滞销风险等级分布")
risk_agg = df_view["滞销风险等级"].value_counts().reset_index()
risk_agg.columns = ["风险等级","商品数"]
st.dataframe(risk_agg, use_container_width=True)

st.divider()
st.markdown("## 商品明细")
show_cols = [
    "店铺", "MSKU", "品名", "时间", "是否年份", "类别", "岁数",
    "总库存", "总滞销金额", "销量", "年前剩余库存", "周转天数", "滞销风险等级"
]
st.dataframe(df_view[show_cols], use_container_width=True)