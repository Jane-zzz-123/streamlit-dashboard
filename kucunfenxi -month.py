import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板（运营主管版）")
st.subheader("按店铺 / 品类 / 岁数 / 年份品 / 年前年后采购 深度归因")


# ----------------------
# 1. 加载数据
# ----------------------
@st.cache_data
def load_data():
    file = "moon-date.xlsx"

    # 4个sheet全部加载
    df_snapshot = pd.read_excel(file, sheet_name="补货建议-每月快照")
    df_product = pd.read_excel(file, sheet_name="商品信息")
    df_sales = pd.read_excel(file, sheet_name="销量数据-每月")
    df_purchase = pd.read_excel(file, sheet_name="采购数据-每月")

    # 统一列名（避免空格问题）
    df_snapshot.columns = df_snapshot.columns.str.strip()
    df_product.columns = df_product.columns.str.strip()
    df_sales.columns = df_sales.columns.str.strip()
    df_purchase.columns = df_purchase.columns.str.strip()

    return df_snapshot, df_product, df_sales, df_purchase


df_snapshot, df_product, df_sales, df_purchase = load_data()

# ----------------------
# 2. 数据预处理（完全按你的业务逻辑）
# ----------------------

# 月份标准化
df_snapshot["统计月份"] = pd.to_datetime(df_snapshot["统计月份"], errors="coerce").dt.to_period("M")

# 合并商品信息（品名匹配）
df_snapshot = df_snapshot.merge(
    df_product[["品名", "MSKU", "是否年份", "类别", "岁数"]],
    on="品名", how="left"
)

# ----------------------
# 3. 计算库存 & 滞销金额（你定义的规则 100% 对齐）
# ----------------------

# 1) 海外库存
df_snapshot["海外库存"] = (
        df_snapshot["FBA库存"]
        + df_snapshot["FBA在途"]
        + df_snapshot["海外仓可用"]
        + df_snapshot["海外仓在途"]
)

# 2) 本地库存
df_snapshot["本地库存"] = (
        df_snapshot["本地可用"]
        + df_snapshot["待检待上架量"]
        + df_snapshot["待交付"]
)

# 3) 总库存
df_snapshot["总库存"] = df_snapshot["海外库存"] + df_snapshot["本地库存"]

# 4) 海外滞销金额
df_snapshot["海外滞销金额"] = df_snapshot["海外库存"] * (df_snapshot["采购成本"] + df_snapshot["头程费用"])

# 5) 本地滞销金额
df_snapshot["本地滞销金额"] = df_snapshot["本地库存"] * df_snapshot["采购成本"]

# 6) 总滞销金额
df_snapshot["总滞销金额"] = df_snapshot["海外滞销金额"] + df_snapshot["本地滞销金额"]

# ----------------------
# 4. 月度销量合并
# ----------------------
df_sales["统计月份"] = pd.to_datetime(df_sales["时间"], errors="coerce").dt.to_period("M")
df_sales_agg = df_sales.groupby(["MSKU", "统计月份"])["销量"].sum().reset_index()
df_sales_agg.rename(columns={"销量": "当月销量"}, inplace=True)

df_final = df_snapshot.merge(
    df_sales_agg,
    left_on=["MSKU", "统计月份"],
    right_on=["MSKU", "统计月份"],
    how="left"
)

# ----------------------
# 5. 年前/年后采购拆解
# ----------------------
df_purchase["采购月份"] = pd.to_datetime(df_purchase["采购日期"], errors="coerce").dt.to_period("M")
df_purchase_agg = df_purchase.groupby(["SKU", "采购类型"])["采购量"].sum().reset_index()

df_purchase_before = df_purchase_agg[df_purchase_agg["采购类型"] == "年前采购"].copy()
df_purchase_before.rename(columns={"采购量": "年前累计采购"}, inplace=True)

df_purchase_after = df_purchase_agg[df_purchase_agg["采购类型"] == "年后采购"].copy()
df_purchase_after.rename(columns={"采购量": "年后累计采购"}, inplace=True)

# 合并采购
df_final = df_final.merge(
    df_purchase_before[["SKU", "年前累计采购"]],
    left_on="MSKU", right_on="SKU", how="left"
)
df_final = df_final.merge(
    df_purchase_after[["SKU", "年后累计采购"]],
    left_on="MSKU", right_on="SKU", how="left"
)

