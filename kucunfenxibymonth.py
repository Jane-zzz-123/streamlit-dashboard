import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="月度库存滞销复盘看板", layout="wide")
st.title("📊 月度库存滞销复盘看板")

# ---------------------- 1. 加载数据 ----------------------
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

# ---------------------- 2. 时间转换 ----------------------
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")
df_pur["采购日期"] = pd.to_datetime(df_pur["采购日期"], errors="coerce")

# ---------------------- 3. 数据合并 ----------------------
# 快照 + 销量 只关联不参与计算
df = df_snap.merge(df_sale[["MSKU","时间","销量"]], on=["MSKU","时间"], how="left")
df["销量"] = df["销量"].fillna(0)

# 商品信息
df_prod_use = df_prod[["MSKU","是否年份","类别","岁数"]].drop_duplicates(subset=["MSKU"])
df = df.merge(df_prod_use, on="MSKU", how="left")

# 采购类型透视
pur_pivot = df_pur.pivot_table(
    index="MSKU", columns="采购类型", values="采购量", aggfunc="sum", fill_value=0
).reset_index()
pur_pivot.columns = [str(c).strip() for c in pur_pivot.columns]
for c in ["年前采购","年后采购"]:
    if c not in pur_pivot.columns:
        pur_pivot[c] = 0
pur_pivot.rename(columns={"年前采购":"年前采购总量","年后采购":"年后采购总量"}, inplace=True)
df = df.merge(pur_pivot[["MSKU","年前采购总量","年后采购总量"]], on="MSKU", how="left")
df[["年前采购总量","年后采购总量"]] = df[["年前采购总量","年后采购总量"]].fillna(0)

# ---------------------- 4. 库存&金额计算 ----------------------
df["海外库存"] = df["FBA库存"] + df["FBA在途"] + df["海外仓可用"] + df["海外仓在途"]
df["本地库存"] = df["本地可用"] + df["待检待上架量"] + df["待交付"]
df["总库存"] = df["海外库存"] + df["本地库存"]
df["年前剩余库存"] = np.maximum(0, df["总库存"] - df["年后采购总量"])

df["海外滞销金额"] = df["海外库存"] * (df["采购成本"] + df["头程费用"])
df["本地滞销金额"] = df["本地库存"] * df["采购成本"]
df["总滞销金额"] = df["海外滞销金额"] + df["本地滞销金额"]
df["总库存金额"] = df["总库存"] * df["采购成本"]

# 周转天数：只用原表【日均】，不再自己算
df["日均"] = df["日均"].fillna(0)
df["周转天数"] = np.where(df["日均"]>0, df["总库存"]/df["日均"], np.nan)

# ---------------------- 5. 年份品口径选择 ----------------------
st.subheader("⚙️ 年份品滞销分析口径选择")
year_type_option = st.radio(
    "",
    ["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"],
    horizontal=True
)
TARGET_CLEAR_DATE = datetime(2026, 10, 31)

# ---------------------- 6. 滞销风险分级 ----------------------
def get_stock_risk(row):
    is_year = str(row["是否年份"]).strip() == "是"
    turn = row["周转天数"]
    stock = row["总库存"]
    avg = row["日均"]
    dt = row["时间"]

    if pd.isna(turn) or avg <= 0 or stock <= 0:
        return "无日均/库存数据"

    if not is_year:
        if turn <= 100:
            return "健康"
        elif 100 < turn <= 150:
            return "低滞销风险"
        elif 150 < turn <= 180:
            return "中滞销风险"
        else:
            return "高滞销风险"
    else:
        if year_type_option == "按照清库存口径（预计售罄时间）":
            need_days = stock / avg
            sell_dt = dt + timedelta(days=need_days)
            over = (sell_dt - TARGET_CLEAR_DATE).days
            if sell_dt <= TARGET_CLEAR_DATE:
                return "健康"
            elif 0 < over <=10:
                return "低滞销风险"
            elif 10 < over <=20:
                return "中滞销风险"
            else:
                return "高滞销风险"
        else:
            if turn <= 100:
                return "健康"
            elif 100 < turn <=150:
                return "低滞销风险"
            elif 150 < turn <=180:
                return "中滞销风险"
            else:
                return "高滞销风险"

df["滞销风险等级"] = df.apply(get_stock_risk, axis=1)

# ---------------------- 7. 时间筛选 单选 默认最新 ----------------------
st.divider()
time_list = sorted(df["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
sel_time = st.selectbox("选择统计时间", time_list, index=len(time_list)-1)

df_curr = df[df["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()
# 上月
df_prev = df.copy()
if len(time_list)>=2:
    prev_time = time_list[-2]
    df_prev = df[df["时间"].dt.strftime("%Y-%m-%d") == prev_time].copy()

# ---------------------- 8. 核心：5个横排卡片 跟你截图版式一致 ----------------------
st.divider()
st.subheader("📊 整体滞销情况概览")

risk_list = ["整体","健康","低滞销风险","中滞销风险","高滞销风险"]

def get_data_by_risk(d, risk):
    if risk=="整体":
        return d
    return d[d["滞销风险等级"]==risk]

# 5列卡片
c1,c2,c3,c4,c5 = st.columns(5)
cols = [c1,c2,c3,c4,c5]

for i,risk in enumerate(risk_list):
    curr = get_data_by_risk(df_curr, risk)
    prev = get_data_by_risk(df_prev, risk)

    sku_curr = curr["MSKU"].nunique()
    sku_prev = prev["MSKU"].nunique()
    sku_diff = sku_curr - sku_prev

    stock_curr = curr["总库存"].sum()
    stock_prev = prev["总库存"].sum()

    sale_risk = ["低滞销风险","中滞销风险","高滞销风险"]
    unsale_stock_curr = curr[curr["滞销风险等级"].isin(sale_risk)]["总库存"].sum()
    unsale_stock_prev = prev[prev["滞销风险等级"].isin(sale_risk)]["总库存"].sum()

    unsale_pct = unsale_stock_curr/stock_curr if stock_curr else 0

    amt_curr = curr["总库存金额"].sum()
    unsale_amt_curr = curr[curr["滞销风险等级"].isin(sale_risk)]["总滞销金额"].sum()
    amt_pct = unsale_amt_curr/amt_curr if amt_curr else 0

    with cols[i]:
        st.markdown(f"### {risk}")
        st.metric("SKU个数", f"{sku_curr}", f"{sku_diff}")
        st.metric("总库存", f"{stock_curr:,.0f}")
        st.metric("滞销库存(占比)", f"{unsale_stock_curr:,.0f} ({unsale_pct:.1%})")
        st.metric("总金额", f"{amt_curr:,.0f}")
        st.metric("滞销金额(占比)", f"{unsale_amt_curr:,.0f} ({amt_pct:.1%})")