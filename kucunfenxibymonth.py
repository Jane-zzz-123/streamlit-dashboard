import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="库存滞销复盘看板", layout="wide")
st.title("📊 整体滞销情况分析")


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

df_snap["时间"] = pd.to_datetime(df_snap["时间"], errors="coerce")
df_sale["时间"] = pd.to_datetime(df_sale["时间"], errors="coerce")

df_merge = df_snap.merge(df_sale[["MSKU", "时间", "销量"]], on=["MSKU", "时间"], how="left")
df_merge["销量"] = df_merge["销量"].fillna(0)

df_prod_use = df_prod[["MSKU", "是否年份", "类别", "岁数"]].drop_duplicates(subset=["MSKU"])
df_merge = df_merge.merge(df_prod_use, on="MSKU", how="left")

pur_pivot = df_pur.pivot_table(index="MSKU", columns="采购类型", values="采购量", aggfunc="sum",
                               fill_value=0).reset_index()
for c in ["年前采购", "年后采购"]:
    if c not in pur_pivot.columns:
        pur_pivot[c] = 0
pur_pivot.rename(columns={"年前采购": "年前采购总量", "年后采购": "年后采购总量"}, inplace=True)
df_merge = df_merge.merge(pur_pivot[["MSKU", "年前采购总量", "年后采购总量"]], on="MSKU", how="left")

df_merge["海外库存"] = (
            df_merge["FBA库存"] + df_merge["FBA在途"] + df_merge["海外仓可用"] + df_merge["海外仓在途"]).fillna(0)
df_merge["本地库存"] = (df_merge["本地可用"] + df_merge["待检待上架量"] + df_merge["待交付"]).fillna(0)
df_merge["总库存"] = df_merge["海外库存"] + df_merge["本地库存"]
df_merge["总库存金额"] = df_merge["总库存"] * df_merge["采购成本"].fillna(0)
df_merge["总滞销金额"] = (
            df_merge["海外库存"] * (df_merge["采购成本"] + df_merge["头程费用"]) + df_merge["本地库存"] * df_merge[
        "采购成本"]).fillna(0)

df_merge["日均"] = df_merge["日均"].fillna(0)
df_merge["周转天数"] = np.where(df_merge["日均"] > 0, df_merge["总库存"] / df_merge["日均"], np.nan)

st.subheader("⚙️ 年份品计算口径")
year_option = st.radio("", ["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"], horizontal=True)
TARGET_CLEAR_DATE = datetime(2026, 10, 31)


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

    if year_option == "按照清库存口径（预计售罄时间）":
        need_days = stock / avg
        sell_dt = dt + timedelta(days=need_days)
        over_days = (sell_dt - TARGET_CLEAR_DATE).days
        if sell_dt <= TARGET_CLEAR_DATE:
            return "健康"
        elif 0 < over_days <= 10:
            return "低滞销风险"
        elif 10 < over_days <= 20:
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


df_merge["滞销风险等级"] = df_merge.apply(get_stock_risk, axis=1)

