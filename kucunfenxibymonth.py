import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板")

# ====================== 1. 数据加载 ======================
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

# ====================== 2. 时间标准化 ======================
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")
df_pur["采购日期"] = pd.to_datetime(df_pur["采购日期"], errors="coerce")

# ====================== 3. 数据合并 ======================
# 快照 + 销量
df_merge = df_snap.merge(
    df_sale[["MSKU", "时间", "销量"]],
    on=["MSKU", "时间"], how="left"
)
df_merge["销量"] = df_merge["销量"].fillna(0)

# 合并商品信息（是否年份品、类别、岁数）
df_prod_use = df_prod[["MSKU", "是否年份", "类别", "岁数"]].drop_duplicates(subset=["MSKU"])
df_merge = df_merge.merge(df_prod_use, on="MSKU", how="left")

# 合并采购数据（年前/年后采购）
pur_agg = df_pur.groupby("MSKU").agg(
    年前采购总量=("年前采购", "sum"),
    年后采购总量=("年后采购", "sum")
).reset_index()
df_merge = df_merge.merge(pur_agg, on="MSKU", how="left")
df_merge[["年前采购总量", "年后采购总量"]] = df_merge[["年前采购总量", "年后采购总量"]].fillna(0)

# ====================== 4. 核心库存指标计算 ======================
df_merge["海外库存"] = (
    df_merge["FBA库存"] + df_merge["FBA在途"] +
    df_merge["海外仓可用"] + df_merge["海外仓在途"]
).fillna(0)

df_merge["本地库存"] = (
    df_merge["本地可用"] + df_merge["待检"] + df_merge["待交付"]
).fillna(0)

df_merge["总库存"] = df_merge["海外库存"] + df_merge["本地库存"]

# 滞销金额
df_merge["海外滞销金额"] = df_merge["海外库存"] * (df_merge["采购成本"] + df_merge["头程费用"]).fillna(0)
df_merge["本地滞销金额"] = df_merge["本地库存"] * df_merge["采购成本"].fillna(0)
df_merge["总滞销金额"] = df_merge["海外滞销金额"] + df_merge["本地滞销金额"]

# 年前剩余库存
df_merge["年前剩余库存"] = np.maximum(0, df_merge["总库存"] - df_merge["年后采购总量"])

# 日均销量 & 周转天数
df_merge["日均销量"] = df_merge["销量"] / 30
df_merge["周转天数"] = np.where(
    df_merge["日均销量"] > 0,
    df_merge["总库存"] / df_merge["日均销量"],
    np.nan
)

# ====================== 【核心升级】顶部筛选：年份品计算口径 ======================
st.subheader("⚙️ 年份品滞销分析口径选择")
year_type_option = st.radio(
    "请选择年份品的计算方式：",
    options=["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"],
    horizontal=True
)

# 固定清仓目标时间（可根据年份自动调整）
TARGET_CLEAR_DATE = datetime(2026, 10, 31)

# ====================== 【核心升级】滞销风险判定函数 ======================
def get_stock_risk(row):
    is_year_product = str(row["是否年份"]).strip() == "是"
    turn_days = row["周转天数"]
    total_stock = row["总库存"]
    avg_sale = row["日均销量"]
    current_date = row["时间"]  # 快照时间

    # 1. 无销量数据 → 无数据
    if pd.isna(turn_days) or avg_sale <= 0 or total_stock <= 0:
        return "无日均/库存数据"

    # ==============================================
    # 情况1：非年份品 → 统一按周转天数判定
    # ==============================================
    if not is_year_product:
        if turn_days <= 100:
            return "健康"
        elif 100 < turn_days <= 150:
            return "轻度滞销风险"
        elif 150 < turn_days <= 180:
            return "中度滞销风险"
        else:
            return "严重滞销风险"

    # ==============================================
    # 情况2：年份品 → 根据选择的口径判定
    # ==============================================
    if is_year_product:
        # 口径A：清库存口径（预计售罄时间）
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

        # 口径B：库存周转天数口径（和非年份品规则一致）
        else:
            if turn_days <= 100:
                return "健康"
            elif 100 < turn_days <= 150:
                return "轻度滞销风险"
            elif 150 < turn_days <= 180:
                return "中度滞销风险"
            else:
                return "严重滞销风险"

# 应用风险判定
df_merge["滞销风险等级"] = df_merge.apply(get_stock_risk, axis=1)

# ====================== 5. 筛选器 ======================
st.subheader("🔍 数据筛选")
col1, col2 = st.columns(2)
with col1:
    time_list = sorted(df_merge["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
    sel_time = st.selectbox("选择统计时间", time_list)
with col2:
    shop_list = sorted(df_merge["店铺"].dropna().unique())
    sel_shop = st.multiselect("选择店铺", shop_list, default=shop_list)

# 筛选后数据
df_view = df_merge[
    (df_merge["时间"].dt.strftime("%Y-%m-%d") == sel_time) &
    (df_merge["店铺"].isin(sel_shop))
].copy()

# ====================== 6. 看板展示 ======================
st.subheader("📈 核心数据概览")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("总库存", f"{df_view['总库存'].sum():,.0f}")
kpi2.metric("总滞销金额", f"{df_view['总滞销金额'].sum():,.2f}")
kpi3.metric("年前剩余库存", f"{df_view['年前剩余库存'].sum():,.0f}")
kpi4.metric("当月总销量", f"{df_view['销量'].sum():,.0f}")

# 店铺维度
st.subheader("🏪 按店铺滞销统计")
shop_agg = df_view.groupby("店铺").agg({
    "总库存": "sum", "总滞销金额": "sum",
    "年前剩余库存": "sum", "销量": "sum"
}).reset_index()
st.dataframe(shop_agg, use_container_width=True)

# 类别 + 岁数
col_a, col_b = st.columns(2)
with col_a:
    st.subheader("📦 按类别滞销统计")
    cate_agg = df_view.groupby("类别")["总滞销金额"].sum().reset_index()
    st.dataframe(cate_agg, use_container_width=True)
with col_b:
    st.subheader("👶 按岁数滞销统计")
    age_agg = df_view.groupby("岁数")["总滞销金额"].sum().reset_index()
    st.dataframe(age_agg, use_container_width=True)

# 滞销风险等级（替换原来的原因）
st.subheader("⚠️ 滞销风险等级分布")
risk_agg = df_view["滞销风险等级"].value_counts().reset_index()
risk_agg.columns = ["风险等级", "商品数量"]
st.dataframe(risk_agg, use_container_width=True)

# 商品明细
st.subheader("📄 商品明细数据")
show_cols = [
    "店铺", "MSKU", "品名", "是否年份",
    "总库存", "总滞销金额", "周转天数", "滞销风险等级"
]
st.dataframe(df_view[show_cols], use_container_width=True)