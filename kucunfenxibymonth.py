import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板")


# ----------------------
# 1. 加载数据（严格按你给的sheet名）
# ----------------------
@st.cache_data
def load_data():
    file = "moon-date.xlsx"
    df_snap = pd.read_excel(file, sheet_name="补货建议-每月快照")
    df_prod = pd.read_excel(file, sheet_name="商品信息")
    df_sale = pd.read_excel(file, sheet_name="销量数据-每月")
    df_pur = pd.read_excel(file, sheet_name="采购数据-每月")

    # 只去空格，绝不改列名
    for df in [df_snap, df_prod, df_sale, df_pur]:
        df.columns = [c.strip() for c in df.columns]
    return df_snap, df_prod, df_sale, df_pur


df_snap, df_prod, df_sale, df_pur = load_data()

# ----------------------
# 2. 时间转换（安全模式，绝不报错）
# ----------------------
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")
df_pur["采购日期"] = pd.to_datetime(df_pur["采购日期"], errors="coerce")

# ----------------------
# 3. 合并：补货 + 销量（MSKU+时间，完全正确）
# ----------------------
df = df_snap.merge(df_sale, on=["MSKU", "时间"], how="left")
df["销量"] = df["销量"].fillna(0)

# ----------------------
# 4. 合并商品信息
# ----------------------
df = df.merge(df_prod[["MSKU", "店铺", "是否年份", "类别", "岁数"]], on="MSKU", how="left")

# ----------------------
# 5. 库存 & 滞销金额（严格按你的规则）
# ----------------------
df["海外库存"] = df["FBA库存"] + df["FBA在途"] + df["海外仓可用"] + df["海外仓在途"]
df["本地库存"] = df["本地可用"] + df["待检待上架量"] + df["待交付"]
df["总库存"] = df["海外库存"] + df["本地库存"]

df["海外滞销金额"] = df["海外库存"] * (df["采购成本"] + df["头程费用"])
df["本地滞销金额"] = df["本地库存"] * df["采购成本"]
df["总滞销金额"] = df["海外滞销金额"] + df["本地滞销金额"]

# ----------------------
# 6. 年前/年后采购（用MSKU关联，完全正确）
# ----------------------
pur_before = df_pur[df_pur["采购类型"] == "年前采购"].groupby("MSKU")["采购量"].sum().reset_index()
pur_after = df_pur[df_pur["采购类型"] == "年后采购"].groupby("MSKU")["采购量"].sum().reset_index()

pur_before.columns = ["MSKU", "年前采购总量"]
pur_after.columns = ["MSKU", "年后采购总量"]

df = df.merge(pur_before, on="MSKU", how="left")
df = df.merge(pur_after, on="MSKU", how="left")

df["年前采购总量"] = df["年前采购总量"].fillna(0)
df["年后采购总量"] = df["年后采购总量"].fillna(0)
df["年前剩余库存"] = np.maximum(0, df["总库存"] - df["年后采购总量"])

# ----------------------
# 7. 滞销归因
# ----------------------
df["周转天数"] = df["总库存"] / df["日均"].replace(0, np.nan)


def get_reason(row):
    avg = row["日均"]
    sale = row["销量"]
    turn = row["周转天数"]

    if pd.isna(turn) or avg <= 0:
        return "无日均数据"
    if sale < avg * 0.7 and turn > 90:
        return "销量下滑+备货过多"
    elif turn > 90:
        return "备货过多"
    elif sale < avg * 0.7:
        return "销量下滑"
    else:
        return "正常"


df["滞销原因"] = df.apply(get_reason, axis=1)

# ----------------------
# 8. 筛选
# ----------------------
st.divider()
time_list = sorted(df["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
sel_time = st.selectbox("选择时间", time_list)
df_view = df[df["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()

shop_list = df_view["店铺"].dropna().unique()
sel_shop = st.multiselect("选择店铺", shop_list, default=shop_list)
df_view = df_view[df_view["店铺"].isin(sel_shop)]

# ----------------------
# 9. 展示看板
# ----------------------
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
    st.markdown("### 按类别")
    st.dataframe(df_view.groupby("类别")["总滞销金额"].sum().reset_index())
with col2:
    st.markdown("### 按岁数")
    st.dataframe(df_view.groupby("岁数")["总滞销金额"].sum().reset_index())

st.divider()
st.markdown("## 滞销原因")
st.dataframe(df_view["滞销原因"].value_counts().reset_index())

st.divider()
st.markdown("## 商品明细")
show_cols = ["店铺", "MSKU", "品名", "时间", "是否年份", "类别", "岁数", "总库存", "总滞销金额", "销量", "年前剩余库存",
             "滞销原因"]
st.dataframe(df_view[show_cols], use_container_width=True)