st.divider()
time_list = sorted(df_merge["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
sel_time = st.selectbox("选择统计时间", time_list, index=len(time_list) - 1)

df_curr = df_merge[df_merge["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()
if len(time_list) >= 2:
    prev_time = time_list[-2]
    df_prev = df_merge[df_merge["时间"].dt.strftime("%Y-%m-%d") == prev_time].copy()
else:
    df_prev = df_curr.copy()

card_config = [
    {"title": "整体", "bg_color": "#f0f0f0"},
    {"title": "健康", "bg_color": "#e6f9e6"},
    {"title": "低滞销风险", "bg_color": "#fff9e6"},
    {"title": "中滞销风险", "bg_color": "#fff2e6"},
    {"title": "高滞销风险", "bg_color": "#ffe6e6"}
]


def calc_metrics(df_curr, df_prev, risk_name):
    if risk_name == "整体":
        curr_data = df_curr.copy()
        prev_data = df_prev.copy()
    else:
        curr_data = df_curr[df_curr["滞销风险等级"] == risk_name].copy()
        prev_data = df_prev[df_prev["滞销风险等级"] == risk_name].copy()

    sku_curr = curr_data["MSKU"].nunique()
    sku_prev = prev_data["MSKU"].nunique()
    sku_diff = sku_curr - sku_prev

    stock_curr = curr_data["总库存"].sum()
    stock_prev = prev_data["总库存"].sum()
    stock_diff = stock_curr - stock_prev

    amt_curr = curr_data["总库存金额"].sum()
    amt_prev = prev_data["总库存金额"].sum()
    amt_diff = amt_curr - amt_prev

    sale_risk_list = ["低滞销风险", "中滞销风险", "高滞销风险"]
    unsale_stock_curr = curr_data[curr_data["滞销风险等级"].isin(sale_risk_list)]["总库存"].sum()
    unsale_stock_prev = prev_data[prev_data["滞销风险等级"].isin(sale_risk_list)]["总库存"].sum()
    unsale_stock_diff = unsale_stock_curr - unsale_stock_prev
    unsale_stock_pct = unsale_stock_curr / stock_curr if stock_curr != 0 else 0

    unsale_amt_curr = curr_data[curr_data["滞销风险等级"].isin(sale_risk_list)]["总滞销金额"].sum()
    unsale_amt_prev = prev_data[prev_data["滞销风险等级"].isin(sale_risk_list)]["总滞销金额"].sum()
    unsale_amt_diff = unsale_amt_curr - unsale_amt_prev
    unsale_amt_pct = unsale_amt_curr / amt_curr if amt_curr != 0 else 0

    return {
        "sku_curr": sku_curr, "sku_prev": sku_prev, "sku_diff": sku_diff,
        "stock_curr": stock_curr, "stock_prev": stock_prev, "stock_diff": stock_diff,
        "amt_curr": amt_curr, "amt_prev": amt_prev, "amt_diff": amt_diff,
        "unsale_stock_curr": unsale_stock_curr, "unsale_stock_prev": unsale_stock_prev,
        "unsale_stock_diff": unsale_stock_diff, "unsale_stock_pct": unsale_stock_pct,
        "unsale_amt_curr": unsale_amt_curr, "unsale_amt_prev": unsale_amt_prev,
        "unsale_amt_diff": unsale_amt_diff, "unsale_amt_pct": unsale_amt_pct
    }


st.divider()
st.subheader("📦 整体滞销情况概览")
cols = st.columns(5)

# --- 把函数提到循环外面，只定义一次 ---
def get_diff_color(diff):
    return "red" if diff >= 0 else "green"

def get_diff_sign(diff):
    return f"+{diff}" if diff >= 0 else f"{diff}"

for idx, config in enumerate(card_config):
    metrics = calc_metrics(df_curr, df_prev, config["title"])

    # --- 先把所有值算好，再塞进 f-string ---
    sku_curr = metrics['sku_curr']
    sku_prev = metrics['sku_prev']
    sku_diff = metrics['sku_diff']
    sku_color = get_diff_color(sku_diff)
    sku_sign = get_diff_sign(sku_diff)

    stock_curr = round(metrics['stock_curr'])
    stock_prev = round(metrics['stock_prev'])
    stock_diff = round(metrics['stock_diff'])
    stock_color = get_diff_color(stock_diff)
    stock_sign = get_diff_sign(stock_diff)

    unsale_stock_curr = round(metrics['unsale_stock_curr'])
    unsale_stock_prev = round(metrics['unsale_stock_prev'])
    unsale_stock_diff = round(metrics['unsale_stock_diff'])
    unsale_stock_pct = metrics['unsale_stock_pct']
    unsale_stock_color = get_diff_color(unsale_stock_diff)
    unsale_stock_sign = get_diff_sign(unsale_stock_diff)

    amt_curr = round(metrics['amt_curr'])
    amt_prev = round(metrics['amt_prev'])
    amt_diff = round(metrics['amt_diff'])
    amt_color = get_diff_color(amt_diff)
    amt_sign = get_diff_sign(amt_diff)

    unsale_amt_curr = round(metrics['unsale_amt_curr'])
    unsale_amt_prev = round(metrics['unsale_amt_prev'])
    unsale_amt_diff = round(metrics['unsale_amt_diff'])
    unsale_amt_pct = metrics['unsale_amt_pct']
    unsale_amt_color = get_diff_color(unsale_amt_diff)
    unsale_amt_sign = get_diff_sign(unsale_amt_diff)

    with cols[idx]:
        st.markdown(f"""
        <div style="background-color:{config['bg_color']}; padding:20px; border-radius:12px; line-height:2.2;">
            <div style="font-size:22px; font-weight:bold; text-align:center; margin-bottom:15px;">
                {config['title']}
            </div>

            <div style="font-size:18px; font-weight:bold; margin-bottom:8px;">
                SKU个数：{sku_curr:,}
                <span style="font-size:12px; color:{sku_color};">
                    （{sku_sign}，上月：{sku_prev:,}）
                </span>
            </div>

            <div style="font-size:14px; margin-bottom:6px;">
                总库存：{stock_curr:,}
                <span style="font-size:11px; color:{stock_color};">
                    （{stock_sign}，上月：{stock_prev:,}）
                </span>
            </div>

            <div style="font-size:14px; margin-bottom:6px;">
                滞销库存：{unsale_stock_curr:,}（占比：{unsale_stock_pct:.2%}）
                <span style="font-size:11px; color:{unsale_stock_color};">
                    （{unsale_stock_sign}，上月：{unsale_stock_prev:,}）
                </span>
            </div>

            <div style="font-size:14px; margin-bottom:6px;">
                总金额：{amt_curr:,}
                <span style="font-size:11px; color:{amt_color};">
                    （{amt_sign}，上月：{amt_prev:,}）
                </span>
            </div>

            <div style="font-size:14px;">
                滞销金额：{unsale_amt_curr:,}（占比：{unsale_amt_pct:.2%}）
                <span style="font-size:11px; color:{unsale_amt_color};">
                    （{unsale_amt_sign}，上月：{unsale_amt_prev:,}）
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)