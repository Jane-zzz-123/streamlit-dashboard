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
# 3. 合并：快照 + 销量（销量仅保留，不参与周转计算）
# ----------------------
df = df_snap.merge(df_sale, on=["MSKU", "时间"], how="left")
df["销量"] = df["销量"].fillna(0)

# ----------------------
# 4. 合并商品信息
# ----------------------
df_prod_use = df_prod[["MSKU", "是否年份", "类别", "岁数"]].drop_duplicates(subset=["MSKU"])
df = df.merge(df_prod_use, on="MSKU", how="left")

# ----------------------
# 5. 采购类型透视汇总 年前/年后采购
# ----------------------
pur_pivot = df_pur.pivot_table(
    index="MSKU",
    columns="采购类型",
    values="采购量",
    aggfunc="sum",
    fill_value=0
).reset_index()
pur_pivot.columns = [str(c).strip() for c in pur_pivot.columns]

for col in ["年前采购", "年后采购"]:
    if col not in pur_pivot.columns:
        pur_pivot[col] = 0

pur_pivot.rename(columns={"年前采购":"年前采购总量","年后采购":"年后采购总量"}, inplace=True)
df = df.merge(pur_pivot[["MSKU","年前采购总量","年后采购总量"]], on="MSKU", how="left")
df[["年前采购总量","年后采购总量"]] = df[["年前采购总量","年后采购总量"]].fillna(0)

# ----------------------
# 6. 库存 & 金额计算（沿用你原表真实列名）
# ----------------------
df["海外库存"] = df["FBA库存"] + df["FBA在途"] + df["海外仓可用"] + df["海外仓在途"]
df["本地库存"] = df["本地可用"] + df["待检待上架量"] + df["待交付"]
df["总库存"] = df["海外库存"] + df["本地库存"]

df["年前剩余库存"] = np.maximum(0, df["总库存"] - df["年后采购总量"])

df["海外滞销金额"] = df["海外库存"] * (df["采购成本"] + df["头程费用"])
df["本地滞销金额"] = df["本地库存"] * df["采购成本"]
df["总滞销金额"] = df["海外滞销金额"] + df["本地滞销金额"]
df["总库存金额"] = df["总库存"] * df["采购成本"]

# ----------------------
# 7. 周转天数：直接用【快照表的日均】，不再自己算！
# ----------------------
# 日均取自原列 日均
df["日均"] = df["日均"].fillna(0)

# 计算周转天数：总库存 / 日均；日均<=0 置空
df["周转天数"] = np.where(
    df["日均"] > 0,
    df["总库存"] / df["日均"],
    np.nan
)

# ----------------------
# 8. 年份品口径选择器
# ----------------------
st.divider()
st.subheader("⚙️ 年份品滞销分析口径选择")
year_type_option = st.radio(
    "请选择年份品计算方式",
    options=["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"],
    horizontal=True
)
TARGET_CLEAR_DATE = datetime(2026, 10, 31)

# ----------------------
# 9. 滞销风险判定（完全按你规则，日均用原表字段）
# ----------------------
def get_stock_risk(row):
    is_year_product = str(row["是否年份"]).strip() == "是"
    turn_days = row["周转天数"]
    total_stock = row["总库存"]
    avg = row["日均"]
    current_date = row["时间"]

    if pd.isna(turn_days) or avg <= 0 or total_stock <= 0:
        return "无日均/库存数据"

    # 非年份品 按周转天数分级
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
        need_days = total_stock / avg
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
        # 年份品同周转天数口径
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
# 10. 时间筛选器 单选默认最新
# ----------------------
st.divider()
st.subheader("📅 选择统计时间")
time_list = sorted(df["时间"].dt.strftime("%Y-%m-%d").dropna().unique())
sel_time = st.selectbox("选择时间", time_list, index=len(time_list)-1)

df_current = df[df["时间"].dt.strftime("%Y-%m-%d") == sel_time].copy()

# 上月数据
if len(time_list) >= 2:
    prev_time = time_list[-2]
    df_prev = df[df["时间"].dt.strftime("%Y-%m-%d") == prev_time].copy()
else:
    df_prev = df_current.copy()

# ----------------------
# 11. 整体5大卡片指标计算
# ----------------------
st.divider()
st.subheader("📊 一、整体滞销情况分析")
risk_list = ["整体", "健康", "低滞销风险", "中滞销风险", "高滞销风险"]

def calc_metrics(data, risk_name):
    if risk_name != "整体":
        d = data[data["滞销风险等级"] == risk_name]
    else:
        d = data

    sku_num = d["MSKU"].nunique()
    total_stock = d["总库存"].sum()
    total_amt = d["总库存金额"].sum()

    # 滞销定义：低/中/高 都算滞销
    sale_risk = ["低滞销风险","中滞销风险","高滞销风险"]
    unsale_stock = d[d["滞销风险等级"].isin(sale_risk)]["总库存"].sum()
    unsale_amt = d[d["滞销风险等级"].isin(sale_risk)]["总滞销金额"].sum()

    stock_pct = unsale_stock / total_stock if total_stock != 0 else 0
    amt_pct = unsale_amt / total_amt if total_amt != 0 else 0

    return {
        "sku_num": sku_num,
        "total_stock": total_stock,
        "unsale_stock": unsale_stock,
        "stock_pct": stock_pct,
        "total_amt": total_amt,
        "unsale_amt": unsale_amt,
        "amt_pct": amt_pct
    }

curr_metric = {r:calc_metrics(df_current, r) for r in risk_list}
prev_metric = {r:calc_metrics(df_prev, r) for r in risk_list}

# 排版5列卡片
cols = st.columns(5)
for idx, risk in enumerate(risk_list):
    with cols[idx]:
        c = curr_metric[risk]
        p = prev_metric[risk]

        st.markdown(f"#### {risk}")
        st.metric("SKU个数", f"{c['sku_num']:,}", f"{c['sku_num'] - p['sku_num']:,}")
        st.metric("总库存", f"{c['total_stock']:,.0f}", f"{c['total_stock'] - p['total_stock']:,.0f}")
        st.metric("滞销库存", f"{c['unsale_stock']:,.0f}({c['stock_pct']:.1%})",
                  f"{c['unsale_stock'] - p['unsale_stock']:,.0f}")
        st.metric("总金额", f"{c['total_amt']:,.0f}", f"{c['total_amt'] - p['total_amt']:,.0f}")
        st.metric("滞销金额", f"{c['unsale_amt']:,.0f}({c['amt_pct']:.1%})",
                  f"{c['unsale_amt'] - p['unsale_amt']:,.0f}")