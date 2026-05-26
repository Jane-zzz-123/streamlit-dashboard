import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="库存滞销分析", layout="wide")
st.title("📊 整体滞销情况分析")

# ================== 加载数据 ==================
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

# ================== 时间格式化 ==================
df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")

# ================== 合并数据 ==================
df_merge = df_snap.merge(df_sale[["MSKU", "时间", "销量"]], on=["MSKU", "时间"], how="left")
df_merge["销量"] = df_merge["销量"].fillna(0)

df_prod_use = df_prod[["MSKU", "是否年份", "类别", "岁数"]].drop_duplicates(subset=["MSKU"])
df_merge = df_merge.merge(df_prod_use, on="MSKU", how="left")

# ================== 采购数据处理 ==================
pur_pivot = df_pur.pivot_table(index="MSKU", columns="采购类型", values="采购量", aggfunc="sum", fill_value=0).reset_index()
for c in ["年前采购", "年后采购"]:
    if c not in pur_pivot.columns:
        pur_pivot[c] = 0
pur_pivot.rename(columns={"年前采购": "年前采购总量", "年后采购": "年后采购总量"}, inplace=True)
df_merge = df_merge.merge(pur_pivot[["MSKU", "年前采购总量", "年后采购总量"]], on="MSKU", how="left")

# ================== 库存 & 金额计算 ==================
df_merge["海外库存"] = (df_merge["FBA库存"] + df_merge["FBA在途"] + df_merge["海外仓可用"] + df_merge["海外仓在途"]).fillna(0)
df_merge["本地库存"] = (df_merge["本地可用"] + df_merge["待检待上架量"] + df_merge["待交付"]).fillna(0)
df_merge["总库存"] = df_merge["海外库存"] + df_merge["本地库存"]
df_merge["总库存金额"] = df_merge["总库存"] * df_merge["采购成本"].fillna(0)
df_merge["总滞销金额"] = (df_merge["海外库存"] * (df_merge["采购成本"] + df_merge["头程费用"]) + df_merge["本地库存"] * df_merge["采购成本"]).fillna(0)

# ================== 周转天数（用原表 日均） ==================
df_merge["日均"] = df_merge["日均"].fillna(0)
df_merge["周转天数"] = np.where(df_merge["日均"] > 0, df_merge["总库存"] / df_merge["日均"], np.nan)

# ================== 年份品口径 ==================
st.subheader("⚙️ 年份品计算口径")
year_option = st.radio("", ["按照清库存口径", "按照周转天数口径"], horizontal=True)
TARGET_CLEAR_DATE = datetime(2026, 10, 31)

# ================== 滞销风险判断 ==================
def get_risk(row):
    is_year = str(row["是否年份"]).strip() == "是"
    turn = row["周转天数"]
    stock = row["总库存"]
    avg = row["日均"]
    dt = row["时间"]

    if pd.isna(turn) or avg <= 0 or stock <= 0:
        return "无数据"

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
        if year_option == "按照清库存口径":
            need = stock / avg
            sell_dt = dt + timedelta(days=need)
            over = (sell_dt - TARGET_CLEAR_DATE).days
            if sell_dt <= TARGET_CLEAR_DATE:
                return "健康"
            elif 0 < over <= 10:
                return "低滞销风险"
            elif 10 < over <= 20:
                return "中滞销风险"
            else:
                return "高滞销风险"
        else:
            if turn <= 100:
                return "健康"
            elif 100 < turn <= 150:
                return "低滞销风险"
            elif 150 < turn <= 180:
                return "中滞销风险"
            else:
                return "高滞销风险"

df_merge["滞销风险等级"] = df_merge.apply(get_risk, axis=1)

# ================== 时间筛选 ==================
st.divider()
all_dates = sorted(df_merge["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
sel_date = st.selectbox("选择时间", all_dates, index=len(all_dates)-1)
df_curr = df_merge[df_merge["时间"].dt.strftime("%Y-%m-%d") == sel_date].copy()
df_prev = df_merge[df_merge["时间"].dt.strftime("%Y-%m-%d") == all_dates[-2]].copy() if len(all_dates) >= 2 else df_curr.copy()

# ================== 配色 & 标题 ==================
colors = {
    "整体": "#f0f0f0",
    "健康": "#e6f9e6",
    "低滞销风险": "#fff9e6",
    "中滞销风险": "#fff2e6",
    "高滞销风险": "#ffe6e6"
}

titles = ["整体", "健康", "低滞销风险", "中滞销风险", "高滞销风险"]

# ================== 计算指标 ==================
def calc(df, risk):
    d = df.copy() if risk == "整体" else df[df["滞销风险等级"] == risk]
    sku = d["MSKU"].nunique()
    stock = d["总库存"].sum()
    amt = d["总库存金额"].sum()

    unsale_stock = d[d["滞销风险等级"].isin(["低滞销风险", "中滞销风险", "高滞销风险"])]["总库存"].sum()
    unsale_amt = d[d["滞销风险等级"].isin(["低滞销风险", "中滞销风险", "高滞销风险"])]["总滞销金额"].sum()

    stock_pct = unsale_stock / stock if stock != 0 else 0
    amt_pct = unsale_amt / amt if amt != 0 else 0
    return sku, stock, unsale_stock, stock_pct, amt, unsale_amt, amt_pct

# ================== 展示卡片（5列） ==================
st.divider()
st.subheader("📦 整体滞销情况概览")
cols = st.columns(5)

for i, t in enumerate(titles):
    sku_c, stock_c, unsale_c, sp_c, amt_c, uamt_c, ap_c = calc(df_curr, t)
    sku_p, stock_p, unsale_p, sp_p, amt_p, uamt_p, ap_p = calc(df_prev, t)

    sku_diff = sku_c - sku_p
    stock_diff = stock_c - stock_p
    unsale_diff = unsale_c - unsale_p
    amt_diff = amt_c - amt_p
    uamt_diff = uamt_c - uamt_p

    card_color = colors[t]
    with cols[i]:
        # 带背景色的卡片
        st.markdown(f"""
        <div style="background-color:{card_color}; padding:12px; border-radius:8px; font-size:12px; line-height:1.8;">
        <div style="font-size:14px; font-weight:bold; margin-bottom:6px;">{t}</div>
        SKU个数：{sku_c}（对比上月{"+" if sku_diff>=0 else ""}{sku_diff}，上月：{sku_p}）<br>
        总库存：{stock_c:,.0f}（对比上月{"+" if stock_diff>=0 else ""}{stock_diff:,.0f}，上月：{stock_p:,.0f}）<br>
        滞销库存：{unsale_c:,.0f}（占比：{sp_c:.2%}）（对比上月{"+" if unsale_diff>=0 else ""}{unsale_diff:,.0f}，上月：{unsale_p:,.0f}）<br>
        总金额：{amt_c:,.0f}（对比上月{"+" if amt_diff>=0 else ""}{amt_diff:,.0f}，上月：{amt_p:,.0f}）<br>
        滞销金额：{uamt_c:,.0f}（占比：{ap_c:.2%}）（对比上月{"+" if uamt_diff>=0 else ""}{uamt_diff:,.0f}，上月：{uamt_p:,.0f}）
        </div>
        """, unsafe_allow_html=True)