# 年前剩余库存
df_final["年前剩余库存"] = np.maximum(0, df_final["总库存"] - df_final["年后累计采购"].fillna(0))

# ----------------------
# 6. 滞销归因（核心：备货多 / 销量下滑）
# ----------------------
df_final["周转天数"] = df_final["总库存"] / df_final["日均"].replace(0, np.nan)
df_final["销量环比标签"] = "正常"
df_final.loc[df_final["当月销量"] < df_final["日均"] * 0.7, "销量环比标签"] = "销量下滑"
df_final.loc[df_final["周转天数"] > 90, "库存标签"] = "备货过多"
df_final["滞销原因"] = "正常"
df_final.loc[(df_final["销量环比标签"] == "销量下滑") & (df_final["库存标签"] == "备货过多"), "滞销原因"] = "销量下滑+备货过多"
df_final.loc[(df_final["销量环比标签"] == "正常") & (df_final["库存标签"] == "备货过多"), "滞销原因"] = "备货过多"
df_final.loc[(df_final["销量环比标签"] == "销量下滑") & (df_final["库存标签"] != "备货过多"), "滞销原因"] = "销量下滑"

# ----------------------
# 7. 看板页面开始
# ----------------------
st.divider()

# 月份筛选
month_list = df_final["统计月份"].astype(str).unique()
select_month = st.selectbox("选择月份", month_list)
df = df_final[df_final["统计月份"].astype(str) == select_month].copy()

# 店铺筛选
shop_list = df["店铺"].dropna().unique()
select_shop = st.multiselect("选择店铺", shop_list, default=shop_list)
df = df[df["店铺"].isin(select_shop)]

# ----------------------
# 8. 核心看板（老板开会一页看完）
# ----------------------
st.markdown("## 🎯 核心概览")
c1, c2, c3, c4 = st.columns(4)
c1.metric("总库存数量", f"{df['总库存'].sum():,.0f}")
c2.metric("总滞销金额", f"{df['总滞销金额'].sum():,.0f} 元")
c3.metric("年前遗留库存", f"{df['年前剩余库存'].sum():,.0f}")
c4.metric("当月销量", f"{df['当月销量'].sum():,.0f}")

st.divider()

# ----------------------
# 9. 店铺维度看板
# ----------------------
st.markdown("## 🛍️ 按店铺滞销分析")
shop_agg = df.groupby("店铺").agg({
    "总库存": "sum",
    "总滞销金额": "sum",
    "年前剩余库存": "sum",
    "当月销量": "sum"
}).reset_index()
st.dataframe(shop_agg, use_container_width=True)

st.divider()

# ----------------------
# 10. 品类/岁数/年份品看板
# ----------------------
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📦 按品类")
    cate_agg = df.groupby("类别").agg({
        "总库存": "sum",
        "总滞销金额": "sum"
    }).reset_index()
    st.dataframe(cate_agg, use_container_width=True)

with col2:
    st.markdown("### 👶 按岁数")
    age_agg = df.groupby("岁数").agg({
        "总库存": "sum",
        "总滞销金额": "sum"
    }).reset_index()
    st.dataframe(age_agg, use_container_width=True)

st.divider()

# ----------------------
# 11. 滞销归因（核心！！！）
# ----------------------
st.markdown("## 🔍 滞销原因归因（备货多 / 销量下滑）")
reason_agg = df["滞销原因"].value_counts().reset_index()
reason_agg.columns = ["滞销原因", "SKU数量"]
st.dataframe(reason_agg, use_container_width=True)

st.divider()

# ----------------------
# 12. 年前/年后库存拆解
# ----------------------
st.markdown("## 📆 年前备货 VS 年后补货 库存结构")
c1, c2 = st.columns(2)
with c1:
    st.metric("年前遗留库存总量", f"{df['年前剩余库存'].sum():,.0f}")
with c2:
    st.metric("年后采购库存", f"{df['年后累计采购'].sum():,.0f}")

before_shop = df.groupby("店铺")["年前剩余库存"].sum().reset_index()
st.dataframe(before_shop, use_container_width=True)

st.divider()

# ----------------------
# 13. 原始数据下载
# ----------------------
st.markdown("## 📥 导出月度复盘明细")
st.dataframe(df[[
    "店铺", "MSKU", "品名", "类别", "岁数", "是否年份",
    "总库存", "总滞销金额", "当月销量", "周转天数",
    "年前剩余库存", "滞销原因"
]], use_container_width=True)