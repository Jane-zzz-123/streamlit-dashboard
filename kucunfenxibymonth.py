import streamlit as st
import pandas as pd
import numpy as np

# 页面基础配置
st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板（主管版）")


# ----------------------
# 1. 加载数据（完全匹配你的Excel Sheet）
# ----------------------
@st.cache_data
def load_data():
    file = "moon-date.xlsx"
    # 加载4个Sheet
    df_snap = pd.read_excel(file, sheet_name="补货建议-每月快照")
    df_prod = pd.read_excel(file, sheet_name="商品信息")
    df_sale = pd.read_excel(file, sheet_name="销量数据-每月")
    df_pur = pd.read_excel(file, sheet_name="采购数据-每月")

    # 仅清除列名空格，不修改任何原字段名
    for df in [df_snap, df_prod, df_sale, df_pur]:
        df.columns = df.columns.str.strip()
    return df_snap, df_prod, df_sale, df_pur


df_snap, df_prod, df_sale, df_pur = load_data()

# ----------------------
# 2. 时间字段统一处理（全程只用【时间】列）
# ----------------------
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")
df_pur["采购日期"] = pd.to_datetime(df_pur["采购日期"], errors="coerce")

# 合并商品信息到库存快照表
df = df_snap.merge(
    df_prod[["店铺", "MSKU", "品名", "是否年份", "类别", "岁数"]],
    on="品名",
    how="left"
)

# ----------------------
# 3. 库存 & 滞销金额计算（严格按你的规则）
# ----------------------
# 海外库存：FBA库存+FBA在途+海外仓可用+海外仓在途
df["海外库存"] = df["FBA库存"] + df["FBA在途"] + df["海外仓可用"] + df["海外仓在途"]
# 本地库存：本地可用+待检待上架量+待交付
df["本地库存"] = df["本地可用"] + df["待检待上架量"] + df["待交付"]
# 总库存
df["总库存"] = df["海外库存"] + df["本地库存"]

# 滞销金额规则 100% 按你要求
df["海外滞销金额"] = df["海外库存"] * (df["采购成本"] + df["头程费用"])
df["本地滞销金额"] = df["本地库存"] * df["采购成本"]
df["总滞销金额"] = df["海外滞销金额"] + df["本地滞销金额"]

# ----------------------
# 4. 月度销量合并
# ----------------------
df_sale_agg = df_sale.groupby(["MSKU", "时间"])["销量"].sum().reset_index()
df = df.merge(df_sale_agg, on=["MSKU", "时间"], how="left")

# ----------------------
# 5. 年前/年后采购拆解
# ----------------------
# 分别汇总年前/年后采购总量
pur_before = df_pur[df_pur["采购类型"] == "年前采购"].groupby("SKU")["采购量"].sum().reset_index()
pur_after = df_pur[df_pur["采购类型"] == "年后采购"].groupby("SKU")["采购量"].sum().reset_index()
pur_before.columns = ["MSKU", "年前采购总量"]
pur_after.columns = ["MSKU", "年后采购总量"]

# 合并到主表
df = df.merge(pur_before, on="MSKU", how="left")
df = df.merge(pur_after, on="MSKU", how="left")
df["年前采购总量"] = df["年前采购总量"].fillna(0)
df["年后采购总量"] = df["年后采购总量"].fillna(0)

# 年前剩余库存 = 总库存 - 年后采购（不能为负数）
df["年前剩余库存"] = np.maximum(0, df["总库存"] - df["年后采购总量"])

# ----------------------
# 6. 滞销归因逻辑
# ----------------------
# 计算周转天数
df["周转天数"] = df["总库存"] / df["日均"].replace(0, np.nan)


# 定义滞销原因函数
def get_reason(row):
    avg_sale = row["日均"]
    real_sale = row["销量"] if pd.notna(row["销量"]) else 0
    turnover = row["周转天数"]
    if real_sale < avg_sale * 0.7 and turnover > 90:
        return "销量下滑+备货过多"
    elif turnover > 90:
        return "备货过多"
    elif real_sale < avg_sale * 0.7:
        return "销量下滑"
    else:
        return "正常"


df["滞销原因"] = df.apply(get_reason, axis=1)

# ----------------------
# 7. 看板筛选
# ----------------------
st.divider()
# 时间筛选（原生时间列，无统计月份）
time_list = sorted(df["时间"].dt.strftime("%Y-%m-%d").unique())
sel_time = st.selectbox("选择统计时间", time_list)
df_view = df[df["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()

# 店铺筛选
shop_list = df_view["店铺"].dropna().unique()
sel_shop = st.multiselect("选择店铺", shop_list, default=shop_list)
df_view = df_view[df_view["店铺"].isin(sel_shop)]

# ----------------------
# 8. 看板核心内容
# ----------------------
st.markdown("## 🎯 核心数据概览")
c1, c2, c3, c4 = st.columns(4)
c1.metric("总库存数量", f"{df_view['总库存'].sum():,.0f}")
c2.metric("总滞销金额", f"{df_view['总滞销金额'].sum():,.0f} 元")
c3.metric("年前遗留库存", f"{df_view['年前剩余库存'].sum():,.0f}")
c4.metric("当月销量", f"{df_view['销量'].sum():,.0f}")

st.divider()
# 店铺维度汇总
st.markdown("## 🛍️ 按店铺汇总")
shop_agg = df_view.groupby("店铺").agg({
    "总库存": "sum",
    "总滞销金额": "sum",
    "年前剩余库存": "sum",
    "销量": "sum"
}).reset_index()
st.dataframe(shop_agg, use_container_width=True)

st.divider()
# 品类 & 岁数分析
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 📦 按品类滞销金额")
    cate_agg = df_view.groupby("类别")["总滞销金额"].sum().reset_index()
    st.dataframe(cate_agg, use_container_width=True)
with col2:
    st.markdown("### 👶 按岁数滞销金额")
    age_agg = df_view.groupby("岁数")["总滞销金额"].sum().reset_index()
    st.dataframe(age_agg, use_container_width=True)

st.divider()
# 滞销原因分布
st.markdown("## 🔍 滞销原因分布")
reason_cnt = df_view["滞销原因"].value_counts().reset_index()
reason_cnt.columns = ["滞销原因", "SKU数量"]
st.dataframe(reason_cnt, use_container_width=True)

st.divider()
# 商品明细导出
st.markdown("## 📥 商品明细数据")
show_cols = [
    "店铺", "MSKU", "品名", "时间", "是否年份", "类别", "岁数",
    "海外库存", "本地库存", "总库存",
    "海外滞销金额", "本地滞销金额", "总滞销金额",
    "日均", "销量", "周转天数", "年前剩余库存", "滞销原因"
]
st.dataframe(df_view[show_cols], use_container_width=True)