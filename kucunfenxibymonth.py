import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板")

# ====================== 1. 加载数据 ======================
@st.cache_data
def load_data():
    file = "moon-date.xlsx"
    df_snap = pd.read_excel(file, sheet_name="补货建议-每月快照")
    df_prod = pd.read_excel(file, sheet_name="商品信息")
    df_sale = pd.read_excel(file, sheet_name="销量数据-每月")
    df_pur = pd.read_excel(file, sheet_name="采购数据-每月")

    for df in [df_snap, df_prod, df_sale, df_pur]:
        df.columns = [c.strip() for c in df.columns]
    return df_snap, df_prod, df_sale, df_pur

df_snap, df_prod, df_sale, df_pur = load_data()

# ====================== 2. 时间格式化 ======================
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")
df_pur["采购日期"] = pd.to_datetime(df_pur["采购日期"], errors="coerce")

# ====================== 3. 合并数据 ======================
df_merge = df_snap.merge(df_sale[["MSKU", "时间", "销量"]], on=["MSKU", "时间"], how="left")
df_merge["销量"] = df_merge["销量"].fillna(0)

df_prod_use = df_prod[["MSKU", "是否年份", "类别", "岁数"]].drop_duplicates(subset=["MSKU"])
df_merge = df_merge.merge(df_prod_use, on="MSKU", how="left")

# ====================== 4. 采购数据透视（正确适配你的表结构） ======================
pur_pivot = df_pur.pivot_table(
    index="MSKU",
    columns="采购类型",
    values="采购量",
    aggfunc="sum",
    fill_value=0
).reset_index()

pur_pivot.columns = [str(c).strip() for c in pur_pivot.columns]

# 安全兜底
for col in ["年前采购", "年后采购"]:
    if col not in pur_pivot.columns:
        pur_pivot[col] = 0

pur_pivot.rename(columns={"年前采购": "年前采购总量", "年后采购": "年后采购总量"}, inplace=True)
df_merge = df_merge.merge(pur_pivot[["MSKU", "年前采购总量", "年后采购总量"]], on="MSKU", how="left")
df_merge[["年前采购总量", "年后采购总量"]] = df_merge[["年前采购总量", "年后采购总量"]].fillna(0)

# ====================== 5. 计算库存（必须放在采购合并之后！） ======================
df_merge["海外库存"] = (
    df_merge["FBA库存"] + df_merge["FBA在途"] +
    df_merge["海外仓可用"] + df_merge["海外仓在途"]
).fillna(0)

df_merge["本地库存"] = (
    df_merge["本地可用"] + df_merge["待检"] + df_merge["待交付"]
).fillna(0)

df_merge["总库存"] = df_merge["海外库存"] + df_merge["本地库存"]

# 年前剩余库存
df_merge["年前剩余库存"] = np.maximum(0, df_merge["总库存"] - df_merge["年后采购总量"])

# 滞销金额
df_merge["海外滞销金额"] = df_merge["海外库存"] * (df_merge["采购成本"] + df_merge["头程费用"]).fillna(0)
df_merge["本地滞销金额"] = df_merge["本地库存"] * df_merge["采购成本"].fillna(0)
df_merge["总滞销金额"] = df_merge["海外滞销金额"] + df_merge["本地滞销金额"]

# 日均 & 周转天数
df_merge["日均销量"] = df_merge["销量"] / 30
df_merge["周转天数"] = np.where(
    df_merge["日均销量"] > 0,
    df_merge["总库存"] / df_merge["日均销量"],
    np.nan
)

# ====================== 6. 年份品口径选择 ======================
st.subheader("⚙️ 年份品滞销分析口径")
year_type_option = st.radio(
    "选择计算方式：",
    ["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"],
    horizontal=True
)
TARGET_CLEAR_DATE = datetime(2026, 10, 31)

# ====================== 7. 滞销风险判定 ======================
def get_stock_risk(row):
    is_year = str(row["是否年份"]).strip() == "是"
    turn = row["周转天数"]
    stock = row["总库存"]
    avg = row["日均销量"]
    dt = row["时间"]

    if pd.isna(turn) or avg <= 0 or stock <= 0:
        return "无数据"

    if not is_year:
        if turn <= 100: return "健康"
        elif 100 < turn <=150: return "轻度滞销风险"
        elif 150 < turn <=180: return "中度滞销风险"
        else: return "严重滞销风险"

    if year_type_option == "按照清库存口径（预计售罄时间）":
        days = stock / avg
        sell_dt = dt + timedelta(days=days)
        over = (sell_dt - TARGET_CLEAR_DATE).days
        if sell_dt <= TARGET_CLEAR_DATE: return "健康"
        elif 0 < over <=10: return "低滞销风险"
        elif 10 < over <=20: return "中滞销风险"
        else: return "高滞销风险"
    else:
        if turn <= 100: return "健康"
        elif 100 < turn <=150: return "轻度滞销风险"
        elif 150 < turn <=180: return "中度滞销风险"
        else: return "严重滞销风险"

df_merge["滞销风险等级"] = df_merge.apply(get_stock_risk, axis=1)

# ====================== 8. 筛选器 ======================
st.subheader("🔍 筛选")
col1, col2 = st.columns(2)
with col1:
    time_list = sorted(df_merge["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
    sel_time = st.selectbox("选择时间", time_list)
with col2:
    shop_list = sorted(df_merge["店铺"].dropna().unique())
    sel_shop = st.multiselect("选择店铺", shop_list, default=shop_list)

df_view = df_merge[
    (df_merge["时间"].dt.strftime("%Y-%m-%d") == sel_time) &
    (df_merge["店铺"].isin(sel_shop))
].copy()

# ====================== 9. 看板展示 ======================
st.subheader("📊 核心概览")
k1,k2,k3,k4 = st.columns(4)
k1.metric("总库存", f"{df_view['总库存'].sum():,.0f}")
k2.metric("总滞销金额", f"{df_view['总滞销金额'].sum():,.0f}")
k3.metric("年前剩余库存", f"{df_view['年前剩余库存'].sum():,.0f}")
k4.metric("当月销量", f"{df_view['销量'].sum():,.0f}")

st.subheader("🏪 店铺维度")
shop_df = df_view.groupby("店铺").agg({
    "总库存":"sum","总滞销金额":"sum","年前剩余库存":"sum","销量":"sum"
}).reset_index()
st.dataframe(shop_df, use_container_width=True)

c1,c2 = st.columns(2)
with c1:
    st.subheader("📦 类别滞销")
    st.dataframe(df_view.groupby("类别")["总滞销金额"].sum().reset_index(), use_container_width=True)
with c2:
    st.subheader("👶 岁数滞销")
    st.dataframe(df_view.groupby("岁数")["总滞销金额"].sum().reset_index(), use_container_width=True)

st.subheader("⚠️ 风险等级")
risk_df = df_view["滞销风险等级"].value_counts().reset_index()
risk_df.columns = ["风险等级","商品数"]
st.dataframe(risk_df, use_container_width=True)

st.subheader("📄 商品明细")
st.dataframe(df_view[[
    "店铺","MSKU","品名","是否年份","总库存","总滞销金额","周转天数","滞销风险等级"
]], use_container_width=True)