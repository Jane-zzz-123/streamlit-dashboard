import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# ===================== 【1. 全局配置：账号&店铺权限（在这里维护人员权限）】 =====================
# 格式：用户名: {"pwd": "密码", "shops": ["店铺A", "店铺B"]}
# shops = ["全部"] 代表超级管理员，可查看所有店铺
USER_AUTH = {
    # 超级管理员（可查看全部店铺）
    "admin": {
        "pwd": "admin1234",
        "shops": ["全部"]
    },
    # 运营1：仅负责 店铺01、店铺02
    "黄怡": {
        "pwd": "syc-huangyi123",
        "shops": ["思业成-US"]
    },
    "黄怡-定行": {
        "pwd": "dx-HHHyi123",
        "shops": ["定行-US"]
    },
    "小娇": {
        "pwd": "pt and ys-xiaojiao",
        "shops": ["拼途-US","艺胜-US"]
    },
    "楷纯": {
        "pwd": "zy and cr-kaichun",
        "shops": ["争艳-US","辰瑞-US"]
    },
    "淑谊": {
        "pwd": "sx and jy-shuyi",
        "shops": ["势兴-US","进益-US"]
    },
    "佰英": {
        "pwd": "cq-baiying123",
        "shops": ["创奇-US"]
    },
    "李珊": {
        "pwd": "dm-lishan123",
        "shops": ["大卖-US"]
    },
}

# 初始化session_state（Streamlit状态存储）
if "login_status" not in st.session_state:
    st.session_state.login_status = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "user_shops" not in st.session_state:
    st.session_state.user_shops = []


# ===================== 【2. 登录页面逻辑】 =====================
# ===================== 【2. 登录页面逻辑（优化版：账号下拉选择）】 =====================
def login_page():
    st.title("🔐 库存滞销看板(按月更新） - 登录界面验证")
    st.divider()

    # 提取所有可用账号列表
    all_user_list = list(USER_AUTH.keys())
    # 下拉选择账号，不用手动输入
    select_username = st.selectbox("请选择登录账号", options=["请选择账号"] + all_user_list)

    password = st.text_input("请输入密码", type="password")
    login_btn = st.button("登录", type="primary")

    if login_btn:
        # 判断是否选了账号
        if select_username == "请选择账号":
            st.error("❌ 请先选择你的登录账号")
            return
        # 账号密码校验
        target_user = USER_AUTH[select_username]
        if target_user["pwd"] != password:
            st.error("❌ 密码错误，请重新输入")
            return

        # 登录成功，写入状态
        st.session_state.login_status = True
        st.session_state.current_user = select_username
        st.session_state.user_shops = target_user["shops"]
        st.rerun()  # 刷新页面进入看板


# 未登录则只展示登录页，终止后续代码
if not st.session_state.login_status:
    login_page()
    st.stop()

# ===================== 【3. 主页面开始（已登录）】 =====================
st.set_page_config(page_title="库存滞销复盘看板", layout="wide")

# 顶部用户信息 + 退出按钮
col_user, col_logout = st.columns([8, 1])
with col_user:
    st.info(f"👤 当前登录用户：{st.session_state.current_user} | 可查看店铺：{st.session_state.user_shops}")
with col_logout:
    if st.button("退出登录"):
        # 清空登录状态
        st.session_state.login_status = False
        st.session_state.current_user = ""
        st.session_state.user_shops = []
        st.rerun()

st.title("📊 整体滞销情况分析")

# ===================== 常量配置 =====================
TARGET_CLEAR_DATE = datetime(2026, 10, 31)
RISK_LEVELS = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]
RISK_COLORS = {
    "整体": "#f5f5f5",
    "健康": "#e8f5e9",
    "低滞销风险": "#fff8e1",
    "中滞销风险": "#ffebee",
    "高滞销风险": "#ffcdd2",
}


# ===================== 数据加载 =====================
@st.cache_data(ttl=3600, show_spinner="正在加载数据...")
def load_data(file: str = "moon-date.xlsx") -> Tuple[pd.DataFrame, ...]:
    sheets = {
        "snap": "补货建议-每月快照",
        "prod": "商品信息",
        "sale": "销量数据-每月",
        "pur": "采购数据-每月",
    }
    dfs = {}
    with pd.ExcelFile(file) as xls:
        for key, sheet_name in sheets.items():
            df = pd.read_excel(xls, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            dfs[key] = df

    dfs["snap"]["时间"] = pd.to_datetime(dfs["snap"]["时间"], errors="coerce").dt.normalize()
    dfs["sale"]["时间"] = pd.to_datetime(dfs["sale"]["时间"], errors="coerce").dt.normalize()

    return dfs["snap"], dfs["prod"], dfs["sale"], dfs["pur"]


df_snap, df_prod, df_sale, df_pur = load_data()


# ===================== 数据加工：按你最新公式 100% 重写 =====================
def build_master_df(df_snap, df_prod, df_sale, df_pur):
    df = df_snap.merge(df_sale[["MSKU", "时间", "销量"]], on=["MSKU", "时间"], how="left")
    df["销量"] = df["销量"].fillna(0)

    prod_cols = ["MSKU", "是否年份", "类别", "岁数"]
    df_prod_use = df_prod[prod_cols].drop_duplicates(subset=["MSKU"])
    df = df.merge(df_prod_use, on="MSKU", how="left")

    pur_pivot = df_pur.pivot_table(index="MSKU", columns="采购类型", values="采购量", aggfunc="sum",
                                   fill_value=0).reset_index()
    rename_map = {}
    if "年前采购" in pur_pivot.columns: rename_map["年前采购"] = "年前采购总量"
    if "年后采购" in pur_pivot.columns: rename_map["年后采购"] = "年后采购总量"
    pur_pivot = pur_pivot.rename(columns=rename_map)
    for c in ["年前采购总量", "年后采购总量"]:
        if c not in pur_pivot.columns: pur_pivot[c] = 0

    df = df.merge(pur_pivot[["MSKU", "年前采购总量", "年后采购总量"]], on="MSKU", how="left")

    # ===================== 【最新公式】FBA+AWD+在途库存 =====================
    df["FBA+AWD+在途库存"] = (
            df["FBA库存"].fillna(0)
            + df["FBA在途"].fillna(0)
            + df["海外仓可用"].fillna(0)
            + df["海外仓在途"].fillna(0)
    ).round(2)

    # ===================== 本地库存 =====================
    df["本地库存"] = (
            df["本地可用"].fillna(0)
            + df["待检待上架量"].fillna(0)
            + df["待交付"].fillna(0)
    ).round(2)

    # ===================== 【最新公式】总库存 =====================
    df["总库存"] = (
            df["FBA+AWD+在途库存"]
            + df["本地库存"]
    ).round(2)

    # 日均销量防0处理
    df["日均"] = df["日均"].fillna(0)
    df.loc[df["日均"] == 0, "日均"] = 0.01

    # ===================== 周转天数 =====================
    df["周转天数"] = (df["总库存"] / df["日均"]).round(2)
    df["周转天数"] = df["周转天数"].clip(upper=36500)

    # ===================== 【追加】FBA 独立周转天数 =====================
    df["周转天数_FBA"] = (df["FBA+AWD+在途库存"] / df["日均"]).round(2)
    df["周转天数_FBA"] = df["周转天数_FBA"].clip(upper=36500)

    # ===================== 预计用完时间 =====================
    df["预计总库存用完时间"] = df["时间"] + pd.to_timedelta(df["周转天数"], unit="D")

    # ===================== 【追加】FBA 预计用完时间 =====================
    df["预计FBA用完时间"] = df["时间"] + pd.to_timedelta(df["周转天数_FBA"], unit="D")

    # ===================== ✅ 正确金额计算（你要求的版本） =====================
    df["采购成本"] = df["采购成本"].fillna(0)
    df["头程费用"] = df["头程费用"].fillna(0)

    # FBA金额 = FBA库存 * (成本+头程)
    df["FBA金额"] = (df["FBA+AWD+在途库存"] * (df["采购成本"] + df["头程费用"])).round(2)
    # 本地金额 = 本地库存 * 成本
    df["本地金额"] = (df["本地库存"] * df["采购成本"]).round(2)
    # 总金额 = FBA金额 + 本地金额
    df["总库存金额"] = (df["FBA金额"] + df["本地金额"]).round(2)

    return df


df_merge = build_master_df(df_snap, df_prod, df_sale, df_pur)

# ===================== 【4. 新增：店铺筛选 + 权限过滤】 =====================
st.divider()
st.subheader("📌 筛选条件")

# 1. 获取当前用户有权限的店铺列表
user_allow_shops = st.session_state.user_shops
all_shops = df_merge["店铺"].dropna().unique().tolist()

# 2. 构建下拉框可选店铺
if "全部" in user_allow_shops:
    # 管理员：可选 全部 + 所有单个店铺
    shop_options = ["全部"] + sorted(all_shops)
else:
    # 普通运营：仅能选自己负责的店铺，无"全部"选项
    shop_options = sorted(user_allow_shops)

# 店铺选择器（核心新增）
sel_shop = st.selectbox("选择店铺", shop_options, index=0)

# 3. 根据选择 + 权限 过滤数据
if sel_shop == "全部":
    # 选全部：使用用户权限内所有店铺
    if "全部" in user_allow_shops:
        df_filter = df_merge.copy()
    else:
        df_filter = df_merge[df_merge["店铺"].isin(user_allow_shops)].copy()
else:
    # 选单个店铺：精准过滤
    df_filter = df_merge[df_merge["店铺"] == sel_shop].copy()


# ===================== 风险等级 + 滞销数量 100% 按你要求 =====================
def classify_risk_and_unsold(df, year_option, target_date):
    df = df.copy()
    df_idx = df.index
    is_year = df["是否年份"].astype(str).str.strip() == "是"

    # ---------- 1. 基准天数 ----------
    target_days_common = 120
    target_days_year = (target_date - df["时间"]).dt.days  # 到2026-10-31的天数
    df["目标基准天数"] = np.where(
        (is_year) & (year_option == "按照清库存口径（预计售罄时间）"),
        target_days_year,
        target_days_common
    )

    # ---------- 2. 预计用完时间 & 超期天数 ----------
    df["预计总库存用完时间"] = df["时间"] + pd.to_timedelta(df["周转天数"], unit="D")
    over_days = (df["预计总库存用完时间"] - target_date).dt.days

    # ---------- 3. 总库存风险判定 ----------
    risk = pd.Series("高滞销风险", index=df_idx)

    if year_option == "按照库存周转天数口径":
        turn = df["周转天数"]
        risk = pd.Series(np.where(turn <= 120, "健康",
                 np.where(turn <= 150, "低滞销风险",
                 np.where(turn <= 180, "中滞销风险", "高滞销风险"))), index=df_idx)
    else:
        # 非年份品：周转天数
        mask_non_year = ~is_year
        turn_non_year = df.loc[mask_non_year, "周转天数"]
        risk.loc[mask_non_year] = np.where(
            turn_non_year <= 120, "健康",
            np.where(turn_non_year <= 150, "低滞销风险",
            np.where(turn_non_year <= 180, "中滞销风险", "高滞销风险"))
        )
        # 年份品：超期天数
        mask_year = is_year
        over_year = over_days.loc[mask_year]
        risk.loc[mask_year] = np.where(
            over_year <= 0, "健康",
            np.where((over_year > 0) & (over_year <= 10), "低滞销风险",
            np.where((over_year > 10) & (over_year <= 20), "中滞销风险",
            "高滞销风险"))
        )
    df["滞销风险等级"] = risk

    # ===================== 滞销数量 =====================
    unhealthy = df["滞销风险等级"] != "健康"
    base = df["目标基准天数"]

    df["FBA+AWD+在途滞销数量"] = np.where(
        unhealthy,
        (df["FBA+AWD+在途库存"] - df["日均"] * base).clip(lower=0).round(2),
        0
    )
    df["总滞销库存"] = np.where(
        unhealthy,
        (df["总库存"] - df["日均"] * base).clip(lower=0).round(2),
        0
    )
    df["本地滞销数量"] = (df["总滞销库存"] - df["FBA+AWD+在途滞销数量"]).round(2)

    # ===================== 滞销金额 =====================
    df["FBA滞销金额"] = (df["FBA+AWD+在途滞销数量"] * (df["采购成本"] + df["头程费用"])).round(2)
    df["本地滞销金额"] = (df["本地滞销数量"] * df["采购成本"]).round(2)
    df["总滞销金额"] = (df["FBA滞销金额"] + df["本地滞销金额"]).round(2)

    # -------------------------------------------------------------------------
    # 修复FBA独立风险（核心修复点：用Series带索引，不再丢失长度）
    # -------------------------------------------------------------------------
    over_days_fba = (df["预计FBA用完时间"] - target_date).dt.days
    risk_fba = pd.Series("高滞销风险", index=df_idx)

    if year_option == "按照库存周转天数口径":
        turn_fba = df["周转天数_FBA"]
        risk_fba = pd.Series(np.where(turn_fba <= 90, "健康",
                   np.where(turn_fba <= 120, "低滞销风险",
                   np.where(turn_fba <= 150, "中滞销风险", "高滞销风险"))), index=df_idx)
    else:
        mask_non_year = ~is_year
        turn_non_year_fba = df.loc[mask_non_year, "周转天数_FBA"]
        risk_fba.loc[mask_non_year] = np.where(
            turn_non_year_fba <= 90, "健康",
            np.where(turn_non_year_fba <= 120, "低滞销风险",
            np.where(turn_non_year_fba <= 150, "中滞销风险", "高滞销风险"))
        )
        mask_year = is_year
        over_year_fba = over_days_fba.loc[mask_year]
        risk_fba.loc[mask_year] = np.where(
            over_year_fba <= 0, "健康",
            np.where((over_year_fba > 0) & (over_year_fba <= 10), "低滞销风险",
            np.where((over_year_fba > 10) & (over_year_fba <= 20), "中滞销风险",
            "高滞销风险"))
        )
    # 赋值带索引的Series，长度100%匹配df
    df["滞销风险等级_FBA"] = risk_fba

    unhealthy_fba = df["滞销风险等级_FBA"] != "健康"
    target_days_common1 = 90
    target_days_year = (target_date - df["时间"]).dt.days
    df["目标基准天数1"] = np.where(
        (is_year) & (year_option == "按照清库存口径（预计售罄时间）"),
        target_days_year,
        target_days_common1
    )
    base1 = df["目标基准天数1"]
    df["FBA滞销数量_仅FBA"] = np.where(
        unhealthy_fba,
        (df["FBA+AWD+在途库存"] - df["日均"] * base1).clip(lower=0).round(2),
        0
    )
    df["FBA滞销金额_仅FBA"] = (df["FBA滞销数量_仅FBA"] * (df["采购成本"] + df["头程费用"])).round(2)

    return df


# ===================== 界面 =====================
st.subheader("⚙️ 年份品计算口径")
year_option = st.radio("", ["按照清库存口径（预计售罄时间）", "按照库存周转天数口径"], horizontal=True)

# 使用**过滤后的数据集**计算风险（关键：替换成 df_filter）
df_filter = classify_risk_and_unsold(df_filter, year_option, TARGET_CLEAR_DATE)

st.divider()
df_filter["年月"] = df_filter["时间"].dt.to_period("M")
time_list = sorted(df_filter["年月"].dropna().astype(str).unique())
sel_month = st.selectbox("选择统计时间", time_list, index=len(time_list) - 1)

prev_month = sel_month
if len(time_list) >= 2:
    idx = time_list.index(sel_month)
    prev_month = time_list[idx - 1] if idx > 0 else sel_month

df_curr = df_filter[df_filter["年月"] == sel_month].copy()
df_prev = df_filter[df_filter["年月"] == prev_month].copy()

# 新增这一行，仅此一处改动
active_shops = df_filter["店铺"].unique().tolist()
# ===================== 指标计算 =====================
# ===================== 【修改后】总库存指标计算 =====================
# ===================== 【总库存指标计算】 =====================
def calc_metrics(df_curr, df_prev, risk_name, all_unsale_stock=0, all_unsale_amt=0):
    risk_list = ["低滞销风险", "中滞销风险", "高滞销风险"]
    if risk_name == "整体":
        curr_unsale = df_curr[df_curr["滞销风险等级"].isin(risk_list)]
        prev_unsale = df_prev[df_prev["滞销风险等级"].isin(risk_list)]

        sku_c = df_curr["MSKU"].nunique()
        sku_p = df_prev["MSKU"].nunique()
        sku_diff = sku_c - sku_p

        stk_c = float(df_curr["总库存"].sum())
        stk_p = float(df_prev["总库存"].sum())
        stk_diff = stk_c - stk_p

        amt_c = float(df_curr["总库存金额"].sum())
        amt_p = float(df_prev["总库存金额"].sum())
        amt_diff = amt_c - amt_p

        u_stk_c = float(curr_unsale["总滞销库存"].sum())
        u_stk_p = float(prev_unsale["总滞销库存"].sum())
        u_stk_diff = u_stk_c - u_stk_p
        pct_stk = u_stk_c / stk_c if stk_c != 0 else 0

        u_amt_c = float(curr_unsale["总滞销金额"].sum())
        u_amt_p = float(prev_unsale["总滞销金额"].sum())
        u_amt_diff = u_amt_c - u_amt_p
        pct_amt = u_amt_c / amt_c if amt_c != 0 else 0
    else:
        c = df_curr[df_curr["滞销风险等级"] == risk_name]
        p = df_prev[df_prev["滞销风险等级"] == risk_name]

        sku_c = c["MSKU"].nunique()
        sku_p = p["MSKU"].nunique()
        sku_diff = sku_c - sku_p

        stk_c = float(c["总库存"].sum())
        stk_p = float(p["总库存"].sum())
        stk_diff = stk_c - stk_p

        amt_c = float(c["总库存金额"].sum())
        amt_p = float(p["总库存金额"].sum())
        amt_diff = amt_c - amt_p

        u_stk_c = float(c["总滞销库存"].sum())
        u_stk_p = float(p["总滞销库存"].sum())
        u_stk_diff = u_stk_c - u_stk_p
        pct_stk = u_stk_c / all_unsale_stock if all_unsale_stock != 0 else 0

        u_amt_c = float(c["总滞销金额"].sum())
        u_amt_p = float(p["总滞销金额"].sum())
        u_amt_diff = u_amt_c - u_amt_p
        pct_amt = u_amt_c / all_unsale_amt if all_unsale_amt != 0 else 0
    return {
        "sku_curr": sku_c, "sku_prev": sku_p, "sku_diff": sku_diff,
        "stock_curr": stk_c, "stock_prev": stk_p, "stock_diff": stk_diff,
        "amt_curr": amt_c, "amt_prev": amt_p, "amt_diff": amt_diff,
        "unsale_stock_curr": u_stk_c, "unsale_stock_prev": u_stk_p, "unsale_stock_diff": u_stk_diff, "unsale_stock_pct": pct_stk,
        "unsale_amt_curr": u_amt_c, "unsale_amt_prev": u_amt_p, "unsale_amt_diff": u_amt_diff, "unsale_amt_pct": pct_amt
    }


# ===================== 卡片渲染 =====================
def render_card_compact(title, m):
    bg = RISK_COLORS.get(title, "#f5f5f5")

    # 数值格式化：正数红色，负数绿色
    def fmt(d):
        d = float(d)
        return ("#e53935", f"+{d:,.0f}") if d >= 0 else ("#2e7d32", f"{d:,.0f}")

    # 各指标的环比颜色+符号
    sku_c, sku_s = fmt(m["sku_diff"])
    stk_c, stk_s = fmt(m["stock_diff"])
    amt_c, amt_s = fmt(m["amt_diff"])

    # 卡片HTML主体
    parts = [f'<div style="background:{bg};padding:20px;border-radius:12px;margin-bottom:15px;">',
             f'<div style="font-size:22px;font-weight:bold;text-align:center">{title}</div>',
             # SKU：当前值 + 上月值 + 环比
             f'<div style="font-size:18px;font-weight:bold">SKU：{m["sku_curr"]:,.0f} （上月：{m["sku_prev"]:,.0f}） <span style="color:{sku_c}">({sku_s})</span></div>',
             # 总库存：当前值 + 上月值 + 环比
             f'<div style="font-size:14px">总库存：{m["stock_curr"]:,.0f} （上月：{m["stock_prev"]:,.0f}） <span style="color:{stk_c}">({stk_s})</span></div>']

    # 非健康卡片：新增滞销指标（含上月值）
    if title != "健康":
        usc, uss = fmt(m["unsale_stock_diff"])
        uac, uas = fmt(m["unsale_amt_diff"])
        parts.append(
            f'<div style="font-size:14px">滞销库存：{m["unsale_stock_curr"]:,.0f} ({m["unsale_stock_pct"]:.1%}) （上月：{m["unsale_stock_prev"]:,.0f}） <span style="color:{usc}">({uss})</span></div>')
        parts.append(
            f'<div style="font-size:14px">滞销金额：{m["unsale_amt_curr"]:,.0f} ({m["unsale_amt_pct"]:.1%}) （上月：{m["unsale_amt_prev"]:,.0f}） <span style="color:{uac}">({uas})</span></div>')

    # 总金额：当前值 + 上月值 + 环比
    parts.append(
        f'<div style="font-size:14px">总金额：{m["amt_curr"]:,.0f} （上月：{m["amt_prev"]:,.0f}） <span style="color:{amt_c}">({amt_s})</span></div></div>')
    st.html("".join(parts))


# ===================== 【新增】FBA+AWD+在途库存 指标计算（和总库存结构完全一样） =====================
# ===================== 【FBA指标计算】 =====================
def calc_metrics_fba(df_curr, df_prev, risk_name, all_unsale_stock_fba=0, all_unsale_amt_fba=0):
    risk_list = ["低滞销风险", "中滞销风险", "高滞销风险"]
    if risk_name == "整体":
        curr_unsale = df_curr[df_curr["滞销风险等级_FBA"].isin(risk_list)]
        prev_unsale = df_prev[df_prev["滞销风险等级_FBA"].isin(risk_list)]

        sku_c = df_curr["MSKU"].nunique()
        sku_p = df_prev["MSKU"].nunique()
        sku_diff = sku_c - sku_p

        stk_c = float(df_curr["FBA+AWD+在途库存"].sum())
        stk_p = float(df_prev["FBA+AWD+在途库存"].sum())
        stk_diff = stk_c - stk_p

        amt_c = float(df_curr["FBA金额"].sum())
        amt_p = float(df_prev["FBA金额"].sum())
        amt_diff = amt_c - amt_p

        u_stk_c = float(curr_unsale["FBA滞销数量_仅FBA"].sum())
        u_stk_p = float(prev_unsale["FBA滞销数量_仅FBA"].sum())
        u_stk_diff = u_stk_c - u_stk_p
        pct_stk = u_stk_c / stk_c if stk_c != 0 else 0

        u_amt_c = float(curr_unsale["FBA滞销金额_仅FBA"].sum())
        u_amt_p = float(prev_unsale["FBA滞销金额_仅FBA"].sum())
        u_amt_diff = u_amt_c - u_amt_p
        pct_amt = u_amt_c / amt_c if amt_c != 0 else 0
    else:
        c = df_curr[df_curr["滞销风险等级_FBA"] == risk_name]
        p = df_prev[df_prev["滞销风险等级_FBA"] == risk_name]

        sku_c = c["MSKU"].nunique()
        sku_p = p["MSKU"].nunique()
        sku_diff = sku_c - sku_p

        stk_c = float(c["FBA+AWD+在途库存"].sum())
        stk_p = float(p["FBA+AWD+在途库存"].sum())
        stk_diff = stk_c - stk_p

        amt_c = float(c["FBA金额"].sum())
        amt_p = float(p["FBA金额"].sum())
        amt_diff = amt_c - amt_p

        u_stk_c = float(c["FBA滞销数量_仅FBA"].sum())
        u_stk_p = float(p["FBA滞销数量_仅FBA"].sum())
        u_stk_diff = u_stk_c - u_stk_p
        pct_stk = u_stk_c / all_unsale_stock_fba if all_unsale_stock_fba != 0 else 0

        u_amt_c = float(c["FBA滞销金额_仅FBA"].sum())
        u_amt_p = float(p["FBA滞销金额_仅FBA"].sum())
        u_amt_diff = u_amt_c - u_amt_p
        pct_amt = u_amt_c / all_unsale_amt_fba if all_unsale_amt_fba != 0 else 0
    return {
        "sku_curr": sku_c, "sku_prev": sku_p, "sku_diff": sku_diff,
        "stock_curr": stk_c, "stock_prev": stk_p, "stock_diff": stk_diff,
        "amt_curr": amt_c, "amt_prev": amt_p, "amt_diff": amt_diff,
        "unsale_stock_curr": u_stk_c, "unsale_stock_prev": u_stk_p, "unsale_stock_diff": u_stk_diff, "unsale_stock_pct": pct_stk,
        "unsale_amt_curr": u_amt_c, "unsale_amt_prev": u_amt_p, "unsale_amt_diff": u_amt_diff, "unsale_amt_pct": pct_amt
    }

# ===================== 输出 =====================
# ===================== 输出 =====================
st.divider()
st.subheader("📦 整体滞销情况概览（总库存口径）")
# 先计算全局滞销分母
metrics_all_total = calc_metrics(df_curr, df_prev, "整体", 0, 0)
all_unsale_stock_total = metrics_all_total["unsale_stock_curr"]
all_unsale_amt_total = metrics_all_total["unsale_amt_curr"]

cols = st.columns(5)
risk_list = ["整体", "健康", "低滞销风险", "中滞销风险", "高滞销风险"]
for i, t in enumerate(risk_list):
    # 补齐5个参数：df_curr, df_prev, t, all_unsale_stock_total, all_unsale_amt_total
    m = calc_metrics(df_curr, df_prev, t, all_unsale_stock_total, all_unsale_amt_total)
    with cols[i]:
        render_card_compact(t, m)

# FBA卡片区域
st.divider()
st.subheader("🌎 FBA+AWD+在途库存 滞销概览（海外优先清货）")
metrics_all_fba = calc_metrics_fba(df_curr, df_prev, "整体", 0, 0)
all_unsale_stock_fba = metrics_all_fba["unsale_stock_curr"]
all_unsale_amt_fba = metrics_all_fba["unsale_amt_curr"]

cols_fba = st.columns(5)
for i, t in enumerate(["整体", "健康", "低滞销风险", "中滞销风险", "高滞销风险"]):
    # 补齐5个入参
    m = calc_metrics_fba(df_curr, df_prev, t, all_unsale_stock_fba, all_unsale_amt_fba)
    with cols_fba[i]:
        render_card_compact(t, m)

# ===================== 【最终完整版明细表】所有字段补齐，不缺项 =====================
with st.expander("📋 查看每个MSKU计算明细（总库存 + FBA双口径统一表）"):
    show_cols = [
        # 基础信息
        "店铺", "MSKU", "品名", "是否年份", "时间",

        # 库存数量（总库存 + FBA + 本地）
        "FBA+AWD+在途库存", "本地库存", "总库存",

        # 运营指标
        "日均","7天日均","14天日均","28天日均","采购成本", "头程费用",
        # ========== FBA 独立口径（完整补齐） ==========
        "周转天数_FBA",
        "预计FBA用完时间",
        "滞销风险等级_FBA",
        "FBA滞销数量_仅FBA",
        "FBA金额",
        "FBA滞销金额_仅FBA",  # FBA口径滞销金额

        # ========== 总库存 口径 ==========
        "周转天数",
        "预计总库存用完时间",
        "滞销风险等级",
        "总滞销库存",
        "总库存金额",
        "总滞销金额",

        # ========== 总库存下的明细拆分（FBA部分 + 本地部分） ==========
        "FBA+AWD+在途滞销数量",
        "FBA滞销金额",  # 总库存风险下的FBA滞销金额
        "本地滞销数量",
        "本地金额",
        "本地滞销金额"
    ]
    st.dataframe(df_curr[show_cols], use_container_width=True)



# ===================== 图表：3行2列 双口径对比（数据100%对齐版） =====================
st.divider()
st.subheader("📊 整体滞销金额 & 数量 & SKU 拆解分析")

import plotly.graph_objects as go

# 1. 统一计算两套数据
risk_list = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]

# 总库存口径
data_total = []
for r in risk_list:
    m = calc_metrics(df_curr, df_prev, r)
    data_total.append({
        "风险等级": r,
        "SKU数": m["sku_curr"],
        "SKU_prev": m["sku_prev"],
        "SKU_diff": m["sku_diff"],
        "总金额": m["amt_curr"],
        "amt_prev": m["amt_prev"],
        "amt_diff": m["amt_diff"],
        "总库存": m["stock_curr"],
        "stock_prev": m["stock_prev"],
        "stock_diff": m["stock_diff"],
        "滞销金额": m["unsale_amt_curr"],
        "unsale_amt_prev": m["unsale_amt_prev"],
        "unsale_amt_diff": m["unsale_amt_diff"],
        "滞销库存": m["unsale_stock_curr"],
        "unsale_stock_prev": m["unsale_stock_prev"],
        "unsale_stock_diff": m["unsale_stock_diff"],
    })
df_total = pd.DataFrame(data_total)

# FBA口径
data_fba = []
for r in risk_list:
    m = calc_metrics_fba(df_curr, df_prev, r)
    data_fba.append({
        "风险等级": r,
        "SKU数": m["sku_curr"],
        "SKU_prev": m["sku_prev"],
        "SKU_diff": m["sku_diff"],
        "总金额": m["amt_curr"],
        "amt_prev": m["amt_prev"],
        "amt_diff": m["amt_diff"],
        "总库存": m["stock_curr"],
        "stock_prev": m["stock_prev"],
        "stock_diff": m["stock_diff"],
        "滞销金额": m["unsale_amt_curr"],
        "unsale_amt_prev": m["unsale_amt_prev"],
        "unsale_amt_diff": m["unsale_amt_diff"],
        "滞销库存": m["unsale_stock_curr"],
        "unsale_stock_prev": m["unsale_stock_prev"],
        "unsale_stock_diff": m["unsale_stock_diff"],
    })
df_fba = pd.DataFrame(data_fba)

# 格式化环比颜色
def fmt_val_html(val):
    if val > 0:
        return f'<span style="color:#d32f2f">↑ +{val:,.0f}</span>'
    elif val < 0:
        return f'<span style="color:#388e3c">↓ {val:,.0f}</span>'
    else:
        return '<span style="color:#666">持平</span>'

# 🔥 最终修复：饼图数据和表格100%对齐
def create_double_pie(df, total_col, unsold_col):
    # 1. 直接用我们计算好的总金额和滞销金额
    total_val = df[total_col].sum()
    unsold_val = df[df["风险等级"] != "健康"][unsold_col].sum()
    not_unsold_val = total_val - unsold_val

    fig = go.Figure()
    # 左侧饼：不滞销 / 滞销（和表格数据完全一致）
    fig.add_trace(go.Pie(
        labels=["不滞销", "滞销"],
        values=[not_unsold_val, unsold_val],
        domain=dict(x=[0, 0.65], y=[0, 1]),
        marker=dict(colors=["#e8f5e9", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    # 右侧细分饼：低/中/高风险
    sub_df = df[df["风险等级"].isin(["低滞销风险", "中滞销风险", "高滞销风险"])]
    fig.add_trace(go.Pie(
        labels=sub_df["风险等级"],
        values=sub_df[unsold_col],
        domain=dict(x=[0.72, 1], y=[0.2, 0.8]),
        marker=dict(colors=["#fff8e1", "#ffebee", "#ffcdd2"], line=dict(width=1)),
        textinfo="label+value+percent",
        texttemplate="%{label}<br>%{value:,.0f}<br>%{percent:.1%}",
        sort=False, direction="clockwise"
    ))
    fig.update_layout(height=400, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    return fig

# ---------------------- 第1行：滞销金额 ----------------------
st.markdown("### 💰 滞销金额对比")
# 计算数据
total_amt_t = df_total["总金额"].sum()
unsold_amt_t = df_total[df_total["风险等级"] != "健康"]["滞销金额"].sum()
low_amt_t = df_total[df_total["风险等级"] == "低滞销风险"]["滞销金额"].iloc[0]
mid_amt_t = df_total[df_total["风险等级"] == "中滞销风险"]["滞销金额"].iloc[0]
high_amt_t = df_total[df_total["风险等级"] == "高滞销风险"]["滞销金额"].iloc[0]

total_amt_f = df_fba["总金额"].sum()
unsold_amt_f = df_fba[df_fba["风险等级"] != "健康"]["滞销金额"].sum()
low_amt_f = df_fba[df_fba["风险等级"] == "低滞销风险"]["滞销金额"].iloc[0]
mid_amt_f = df_fba[df_fba["风险等级"] == "中滞销风险"]["滞销金额"].iloc[0]
high_amt_f = df_fba[df_fba["风险等级"] == "高滞销风险"]["滞销金额"].iloc[0]

# 构建HTML表格
html_table = f"""
<style>
table {{width:100%;border-collapse:collapse;margin:10px 0;}}
th, td {{border:1px solid #ddd;padding:8px;text-align:left;}}
th {{background-color:#f2f2f2;}}
</style>
<table>
  <tr>
    <th>指标分类</th>
    <th>总库存口径</th>
    <th>FBA+AWD+在途口径</th>
  </tr>
  <tr>
    <td>总库存金额</td>
    <td>{total_amt_t:,.0f} 元 {fmt_val_html(df_total["amt_diff"].sum())}</td>
    <td>{total_amt_f:,.0f} 元 {fmt_val_html(df_fba["amt_diff"].sum())}</td>
  </tr>
  <tr>
    <td>滞销总金额(占整体)</td>
    <td>{unsold_amt_t:,.0f} 元 ({unsold_amt_t/total_amt_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] != "健康"]["unsale_amt_diff"].sum())}</td>
    <td>{unsold_amt_f:,.0f} 元 ({unsold_amt_f/total_amt_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] != "健康"]["unsale_amt_diff"].sum())}</td>
  </tr>
  <tr>
    <td>高滞销风险(占滞销)</td>
    <td>{high_amt_t:,.0f} 元 ({high_amt_t/unsold_amt_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "高滞销风险"]["unsale_amt_diff"].iloc[0])}</td>
    <td>{high_amt_f:,.0f} 元 ({high_amt_f/unsold_amt_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "高滞销风险"]["unsale_amt_diff"].iloc[0])}</td>
  </tr>
  <tr>
    <td>中滞销风险(占滞销)</td>
    <td>{mid_amt_t:,.0f} 元 ({mid_amt_t/unsold_amt_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "中滞销风险"]["unsale_amt_diff"].iloc[0])}</td>
    <td>{mid_amt_f:,.0f} 元 ({mid_amt_f/unsold_amt_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "中滞销风险"]["unsale_amt_diff"].iloc[0])}</td>
  </tr>
  <tr>
    <td>低滞销风险(占滞销)</td>
    <td>{low_amt_t:,.0f} 元 ({low_amt_t/unsold_amt_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "低滞销风险"]["unsale_amt_diff"].iloc[0])}</td>
    <td>{low_amt_f:,.0f} 元 ({low_amt_f/unsold_amt_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "低滞销风险"]["unsale_amt_diff"].iloc[0])}</td>
  </tr>
</table>
"""
st.markdown(html_table, unsafe_allow_html=True)

# 双饼图（现在和表格数据100%对齐）
c1, c2 = st.columns(2)
with c1:
    st.caption("总库存口径")
    fig_amt_t = create_double_pie(df_total, "总金额", "滞销金额")
    st.plotly_chart(fig_amt_t, use_container_width=True)
with c2:
    st.caption("FBA+AWD+在途口径")
    fig_amt_f = create_double_pie(df_fba, "总金额", "滞销金额")
    st.plotly_chart(fig_amt_f, use_container_width=True)

st.divider()

# ---------------------- 第2行：滞销数量 ----------------------
st.markdown("### 📦 滞销数量对比")
# 计算数据
total_stk_t = df_total["总库存"].sum()
unsold_stk_t = df_total[df_total["风险等级"] != "健康"]["滞销库存"].sum()
low_stk_t = df_total[df_total["风险等级"] == "低滞销风险"]["滞销库存"].iloc[0]
mid_stk_t = df_total[df_total["风险等级"] == "中滞销风险"]["滞销库存"].iloc[0]
high_stk_t = df_total[df_total["风险等级"] == "高滞销风险"]["滞销库存"].iloc[0]

total_stk_f = df_fba["总库存"].sum()
unsold_stk_f = df_fba[df_fba["风险等级"] != "健康"]["滞销库存"].sum()
low_stk_f = df_fba[df_fba["风险等级"] == "低滞销风险"]["滞销库存"].iloc[0]
mid_stk_f = df_fba[df_fba["风险等级"] == "中滞销风险"]["滞销库存"].iloc[0]
high_stk_f = df_fba[df_fba["风险等级"] == "高滞销风险"]["滞销库存"].iloc[0]

# 构建HTML表格
html_table_stk = f"""
<style>
table {{width:100%;border-collapse:collapse;margin:10px 0;}}
th, td {{border:1px solid #ddd;padding:8px;text-align:left;}}
th {{background-color:#f2f2f2;}}
</style>
<table>
  <tr>
    <th>指标分类</th>
    <th>总库存口径</th>
    <th>FBA+AWD+在途口径</th>
  </tr>
  <tr>
    <td>总库存数量</td>
    <td>{total_stk_t:,.0f} 件 {fmt_val_html(df_total["stock_diff"].sum())}</td>
    <td>{total_stk_f:,.0f} 件 {fmt_val_html(df_fba["stock_diff"].sum())}</td>
  </tr>
  <tr>
    <td>滞销总数量(占整体)</td>
    <td>{unsold_stk_t:,.0f} 件 ({unsold_stk_t/total_stk_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] != "健康"]["unsale_stock_diff"].sum())}</td>
    <td>{unsold_stk_f:,.0f} 件 ({unsold_stk_f/total_stk_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] != "健康"]["unsale_stock_diff"].sum())}</td>
  </tr>
  <tr>
    <td>高滞销风险(占滞销)</td>
    <td>{high_stk_t:,.0f} 件 ({high_stk_t/unsold_stk_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "高滞销风险"]["unsale_stock_diff"].iloc[0])}</td>
    <td>{high_stk_f:,.0f} 件 ({high_stk_f/unsold_stk_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "高滞销风险"]["unsale_stock_diff"].iloc[0])}</td>
  </tr>
  <tr>
    <td>中滞销风险(占滞销)</td>
    <td>{mid_stk_t:,.0f} 件 ({mid_stk_t/unsold_stk_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "中滞销风险"]["unsale_stock_diff"].iloc[0])}</td>
    <td>{mid_stk_f:,.0f} 件 ({mid_stk_f/unsold_stk_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "中滞销风险"]["unsale_stock_diff"].iloc[0])}</td>
  </tr>
  <tr>
    <td>低滞销风险(占滞销)</td>
    <td>{low_stk_t:,.0f} 件 ({low_stk_t/unsold_stk_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "低滞销风险"]["unsale_stock_diff"].iloc[0])}</td>
    <td>{low_stk_f:,.0f} 件 ({low_stk_f/unsold_stk_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "低滞销风险"]["unsale_stock_diff"].iloc[0])}</td>
  </tr>
</table>
"""
st.markdown(html_table_stk, unsafe_allow_html=True)

# 双饼图
c3, c4 = st.columns(2)
with c3:
    st.caption("总库存口径")
    fig_stk_t = create_double_pie(df_total, "总库存", "滞销库存")
    st.plotly_chart(fig_stk_t, use_container_width=True)
with c4:
    st.caption("FBA+AWD+在途口径")
    fig_stk_f = create_double_pie(df_fba, "总库存", "滞销库存")
    st.plotly_chart(fig_stk_f, use_container_width=True)

st.divider()

# ---------------------- 第3行：滞销SKU ----------------------
st.markdown("### 📊 滞销SKU对比")
# 计算数据
total_sku_t = df_total["SKU数"].sum()
unsold_sku_t = df_total[df_total["风险等级"] != "健康"]["SKU数"].sum()
low_sku_t = df_total[df_total["风险等级"] == "低滞销风险"]["SKU数"].iloc[0]
mid_sku_t = df_total[df_total["风险等级"] == "中滞销风险"]["SKU数"].iloc[0]
high_sku_t = df_total[df_total["风险等级"] == "高滞销风险"]["SKU数"].iloc[0]

total_sku_f = df_fba["SKU数"].sum()
unsold_sku_f = df_fba[df_fba["风险等级"] != "健康"]["SKU数"].sum()
low_sku_f = df_fba[df_fba["风险等级"] == "低滞销风险"]["SKU数"].iloc[0]
mid_sku_f = df_fba[df_fba["风险等级"] == "中滞销风险"]["SKU数"].iloc[0]
high_sku_f = df_fba[df_fba["风险等级"] == "高滞销风险"]["SKU数"].iloc[0]

# 构建HTML表格
html_table_sku = f"""
<style>
table {{width:100%;border-collapse:collapse;margin:10px 0;}}
th, td {{border:1px solid #ddd;padding:8px;text-align:left;}}
th {{background-color:#f2f2f2;}}
</style>
<table>
  <tr>
    <th>指标分类</th>
    <th>总库存口径</th>
    <th>FBA+AWD+在途口径</th>
  </tr>
  <tr>
    <td>总SKU数量</td>
    <td>{total_sku_t} 个 {fmt_val_html(df_total["SKU_diff"].sum())}</td>
    <td>{total_sku_f} 个 {fmt_val_html(df_fba["SKU_diff"].sum())}</td>
  </tr>
  <tr>
    <td>滞销总SKU(占整体)</td>
    <td>{unsold_sku_t} 个 ({unsold_sku_t/total_sku_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] != "健康"]["SKU_diff"].sum())}</td>
    <td>{unsold_sku_f} 个 ({unsold_sku_f/total_sku_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] != "健康"]["SKU_diff"].sum())}</td>
  </tr>
  <tr>
    <td>高滞销风险(占滞销)</td>
    <td>{high_sku_t} 个 ({high_sku_t/unsold_sku_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "高滞销风险"]["SKU_diff"].iloc[0])}</td>
    <td>{high_sku_f} 个 ({high_sku_f/unsold_sku_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "高滞销风险"]["SKU_diff"].iloc[0])}</td>
  </tr>
  <tr>
    <td>中滞销风险(占滞销)</td>
    <td>{mid_sku_t} 个 ({mid_sku_t/unsold_sku_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "中滞销风险"]["SKU_diff"].iloc[0])}</td>
    <td>{mid_sku_f} 个 ({mid_sku_f/unsold_sku_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "中滞销风险"]["SKU_diff"].iloc[0])}</td>
  </tr>
  <tr>
    <td>低滞销风险(占滞销)</td>
    <td>{low_sku_t} 个 ({low_sku_t/unsold_sku_t:.1%}) {fmt_val_html(df_total[df_total["风险等级"] == "低滞销风险"]["SKU_diff"].iloc[0])}</td>
    <td>{low_sku_f} 个 ({low_sku_f/unsold_sku_f:.1%}) {fmt_val_html(df_fba[df_fba["风险等级"] == "低滞销风险"]["SKU_diff"].iloc[0])}</td>
  </tr>
</table>
"""
st.markdown(html_table_sku, unsafe_allow_html=True)

# 双饼图
c5, c6 = st.columns(2)
with c5:
    st.caption("总库存口径")
    fig_sku_t = create_double_pie(df_total, "SKU数", "SKU数")
    st.plotly_chart(fig_sku_t, use_container_width=True)
with c6:
    st.caption("FBA+AWD+在途口径")
    fig_sku_f = create_double_pie(df_fba, "SKU数", "SKU数")
    st.plotly_chart(fig_sku_f, use_container_width=True)



# ===================== 年份品 / 非年份品 滞销拆分占比分析（双口径对比版） =====================
# ===================== 年份品 / 非年份品 滞销结构（完整表格版 + 一行六列饼图） =====================
st.divider()
st.subheader("📅 年份品 & 非年份品 滞销结构拆分")

import plotly.express as px

# 1. 风险等级定义
risk_list = ["低滞销风险", "中滞销风险", "高滞销风险"]

# 2. 统计函数（支持总库存/FBA口径、当月/上月）
def stat_total(df):
    year = df[df["是否年份"] == "是"]
    noyear = df[df["是否年份"] == "否"]
    y_risk = year[year["滞销风险等级"].isin(risk_list)]
    ny_risk = noyear[noyear["滞销风险等级"].isin(risk_list)]
    return (
        y_risk["MSKU"].nunique(),
        y_risk["总滞销库存"].sum(),
        y_risk["总滞销金额"].sum(),
        ny_risk["MSKU"].nunique(),
        ny_risk["总滞销库存"].sum(),
        ny_risk["总滞销金额"].sum()
    )

def stat_fba(df):
    year = df[df["是否年份"] == "是"]
    noyear = df[df["是否年份"] == "否"]
    y_risk = year[year["滞销风险等级_FBA"].isin(risk_list)]
    ny_risk = noyear[noyear["滞销风险等级_FBA"].isin(risk_list)]
    return (
        y_risk["MSKU"].nunique(),
        y_risk["FBA滞销数量_仅FBA"].sum(),
        y_risk["FBA滞销金额_仅FBA"].sum(),
        ny_risk["MSKU"].nunique(),
        ny_risk["FBA滞销数量_仅FBA"].sum(),
        ny_risk["FBA滞销金额_仅FBA"].sum()
    )

# 3. 当月/上月数据
# 总库存
y1_sku, y1_qty, y1_amt, ny1_sku, ny1_qty, ny1_amt = stat_total(df_curr)
total1_sku = y1_sku + ny1_sku
total1_qty = y1_qty + ny1_qty
total1_amt = y1_amt + ny1_amt

y1p_sku, y1p_qty, y1p_amt, ny1p_sku, ny1p_qty, ny1p_amt = stat_total(df_prev)
total1p_sku = y1p_sku + ny1p_sku
total1p_qty = y1p_qty + ny1p_qty
total1p_amt = y1p_amt + ny1p_amt

# FBA
y2_sku, y2_qty, y2_amt, ny2_sku, ny2_qty, ny2_amt = stat_fba(df_curr)
total2_sku = y2_sku + ny2_sku
total2_qty = y2_qty + ny2_qty
total2_amt = y2_amt + ny2_amt

y2p_sku, y2p_qty, y2p_amt, ny2p_sku, ny2p_qty, ny2p_amt = stat_fba(df_prev)
total2p_sku = y2p_sku + ny2p_sku
total2p_qty = y2p_qty + ny2p_qty
total2p_amt = y2p_amt + ny2p_amt

# 4. 环比差值
def diff(a, b): return round(a) - round(b)

d1_sku = diff(total1_sku, total1p_sku)
d1_qty = diff(total1_qty, total1p_qty)
d1_amt = diff(total1_amt, total1p_amt)
d1y_sku = diff(y1_sku, y1p_sku)
d1y_qty = diff(y1_qty, y1p_qty)
d1y_amt = diff(y1_amt, y1p_amt)
d1n_sku = diff(ny1_sku, ny1p_sku)
d1n_qty = diff(ny1_qty, ny1p_qty)
d1n_amt = diff(ny1_amt, ny1p_amt)

d2_sku = diff(total2_sku, total2p_sku)
d2_qty = diff(total2_qty, total2p_qty)
d2_amt = diff(total2_amt, total2p_amt)
d2y_sku = diff(y2_sku, y2p_sku)
d2y_qty = diff(y2_qty, y2p_qty)
d2y_amt = diff(y2_amt, y2p_amt)
d2n_sku = diff(ny2_sku, ny2p_sku)
d2n_qty = diff(ny2_qty, ny2p_qty)
d2n_amt = diff(ny2_amt, ny2p_amt)

# 格式化工具
def pct(a, b): return f"{a/b*100:.2f}%" if b > 0 else "0.00%"
def color_num(v):
    if v > 0: return f'<span style="color:#d32f2f">↑ +{v:,}</span>'
    elif v < 0: return f'<span style="color:#388e3c">↓ {v:,}</span>'
    else: return "—"

# 数值统一转整数
total1_sku = round(total1_sku)
y1_sku = round(y1_sku)
ny1_sku = round(ny1_sku)
total1_qty = round(total1_qty)
y1_qty = round(y1_qty)
ny1_qty = round(ny1_qty)
total1_amt = round(total1_amt)
y1_amt = round(y1_amt)
ny1_amt = round(ny1_amt)

total2_sku = round(total2_sku)
y2_sku = round(y2_sku)
ny2_sku = round(ny2_sku)
total2_qty = round(total2_qty)
y2_qty = round(y2_qty)
ny2_qty = round(ny2_qty)
total2_amt = round(total2_amt)
y2_amt = round(y2_amt)
ny2_amt = round(ny2_amt)

# ===================== 【完整表格：细分年份/非年份】 =====================
st.markdown("### 📊 滞销结构对比（按年份/非年份拆分）")
html_table = f"""
<style>
table {{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px;}}
th, td {{border:1px solid #ddd;padding:8px;text-align:left;}}
th {{background-color:#f2f2f2;}}
</style>
<table>
  <tr>
    <th>指标分类</th>
    <th>总库存口径</th>
    <th>FBA+AWD+在途口径</th>
  </tr>
  <!-- SKU部分 -->
  <tr>
    <td>滞销SKU总数</td>
    <td>{total1_sku:,} 个 {color_num(d1_sku)}</td>
    <td>{total2_sku:,} 个 {color_num(d2_sku)}</td>
  </tr>
  <tr>
    <td style="padding-left:20px;">年份品SKU（占比）</td>
    <td>{y1_sku:,} 个（{pct(y1_sku, total1_sku)}）{color_num(d1y_sku)}</td>
    <td>{y2_sku:,} 个（{pct(y2_sku, total2_sku)}）{color_num(d2y_sku)}</td>
  </tr>
  <tr>
    <td style="padding-left:20px;">非年份品SKU（占比）</td>
    <td>{ny1_sku:,} 个（{pct(ny1_sku, total1_sku)}）{color_num(d1n_sku)}</td>
    <td>{ny2_sku:,} 个（{pct(ny2_sku, total2_sku)}）{color_num(d2n_sku)}</td>
  </tr>
  <!-- 数量部分 -->
  <tr>
    <td>滞销总数量</td>
    <td>{total1_qty:,} 件 {color_num(d1_qty)}</td>
    <td>{total2_qty:,} 件 {color_num(d2_qty)}</td>
  </tr>
  <tr>
    <td style="padding-left:20px;">年份品数量（占比）</td>
    <td>{y1_qty:,} 件（{pct(y1_qty, total1_qty)}）{color_num(d1y_qty)}</td>
    <td>{y2_qty:,} 件（{pct(y2_qty, total2_qty)}）{color_num(d2y_qty)}</td>
  </tr>
  <tr>
    <td style="padding-left:20px;">非年份品数量（占比）</td>
    <td>{ny1_qty:,} 件（{pct(ny1_qty, total1_qty)}）{color_num(d1n_qty)}</td>
    <td>{ny2_qty:,} 件（{pct(ny2_qty, total2_qty)}）{color_num(d2n_qty)}</td>
  </tr>
  <!-- 金额部分 -->
  <tr>
    <td>滞销总金额</td>
    <td>{total1_amt:,} 元 {color_num(d1_amt)}</td>
    <td>{total2_amt:,} 元 {color_num(d2_amt)}</td>
  </tr>
  <tr>
    <td style="padding-left:20px;">年份品金额（占比）</td>
    <td>{y1_amt:,} 元（{pct(y1_amt, total1_amt)}）{color_num(d1y_amt)}</td>
    <td>{y2_amt:,} 元（{pct(y2_amt, total2_amt)}）{color_num(d2y_amt)}</td>
  </tr>
  <tr>
    <td style="padding-left:20px;">非年份品金额（占比）</td>
    <td>{ny1_amt:,} 元（{pct(ny1_amt, total1_amt)}）{color_num(d1n_amt)}</td>
    <td>{ny2_amt:,} 元（{pct(ny2_amt, total2_amt)}）{color_num(d2n_amt)}</td>
  </tr>
</table>
"""
st.markdown(html_table, unsafe_allow_html=True)

# ===================== 【饼图：一行六列放大版】 =====================
st.markdown("### 🥧 占比饼图对比（总库存 ↔ FBA+AWD+在途）")
cols = st.columns(6, gap="small")
colors = ["#a6c9ff", "#0066cc"]
height = 300

# 总库存组
with cols[0]:
    fig = px.pie(names=["年份品", "非年份品"], values=[y1_sku, ny1_sku], title="总库存 - SKU占比", color_discrete_sequence=colors)
    fig.update_layout(height=height, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)
with cols[1]:
    fig = px.pie(names=["年份品", "非年份品"], values=[y1_qty, ny1_qty], title="总库存 - 数量占比", color_discrete_sequence=colors)
    fig.update_layout(height=height, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)
with cols[2]:
    fig = px.pie(names=["年份品", "非年份品"], values=[y1_amt, ny1_amt], title="总库存 - 金额占比", color_discrete_sequence=colors)
    fig.update_layout(height=height, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

# FBA组
with cols[3]:
    fig = px.pie(names=["年份品", "非年份品"], values=[y2_sku, ny2_sku], title="FBA - SKU占比", color_discrete_sequence=colors)
    fig.update_layout(height=height, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)
with cols[4]:
    fig = px.pie(names=["年份品", "非年份品"], values=[y2_qty, ny2_qty], title="FBA - 数量占比", color_discrete_sequence=colors)
    fig.update_layout(height=height, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)
with cols[5]:
    fig = px.pie(names=["年份品", "非年份品"], values=[y2_amt, ny2_amt], title="FBA - 金额占比", color_discrete_sequence=colors)
    fig.update_layout(height=height, showlegend=False, margin=dict(t=40, b=10, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("📊 滞销拆解（含环比+占比 | 按口径/年份拆分）")

RISK_LIST = ["健康", "低滞销风险", "中滞销风险", "高滞销风险"]

# 计算函数
def get_segment_metrics(df_curr, df_prev, risk_col, stock_col, amt_col, unsold_stock_col, unsold_amt_col):
    res = {}
    res["curr_total_sku"] = df_curr["MSKU"].nunique()
    res["prev_total_sku"] = df_prev["MSKU"].nunique()
    res["diff_total_sku"] = res["curr_total_sku"] - res["prev_total_sku"]

    res["curr_total_stock"] = round(df_curr[stock_col].sum())
    res["prev_total_stock"] = round(df_prev[stock_col].sum())
    res["diff_total_stock"] = res["curr_total_stock"] - res["prev_total_stock"]

    res["curr_total_amt"] = round(df_curr[amt_col].sum())
    res["prev_total_amt"] = round(df_prev[amt_col].sum())
    res["diff_total_amt"] = res["curr_total_amt"] - res["prev_total_amt"]

    for r in RISK_LIST:
        dc = df_curr[df_curr[risk_col] == r]
        dp = df_prev[df_prev[risk_col] == r]

        res[f"{r}_sku_curr"] = dc["MSKU"].nunique()
        res[f"{r}_sku_prev"] = dp["MSKU"].nunique()
        res[f"{r}_sku_diff"] = res[f"{r}_sku_curr"] - res[f"{r}_sku_prev"]

        res[f"{r}_stock_curr"] = round(dc[stock_col].sum())
        res[f"{r}_stock_prev"] = round(dp[stock_col].sum())
        res[f"{r}_stock_diff"] = res[f"{r}_stock_curr"] - res[f"{r}_stock_prev"]

        res[f"{r}_amt_curr"] = round(dc[amt_col].sum())
        res[f"{r}_amt_prev"] = round(dp[amt_col].sum())
        res[f"{r}_amt_diff"] = res[f"{r}_amt_curr"] - res[f"{r}_amt_prev"]

        if r != "健康":
            res[f"{r}_unsold_stock_curr"] = round(dc[unsold_stock_col].sum())
            res[f"{r}_unsold_stock_prev"] = round(dp[unsold_stock_col].sum())
            res[f"{r}_unsold_stock_diff"] = res[f"{r}_unsold_stock_curr"] - res[f"{r}_unsold_stock_prev"]

            res[f"{r}_unsold_amt_curr"] = round(dc[unsold_amt_col].sum())
            res[f"{r}_unsold_amt_prev"] = round(dp[unsold_amt_col].sum())
            res[f"{r}_unsold_amt_diff"] = res[f"{r}_unsold_amt_curr"] - res[f"{r}_unsold_amt_prev"]
        else:
            res[f"{r}_unsold_stock_curr"] = 0
            res[f"{r}_unsold_stock_prev"] = 0
            res[f"{r}_unsold_stock_diff"] = 0
            res[f"{r}_unsold_amt_curr"] = 0
            res[f"{r}_unsold_amt_prev"] = 0
            res[f"{r}_unsold_amt_diff"] = 0

    unsold_risk = ["低滞销风险", "中滞销风险", "高滞销风险"]
    res["unsold_sku_curr"] = sum(res[f"{x}_sku_curr"] for x in unsold_risk)
    res["unsold_sku_prev"] = sum(res[f"{x}_sku_prev"] for x in unsold_risk)
    res["unsold_sku_diff"] = res["unsold_sku_curr"] - res["unsold_sku_prev"]

    res["unsold_stock_curr"] = sum(res[f"{x}_unsold_stock_curr"] for x in unsold_risk)
    res["unsold_stock_prev"] = sum(res[f"{x}_unsold_stock_prev"] for x in unsold_risk)
    res["unsold_stock_diff"] = res["unsold_stock_curr"] - res["unsold_stock_prev"]

    res["unsold_amt_curr"] = sum(res[f"{x}_unsold_amt_curr"] for x in unsold_risk)
    res["unsold_amt_prev"] = sum(res[f"{x}_unsold_amt_prev"] for x in unsold_risk)
    res["unsold_amt_diff"] = res["unsold_amt_curr"] - res["unsold_amt_prev"]

    res["pct_sku"] = res["unsold_sku_curr"] / res["curr_total_sku"] if res["curr_total_sku"] != 0 else 0
    res["pct_stock"] = res["unsold_stock_curr"] / res["curr_total_stock"] if res["curr_total_stock"] != 0 else 0
    res["pct_amt"] = res["unsold_amt_curr"] / res["curr_total_amt"] if res["curr_total_amt"] != 0 else 0

    for r in unsold_risk:
        res[f"{r}_pct_sku"] = res[f"{r}_sku_curr"] / res["unsold_sku_curr"] if res["unsold_sku_curr"] != 0 else 0
        res[f"{r}_pct_stock"] = res[f"{r}_unsold_stock_curr"] / res["unsold_stock_curr"] if res["unsold_stock_curr"] != 0 else 0
        res[f"{r}_pct_amt"] = res[f"{r}_unsold_amt_curr"] / res["unsold_amt_curr"] if res["unsold_amt_curr"] != 0 else 0

    return res

# 筛选数据
# 年份品
df_curr_year = df_curr[df_curr["是否年份"] == "是"].copy()
df_prev_year = df_prev[df_prev["是否年份"] == "是"].copy()

# 非年份品
df_curr_nonyear = df_curr[df_curr["是否年份"] == "否"].copy()
df_prev_nonyear = df_prev[df_prev["是否年份"] == "否"].copy()

# 计算指标
# 1. 总库存口径 - 年份品/非年份品
met_year_total = get_segment_metrics(
    df_curr_year, df_prev_year,
    risk_col="滞销风险等级",
    stock_col="总库存",
    amt_col="总库存金额",
    unsold_stock_col="总滞销库存",
    unsold_amt_col="总滞销金额"
)

met_nonyear_total = get_segment_metrics(
    df_curr_nonyear, df_prev_nonyear,
    risk_col="滞销风险等级",
    stock_col="总库存",
    amt_col="总库存金额",
    unsold_stock_col="总滞销库存",
    unsold_amt_col="总滞销金额"
)

# 2. FBA口径 - 年份品/非年份品
met_year_fba = get_segment_metrics(
    df_curr_year, df_prev_year,
    risk_col="滞销风险等级_FBA",
    stock_col="FBA+AWD+在途库存",
    amt_col="FBA金额",
    unsold_stock_col="FBA滞销数量_仅FBA",
    unsold_amt_col="FBA滞销金额_仅FBA"
)

met_nonyear_fba = get_segment_metrics(
    df_curr_nonyear, df_prev_nonyear,
    risk_col="滞销风险等级_FBA",
    stock_col="FBA+AWD+在途库存",
    amt_col="FBA金额",
    unsold_stock_col="FBA滞销数量_仅FBA",
    unsold_amt_col="FBA滞销金额_仅FBA"
)

# 格式化单元格并存储差值，方便后续上色
def format_cell(val, diff, pct=None, unit=""):
    arrow = "↑" if diff >= 0 else "↓"
    diff_str = f"{arrow}{diff:+d}".replace("+", "")
    if pct is not None:
        text = f"{val:,}{unit} ({pct:.1%}) {diff_str}"
    else:
        text = f"{val:,}{unit} {diff_str}"
    return text, diff  # 同时返回文本和差值

row_list = [
    "全部",
    "滞销合计(低+中+高)",
    "健康",
    "低滞销风险",
    "中滞销风险",
    "高滞销风险"
]

# 构建表格：SKU/数量/金额，每块里区分年份品/非年份品
def build_table(m_year, m_nonyear, unit=""):
    rows = []
    for lab in row_list:
        if lab == "全部":
            if unit == " 个":
                y_text, y_diff = format_cell(m_year["curr_total_sku"], m_year["diff_total_sku"], unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear["curr_total_sku"], m_nonyear["diff_total_sku"], unit=unit)
            elif unit == " 件":
                y_text, y_diff = format_cell(m_year["curr_total_stock"], m_year["diff_total_stock"], unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear["curr_total_stock"], m_nonyear["diff_total_stock"], unit=unit)
            else:
                y_text, y_diff = format_cell(m_year["curr_total_amt"], m_year["diff_total_amt"], unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear["curr_total_amt"], m_nonyear["diff_total_amt"], unit=unit)

        elif lab == "滞销合计(低+中+高)":
            if unit == " 个":
                y_text, y_diff = format_cell(m_year["unsold_sku_curr"], m_year["unsold_sku_diff"], m_year["pct_sku"], unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear["unsold_sku_curr"], m_nonyear["unsold_sku_diff"], m_nonyear["pct_sku"], unit=unit)
            elif unit == " 件":
                y_text, y_diff = format_cell(m_year["unsold_stock_curr"], m_year["unsold_stock_diff"], m_year["pct_stock"], unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear["unsold_stock_curr"], m_nonyear["unsold_stock_diff"], m_nonyear["pct_stock"], unit=unit)
            else:
                y_text, y_diff = format_cell(m_year["unsold_amt_curr"], m_year["unsold_amt_diff"], m_year["pct_amt"], unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear["unsold_amt_curr"], m_nonyear["unsold_amt_diff"], m_nonyear["pct_amt"], unit=unit)

        else:
            if unit == " 个":
                y_text, y_diff = format_cell(m_year[f"{lab}_sku_curr"], m_year[f"{lab}_sku_diff"], m_year[f"{lab}_pct_sku"] if lab!="健康" else None, unit=unit)
                ny_text, ny_diff = format_cell(m_nonyear[f"{lab}_sku_curr"], m_nonyear[f"{lab}_sku_diff"], m_nonyear[f"{lab}_pct_sku"] if lab!="健康" else None, unit=unit)
            elif unit == " 件":
                val_y = m_year[f"{lab}_unsold_stock_curr"] if lab!="健康" else m_year[f"{lab}_stock_curr"]
                diff_y = m_year[f"{lab}_unsold_stock_diff"] if lab!="健康" else m_year[f"{lab}_stock_diff"]
                pct_y = m_year[f"{lab}_pct_stock"] if lab!="健康" else None

                val_ny = m_nonyear[f"{lab}_unsold_stock_curr"] if lab!="健康" else m_nonyear[f"{lab}_stock_curr"]
                diff_ny = m_nonyear[f"{lab}_unsold_stock_diff"] if lab!="健康" else m_nonyear[f"{lab}_stock_diff"]
                pct_ny = m_nonyear[f"{lab}_pct_stock"] if lab!="健康" else None

                y_text, y_diff = format_cell(val_y, diff_y, pct_y, unit=unit)
                ny_text, ny_diff = format_cell(val_ny, diff_ny, pct_ny, unit=unit)
            else:
                val_y = m_year[f"{lab}_unsold_amt_curr"] if lab!="健康" else m_year[f"{lab}_amt_curr"]
                diff_y = m_year[f"{lab}_unsold_amt_diff"] if lab!="健康" else m_year[f"{lab}_amt_diff"]
                pct_y = m_year[f"{lab}_pct_amt"] if lab!="健康" else None

                val_ny = m_nonyear[f"{lab}_unsold_amt_curr"] if lab!="健康" else m_nonyear[f"{lab}_amt_curr"]
                diff_ny = m_nonyear[f"{lab}_unsold_amt_diff"] if lab!="健康" else m_nonyear[f"{lab}_amt_diff"]
                pct_ny = m_nonyear[f"{lab}_pct_amt"] if lab!="健康" else None

                y_text, y_diff = format_cell(val_y, diff_y, pct_y, unit=unit)
                ny_text, ny_diff = format_cell(val_ny, diff_ny, pct_ny, unit=unit)

        rows.append({
            "分类": lab,
            "年份品": y_text,
            "年份品_diff": y_diff,
            "年份品_color": "red" if y_diff > 0 else "green" if y_diff < 0 else None,
            "非年份品": ny_text,
            "非年份品_diff": ny_diff,
            "非年份品_color": "red" if ny_diff > 0 else "green" if ny_diff < 0 else None
        })

    df = pd.DataFrame(rows)
    return df

# 生成表格（包含差值和颜色信息）
# 1. 总库存口径
df_sku_total = build_table(met_year_total, met_nonyear_total, unit=" 个")
df_stock_total = build_table(met_year_total, met_nonyear_total, unit=" 件")
df_amt_total = build_table(met_year_total, met_nonyear_total, unit=" 元")

# 2. FBA口径
df_sku_fba = build_table(met_year_fba, met_nonyear_fba, unit=" 个")
df_stock_fba = build_table(met_year_fba, met_nonyear_fba, unit=" 件")
df_amt_fba = build_table(met_year_fba, met_nonyear_fba, unit=" 元")

# 自定义颜色函数（优化版：差值为0不上色）
def color_text(val):
    if "↑0" in val or "↓0" in val:
        return ""  # 差值为0，保持默认黑色
    elif "↑" in val:
        return "color: red"
    elif "↓" in val:
        return "color: green"
    else:
        return ""

# 渲染带颜色的表格
def render_colored_df(df, title):
    st.markdown(title)
    display_df = df[["分类", "年份品", "非年份品"]].copy()
    st.dataframe(
        display_df.style.applymap(color_text, subset=["年份品", "非年份品"]),
        use_container_width=True,
        hide_index=True,
        height=320
    )

# 渲染页面：先总库存口径，再FBA口径，每块里一行三列
st.markdown("### 📦 总库存口径")
col1, col2, col3 = st.columns(3)
with col1:
    render_colored_df(df_sku_total, "#### 📊 SKU 统计（年份品/非年份品）")
with col2:
    render_colored_df(df_stock_total, "#### 📦 库存数量统计（年份品/非年份品）")
with col3:
    render_colored_df(df_amt_total, "#### 💰 库存金额统计（年份品/非年份品）")

st.divider()

st.markdown("### 🚀 FBA+AWD+在途口径")
col4, col5, col6 = st.columns(3)
with col4:
    render_colored_df(df_sku_fba, "#### 📊 SKU 统计（年份品/非年份品）")
with col5:
    render_colored_df(df_stock_fba, "#### 📦 库存数量统计（年份品/非年份品）")
with col6:
    render_colored_df(df_amt_fba, "#### 💰 库存金额统计（年份品/非年份品）")



st.divider()
st.subheader("📦 滞销库存来源分析（按采购类型）")

# ===================== 1. 基础配置 =====================
stock_date = pd.to_datetime(df_curr["时间"].iloc[0])
risk_unsale = ["低滞销风险", "中滞销风险", "高滞销风险"]
df_unsale = df_curr[df_curr["滞销风险等级"].isin(risk_unsale)].copy()

# 上月滞销数据
df_unsale_prev = df_prev[df_prev["滞销风险等级"].isin(risk_unsale)].copy()
stock_date_prev = pd.to_datetime(df_prev["时间"].iloc[0])


# ===================== 2. 采购数据：只算库存日期之前 =====================
# 改造函数，新增shop_list入参，过滤采购表对应店铺
def get_pur_before(df_pur_raw, date_limit, shop_list):
    pur_clean = df_pur_raw.copy()
    pur_clean["采购日期"] = pd.to_datetime(pur_clean["采购日期"], errors="coerce")
    # 新增：过滤当前权限/筛选的店铺
    pur_clean = pur_clean[pur_clean["店铺"].isin(shop_list)]

    date_upper = date_limit + pd.DateOffset(years=1)
    pur_before = pur_clean[
        (pur_clean["采购日期"] <= date_upper) &
        (pur_clean["采购日期"].notna())
        ].copy()

    msku_pur = pur_before.pivot_table(
        index="MSKU",
        columns="采购类型",
        values="采购量",
        aggfunc="sum"
    ).fillna(0).reset_index()
    for c in ["年前采购", "年后采购", "年货采购"]:
        if c not in msku_pur.columns:
            msku_pur[c] = 0
    return msku_pur


msku_pur_curr = get_pur_before(df_pur, stock_date, active_shops)
msku_pur_prev = get_pur_before(df_pur, stock_date_prev, active_shops)

# ===================== 3. 数据整合（总库存 + FBA 双维度） =====================
# 第一步：只聚合库存/成本类字段，不碰日均
inv_full_all = df_curr.groupby("MSKU").agg(
    店铺=("店铺", "first"),
    品名=("品名", "first"),
    采购成本=("采购成本", "first"),
    头程费用=("头程费用", "first"),
    FBA_AWD_在途库存=("FBA+AWD+在途库存", "sum"),
    本地库存=("本地库存", "sum"),
    总库存=("总库存", "sum"),
    滞销总库存=("总滞销库存", "sum"),
    FBA滞销数量_仅FBA=("FBA滞销数量_仅FBA", "sum")
).reset_index()

# 单独提取MSKU+四类日均，去重后合并进聚合表
daily_info_curr = df_curr[["MSKU", "日均", "7天日均", "14天日均", "28天日均"]].drop_duplicates(subset="MSKU")
inv_full_all = inv_full_all.merge(daily_info_curr, on="MSKU", how="left")

# 关联采购数据
df_merge_all = inv_full_all.merge(msku_pur_curr, on="MSKU", how="left").fillna(0)
df_merge_all["年货前采购总库存"] = (
    df_merge_all["总库存"] - df_merge_all["年货采购"] - df_merge_all["年前采购"] - df_merge_all["年后采购"]
).clip(lower=0)

# 上月全量数据（同步逻辑）
inv_full_all_prev = df_prev.groupby("MSKU").agg(
    店铺=("店铺", "first"),
    品名=("品名", "first"),
    采购成本=("采购成本", "first"),
    头程费用=("头程费用", "first"),
    FBA_AWD_在途库存=("FBA+AWD+在途库存", "sum"),
    本地库存=("本地库存", "sum"),
    总库存=("总库存", "sum"),
    滞销总库存=("总滞销库存", "sum"),
    FBA滞销数量_仅FBA=("FBA滞销数量_仅FBA", "sum")
).reset_index()

# 上月日均合并
daily_info_prev = df_prev[["MSKU", "日均", "7天日均", "14天日均", "28天日均"]].drop_duplicates(subset="MSKU")
inv_full_all_prev = inv_full_all_prev.merge(daily_info_prev, on="MSKU", how="left")

df_merge_all_prev = inv_full_all_prev.merge(msku_pur_prev, on="MSKU", how="left").fillna(0)
df_merge_all_prev["年货前采购总库存"] = (
    df_merge_all_prev["总库存"] - df_merge_all_prev["年货采购"] - df_merge_all_prev["年前采购"] - df_merge_all_prev["年后采购"]
).clip(lower=0)

# 用全量数据
df_merge_curr = df_merge_all.copy()
df_merge_prev = df_merge_all_prev.copy()

# ===================== 4. 通用数量分摊函数（年后→年前→年货→年货前） =====================
def alloc_qty_by_purchase(df_target, qty_col, suffix):
    """总库存口径分摊，原有逻辑不变"""
    def alloc_row(row):
        unsale = row[qty_col]
        after = row["年后采购"]
        before = row["年前采购"]
        goods = row["年货采购"]

        a = min(unsale, after)
        unsale -= a
        b = min(unsale, before)
        unsale -= b
        c = min(unsale, goods)
        unsale -= c
        d = unsale
        return pd.Series([d, c, b, a])

    col_list = [
        f"年货前采购滞销数量{suffix}",
        f"年货采购滞销数量{suffix}",
        f"年前采购滞销数量{suffix}",
        f"年后采购滞销数量{suffix}"
    ]
    df_target[col_list] = df_target.apply(alloc_row, axis=1)
    return df_target

# ===================== FBA分摊函数（修复稳定版，无KeyError、无重复计算） =====================
def alloc_qty_fba_correct(df_target):
    def alloc_row(row):
        local_qty = float(row["本地库存"])
        fba_total = float(row["FBA滞销数量_仅FBA"])

        pur_after  = float(row["年后采购"])
        pur_before = float(row["年前采购"])
        pur_goods  = float(row["年货采购"])
        pur_pre    = float(row["年货前采购总库存"])

        # 第一步：本地库存 年后→年前→年货→年货前 扣减
        remain_local = local_qty
        deduct = min(remain_local, pur_after)
        pur_after -= deduct
        remain_local -= deduct

        deduct = min(remain_local, pur_before)
        pur_before -= deduct
        remain_local -= deduct

        deduct = min(remain_local, pur_goods)
        pur_goods -= deduct
        remain_local -= deduct

        deduct = min(remain_local, pur_pre)
        pur_pre -= deduct
        remain_local -= deduct

        # 第二步：剩余采购量分摊FBA滞销
        remain_fba = fba_total
        fba_after  = min(remain_fba, pur_after)
        remain_fba -= fba_after

        fba_before = min(remain_fba, pur_before)
        remain_fba -= fba_before

        fba_goods  = min(remain_fba, pur_goods)
        remain_fba -= fba_goods

        fba_pre    = remain_fba

        # 返回顺序：年货前、年货、年前、年后
        return pd.Series([fba_pre, fba_goods, fba_before, fba_after])

    fba_cols = [
        "年货前采购滞销数量_fba",
        "年货采购滞销数量_fba",
        "年前采购滞销数量_fba",
        "年后采购滞销数量_fba"
    ]
    df_target[fba_cols] = df_target.apply(alloc_row, axis=1)
    return df_target

# ===================== 5. 金额计算函数（两套规则） =====================
def calc_amt_total(row):
    """总库存口径：本地=成本，FBA=成本+头程"""
    local_total = row["本地库存"]
    cost = row["采购成本"]
    freight = row["头程费用"]

    qty_pre = row["年货前采购滞销数量_total"]
    qty_goods = row["年货采购滞销数量_total"]
    qty_before = row["年前采购滞销数量_total"]
    qty_after = row["年后采购滞销数量_total"]

    def calc_single(qty, remain_local_ref):
        if qty <= 0:
            return 0
        use_local = min(qty, remain_local_ref[0])
        use_fba = qty - use_local
        remain_local_ref[0] -= use_local
        return round(use_local * cost + use_fba * (cost + freight), 2)

    remain_local = [local_total]
    amt_after = calc_single(qty_after, remain_local)
    amt_before = calc_single(qty_before, remain_local)
    amt_goods = calc_single(qty_goods, remain_local)
    amt_pre = calc_single(qty_pre, remain_local)

    return pd.Series([amt_pre, amt_goods, amt_before, amt_after])

def calc_amt_fba(row):
    """FBA口径：统一按 成本+头程 计价"""
    cost = row["采购成本"]
    freight = row["头程费用"]

    qty_pre = row["年货前采购滞销数量_fba"]
    qty_goods = row["年货采购滞销数量_fba"]
    qty_before = row["年前采购滞销数量_fba"]
    qty_after = row["年后采购滞销数量_fba"]

    def calc_single(qty):
        return round(qty * (cost + freight), 2) if qty > 0 else 0

    return pd.Series([
        calc_single(qty_pre),
        calc_single(qty_goods),
        calc_single(qty_before),
        calc_single(qty_after)
    ])

# ===================== 6. 【1】总库存维度 计算 =====================
df_merge_curr = alloc_qty_by_purchase(df_merge_curr, qty_col="滞销总库存", suffix="_total")
df_merge_prev = alloc_qty_by_purchase(df_merge_prev, qty_col="滞销总库存", suffix="_total")

# 总库存金额
amt_cols_total = [
    "年货前采购滞销金额_total",
    "年货采购滞销金额_total",
    "年前采购滞销金额_total",
    "年后采购滞销金额_total"
]
df_merge_curr[amt_cols_total] = df_merge_curr.apply(calc_amt_total, axis=1)
df_merge_prev[amt_cols_total] = df_merge_prev.apply(calc_amt_total, axis=1)

# ===================== 7. FBA维度 分摊（仅调用一次，禁止重复） =====================
df_merge_curr = alloc_qty_fba_correct(df_merge_curr)
df_merge_prev = alloc_qty_fba_correct(df_merge_prev)

# ===================== 【校验代码】 =====================
st.subheader("🔍 分摊后校验")
required_cols = ["年货前采购滞销数量_fba", "年货采购滞销数量_fba", "年前采购滞销数量_fba", "年后采购滞销数量_fba"]
missing_cols = [col for col in required_cols if col not in df_merge_curr.columns]
if missing_cols:
    st.error(f"错误：缺少字段 {missing_cols}")
else:
    df_merge_curr["FBA拆分后合计校验"] = (
            df_merge_curr["年货前采购滞销数量_fba"]
            + df_merge_curr["年货采购滞销数量_fba"]
            + df_merge_curr["年前采购滞销数量_fba"]
            + df_merge_curr["年后采购滞销数量_fba"]
    )
    st.write(f"原始FBA滞销总量：{df_merge_curr['FBA滞销数量_仅FBA'].sum():,.2f}")
    st.write(f"四项拆分后总和：{df_merge_curr['FBA拆分后合计校验'].sum():,.2f}")
    st.write(f"单条不匹配行数：{(df_merge_curr['FBA拆分后合计校验'] != df_merge_curr['FBA滞销数量_仅FBA']).sum()}")

# ===================== 8. FBA金额计算 =====================
amt_cols_fba = [
    "年货前采购滞销金额_fba",
    "年货采购滞销金额_fba",
    "年前采购滞销金额_fba",
    "年后采购滞销金额_fba"
]
df_merge_curr[amt_cols_fba] = df_merge_curr.apply(calc_amt_fba, axis=1)
df_merge_prev[amt_cols_fba] = df_merge_prev.apply(calc_amt_fba, axis=1)

# ===================== 9. 汇总函数 =====================
def sum_data(df, suffix):
    return {
        "pre_qty": int(df[f"年货前采购滞销数量{suffix}"].sum()),
        "goods_qty": int(df[f"年货采购滞销数量{suffix}"].sum()),
        "before_qty": int(df[f"年前采购滞销数量{suffix}"].sum()),
        "after_qty": int(df[f"年后采购滞销数量{suffix}"].sum()),
        "pre_amt": round(df[f"年货前采购滞销金额{suffix}"].sum(), 2),
        "goods_amt": round(df[f"年货采购滞销金额{suffix}"].sum(), 2),
        "before_amt": round(df[f"年前采购滞销金额{suffix}"].sum(), 2),
        "after_amt": round(df[f"年后采购滞销金额{suffix}"].sum(), 2),
    }

# 汇总数据
curr_sum_total = sum_data(df_merge_curr, suffix="_total")
prev_sum_total = sum_data(df_merge_prev, suffix="_total")

curr_sum_fba = sum_data(df_merge_curr, suffix="_fba")
prev_sum_fba = sum_data(df_merge_prev, suffix="_fba")

# 公共基础采购库存
total_pre_all_stock = int(df_merge_all["年货前采购总库存"].sum())
total_pur_year = msku_pur_curr["年货采购"].sum()
total_pur_before = msku_pur_curr["年前采购"].sum()
total_pur_after = msku_pur_curr["年后采购"].sum()

# 占比通用函数
def safe_pct(val, total):
    return val / total * 100 if total != 0 else 0

# -------- 总库存占比 --------
total_curr_qty_total = curr_sum_total["pre_qty"] + curr_sum_total["goods_qty"] + curr_sum_total["before_qty"] + curr_sum_total["after_qty"]
pct_pre_total = safe_pct(curr_sum_total["pre_qty"], total_curr_qty_total)
pct_goods_total = safe_pct(curr_sum_total["goods_qty"], total_curr_qty_total)
pct_before_total = safe_pct(curr_sum_total["before_qty"], total_curr_qty_total)
pct_after_total = safe_pct(curr_sum_total["after_qty"], total_curr_qty_total)

pct_of_pur_pre_total = safe_pct(curr_sum_total["pre_qty"], total_pre_all_stock)
pct_of_pur_goods_total = safe_pct(curr_sum_total["goods_qty"], total_pur_year)
pct_of_pur_before_total = safe_pct(curr_sum_total["before_qty"], total_pur_before)
pct_of_pur_after_total = safe_pct(curr_sum_total["after_qty"], total_pur_after)

# -------- FBA占比 --------
total_curr_qty_fba = curr_sum_fba["pre_qty"] + curr_sum_fba["goods_qty"] + curr_sum_fba["before_qty"] + curr_sum_fba["after_qty"]
pct_pre_fba = safe_pct(curr_sum_fba["pre_qty"], total_curr_qty_fba)
pct_goods_fba = safe_pct(curr_sum_fba["goods_qty"], total_curr_qty_fba)
pct_before_fba = safe_pct(curr_sum_fba["before_qty"], total_curr_qty_fba)
pct_after_fba = safe_pct(curr_sum_fba["after_qty"], total_curr_qty_fba)

pct_of_pur_pre_fba = safe_pct(curr_sum_fba["pre_qty"], total_pre_all_stock)
pct_of_pur_goods_fba = safe_pct(curr_sum_fba["goods_qty"], total_pur_year)
pct_of_pur_before_fba = safe_pct(curr_sum_fba["before_qty"], total_pur_before)
pct_of_pur_after_fba = safe_pct(curr_sum_fba["after_qty"], total_pur_after)

# ===================== 10. 环比格式化 =====================
def fmt_num_curr(curr, prev):
    diff = curr - prev
    if diff > 0:
        return f"{curr:,}", f'<span style="color:#d32f2f">↑ +{diff:,}</span>'
    elif diff < 0:
        return f"{curr:,}", f'<span style="color:#388e3c">↓ {diff:,}</span>'
    else:
        return f"{curr:,}", '<span style="color:#666">持平</span>'

def fmt_amt_curr(curr, prev):
    diff = curr - prev
    if diff > 0:
        return f"{curr:,.2f}", f'<span style="color:#d32f2f">↑ +{diff:,.2f}</span>'
    elif diff < 0:
        return f"{curr:,.2f}", f'<span style="color:#388e3c">↓ {diff:,.2f}</span>'
    else:
        return f"{curr:,.2f}", '<span style="color:#666">持平</span>'

# ===================== 11. 页面渲染 =====================
# 第一组：总库存（本地+FBA）
st.markdown("### 📊 维度一：总库存（本地 + FBA+AWD在途）滞销来源")
c1, c2, c3, c4 = st.columns(4)

# 年货前
qty_str1, qty_fluc1 = fmt_num_curr(curr_sum_total["pre_qty"], prev_sum_total["pre_qty"])
amt_str1, amt_fluc1 = fmt_amt_curr(curr_sum_total["pre_amt"], prev_sum_total["pre_amt"])
with c1:
    st.markdown(f"""
    <div style="background:#f3f4f6; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#444;">⏳ 年货前采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str1} 件 {qty_fluc1}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str1} 元 {amt_fluc1}</div>
        <div style="font-size:14px;color:#666;">年货前采购总库存：{total_pre_all_stock:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_pre_total:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_pre_total:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 年货
qty_str2, qty_fluc2 = fmt_num_curr(curr_sum_total["goods_qty"], prev_sum_total["goods_qty"])
amt_str2, amt_fluc2 = fmt_amt_curr(curr_sum_total["goods_amt"], prev_sum_total["goods_amt"])
with c2:
    st.markdown(f"""
    <div style="background:#fff9e6; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#e65100;">🧧 年货采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str2} 件 {qty_fluc2}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str2} 元 {amt_fluc2}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_year:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_goods_total:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_goods_total:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 年前
qty_str3, qty_fluc3 = fmt_num_curr(curr_sum_total["before_qty"], prev_sum_total["before_qty"])
amt_str3, amt_fluc3 = fmt_amt_curr(curr_sum_total["before_amt"], prev_sum_total["before_amt"])
with c3:
    st.markdown(f"""
    <div style="background:#ffebee; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#c62828;">🧨 年前采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str3} 件 {qty_fluc3}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str3} 元 {amt_fluc3}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_before:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_before_total:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_before_total:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 年后
qty_str4, qty_fluc4 = fmt_num_curr(curr_sum_total["after_qty"], prev_sum_total["after_qty"])
amt_str4, amt_fluc4 = fmt_amt_curr(curr_sum_total["after_amt"], prev_sum_total["after_amt"])
with c4:
    st.markdown(f"""
    <div style="background:#e3f2fd; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#1565c0;">🧊 年后采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_str4} 件 {qty_fluc4}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_str4} 元 {amt_fluc4}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_after:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_after_total:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_after_total:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# 第二组：FBA+AWD在途（仅海外库存）
st.markdown("### 🚀 维度二：FBA+AWD+在途 滞销来源（剔除本地库存）")
c5, c6, c7, c8 = st.columns(4)

# 年货前
qty_f1, fluc_f1 = fmt_num_curr(curr_sum_fba["pre_qty"], prev_sum_fba["pre_qty"])
amt_f1, a_fluc_f1 = fmt_amt_curr(curr_sum_fba["pre_amt"], prev_sum_fba["pre_amt"])
with c5:
    st.markdown(f"""
    <div style="background:#f3f4f6; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#444;">⏳ 年货前采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_f1} 件 {fluc_f1}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_f1} 元 {a_fluc_f1}</div>
        <div style="font-size:14px;color:#666;">年货前采购总库存：{total_pre_all_stock:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_pre_fba:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_pre_fba:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 年货
qty_f2, fluc_f2 = fmt_num_curr(curr_sum_fba["goods_qty"], prev_sum_fba["goods_qty"])
amt_f2, a_fluc_f2 = fmt_amt_curr(curr_sum_fba["goods_amt"], prev_sum_fba["goods_amt"])
with c6:
    st.markdown(f"""
    <div style="background:#fff9e6; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#e65100;">🧧 年货采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_f2} 件 {fluc_f2}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_f2} 元 {a_fluc_f2}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_year:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_goods_fba:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_goods_fba:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 年前
qty_f3, fluc_f3 = fmt_num_curr(curr_sum_fba["before_qty"], prev_sum_fba["before_qty"])
amt_f3, a_fluc_f3 = fmt_amt_curr(curr_sum_fba["before_amt"], prev_sum_fba["before_amt"])
with c7:
    st.markdown(f"""
    <div style="background:#ffebee; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#c62828;">🧨 年前采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_f3} 件 {fluc_f3}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_f3} 元 {a_fluc_f3}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_before:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_before_fba:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_before_fba:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# 年后
qty_f4, fluc_f4 = fmt_num_curr(curr_sum_fba["after_qty"], prev_sum_fba["after_qty"])
amt_f4, a_fluc_f4 = fmt_amt_curr(curr_sum_fba["after_amt"], prev_sum_fba["after_amt"])
with c8:
    st.markdown(f"""
    <div style="background:#e3f2fd; padding:20px; border-radius:12px; text-align:center;">
        <h4 style="margin:0;color:#1565c0;">🧊 年后采购滞销</h4>
        <div style="font-size:32px;font-weight:bold;margin:8px 0;">{qty_f4} 件 {fluc_f4}</div>
        <div style="font-size:16px;margin:4px 0;">金额：{amt_f4} 元 {a_fluc_f4}</div>
        <div style="font-size:14px;color:#666;">采购总量：{total_pur_after:,.0f} 件</div>
        <div style="font-size:14px;color:#666;">滞销占采购量：{pct_of_pur_after_fba:.2f}%</div>
        <div style="font-size:14px;color:#666;">滞销总占比：{pct_after_fba:.2f}%</div>
    </div>
    """, unsafe_allow_html=True)

# ===================== 9. 明细表格 =====================
with st.expander("📄 查看 MSKU 滞销来源明细（数量+金额+本地/FBA口径）"):
    show_cols = [
        # 基础信息
        "MSKU", "店铺", "品名",
        "日均",
        "7天日均",
        "14天日均",
        "28天日均",
        # 库存基础数据
        "总库存", "本地库存", "FBA_AWD_在途库存", "年货前采购总库存",
        "采购成本", "头程费用",
        # 原始采购量
        "年货采购", "年前采购", "年后采购",
        # ========== 总库存口径（_total） ==========
        "滞销总库存",
        "年货前采购滞销数量_total",
        "年货采购滞销数量_total",
        "年前采购滞销数量_total",
        "年后采购滞销数量_total",
        "年货前采购滞销金额_total",
        "年货采购滞销金额_total",
        "年前采购滞销金额_total",
        "年后采购滞销金额_total",
        # ========== FBA+AWD在途口径（_fba） ==========
        "FBA滞销数量_仅FBA",
        "年货前采购滞销数量_fba",
        "年货采购滞销数量_fba",
        "年前采购滞销数量_fba",
        "年后采购滞销数量_fba",
        "年货前采购滞销金额_fba",
        "年货采购滞销金额_fba",
        "年前采购滞销金额_fba",
        "年后采购滞销金额_fba"
    ]

    # 排序：优先按总滞销库存倒序
    st.dataframe(
        df_merge_curr[show_cols].sort_values("滞销总库存", ascending=False),
        use_container_width=True,
        height=600
    )



# ===================== 完整全套代码：HTML表格渲染彩色环比（无span明文） =====================
import plotly.express as px
import plotly.io as pio
pio.templates.default = "plotly_white"

# 1. 合并商品【是否年份】标识到当月/上月数据表
df_merge_curr = df_merge_curr.merge(
    df_curr[["MSKU", "是否年份"]].drop_duplicates("MSKU"),
    on="MSKU", how="left"
).fillna({"是否年份": "否"})

df_merge_prev = df_merge_prev.merge(
    df_prev[["MSKU", "是否年份"]].drop_duplicates("MSKU"),
    on="MSKU", how="left"
).fillna({"是否年份": "否"})

# 2. 采购类型全局配置
pur_config_list = [
    {
        "name_cn": "年货前采购",
        "qty_total_col": "年货前采购滞销数量_total",
        "amt_total_col": "年货前采购滞销金额_total",
        "qty_fba_col": "年货前采购滞销数量_fba",
        "amt_fba_col": "年货前采购滞销金额_fba",
        "color": "#9ca3af"
    },
    {
        "name_cn": "年货采购",
        "qty_total_col": "年货采购滞销数量_total",
        "amt_total_col": "年货采购滞销金额_total",
        "qty_fba_col": "年货采购滞销数量_fba",
        "amt_fba_col": "年货采购滞销金额_fba",
        "color": "#f59e0b"
    },
    {
        "name_cn": "年前采购",
        "qty_total_col": "年前采购滞销数量_total",
        "amt_total_col": "年前采购滞销金额_total",
        "qty_fba_col": "年前采购滞销数量_fba",
        "amt_fba_col": "年前采购滞销金额_fba",
        "color": "#ef4444"
    },
    {
        "name_cn": "年后采购",
        "qty_total_col": "年后采购滞销数量_total",
        "amt_total_col": "年后采购滞销金额_total",
        "qty_fba_col": "年后采购滞销数量_fba",
        "amt_fba_col": "年后采购滞销金额_fba",
        "color": "#3b82f6"
    }
]

# 3. 聚合函数
def agg_single_pur(df_curr, df_prev, pur_cfg):
    curr_agg = df_curr.groupby("是否年份").agg(
        qty_total=("是否年份", lambda x: df_curr.loc[x.index, pur_cfg["qty_total_col"]].sum()),
        amt_total=("是否年份", lambda x: df_curr.loc[x.index, pur_cfg["amt_total_col"]].sum()),
        qty_fba=("是否年份", lambda x: df_curr.loc[x.index, pur_cfg["qty_fba_col"]].sum()),
        amt_fba=("是否年份", lambda x: df_curr.loc[x.index, pur_cfg["amt_fba_col"]].sum())
    ).reset_index()
    prev_agg = df_prev.groupby("是否年份").agg(
        qty_total_prev=("是否年份", lambda x: df_prev.loc[x.index, pur_cfg["qty_total_col"]].sum()),
        amt_total_prev=("是否年份", lambda x: df_prev.loc[x.index, pur_cfg["amt_total_col"]].sum()),
        qty_fba_prev=("是否年份", lambda x: df_prev.loc[x.index, pur_cfg["qty_fba_col"]].sum()),
        amt_fba_prev=("是否年份", lambda x: df_prev.loc[x.index, pur_cfg["amt_fba_col"]].sum())
    ).reset_index()
    merge_df = curr_agg.merge(prev_agg, on="是否年份", how="left").fillna(0)
    merge_df["商品类型"] = merge_df["是否年份"].map({"是": "年份品", "否": "非年份品"})
    return merge_df

# 4. 饼图绘制函数
def draw_single_pie(df_source, pur_name, chart_type, stock_type, color_year="#ef4444", color_non="#666666"):
    val_col = f"{chart_type}_{stock_type}"
    title_map = {
        ("qty", "total"): f"{pur_name}｜总库存口径-滞销数量占比",
        ("amt", "total"): f"{pur_name}｜总库存口径-滞销金额占比",
        ("qty", "fba"): f"{pur_name}｜FBA+AWD口径-滞销数量占比",
        ("amt", "fba"): f"{pur_name}｜FBA+AWD口径-滞销金额占比",
    }
    fig = px.pie(
        df_source,
        values=val_col,
        names="商品类型",
        title=title_map[(chart_type, stock_type)],
        hole=0.3,
        color_discrete_map={
            "年份品": color_year,
            "非年份品": "#6386e8"
        }
    )
    fig.update_traces(texttemplate="%{percent:.2%}<br>%{value:,.0f}", textposition="inside")
    fig.update_layout(height=360)
    return fig

# ========== HTML彩色格式化函数：红涨#d32f2f 绿跌#388e3c 持平无颜色 ==========
def fmt_qty_html(curr, prev):
    curr_int = int(curr)
    prev_int = int(prev)
    diff = curr_int - prev_int
    if diff > 0:
        return f"{curr_int:,} <span style='color:#d32f2f'>↑+{diff:,}</span>"
    elif diff < 0:
        return f"{curr_int:,} <span style='color:#388e3c'>↓{diff:,}</span>"
    else:
        return f"{curr_int:,} 持平"

def fmt_amt_html(curr, prev):
    curr_2 = round(curr, 2)
    prev_2 = round(prev, 2)
    diff = curr_2 - prev_2
    if diff > 0:
        return f"{curr_2:,.2f} <span style='color:#d32f2f'>↑+{diff:,.2f}</span>"
    elif diff < 0:
        return f"{curr_2:,.2f} <span style='color:#388e3c'>↓{diff:,.2f}</span>"
    else:
        return f"{curr_2:,.2f} 持平"

# ===================== 页面渲染循环（HTML表格，正常渲染颜色） =====================
st.divider()
st.header("📦 分采购类型滞销细分（双口径 × 年份品/非年份品）")

for pur in pur_config_list:
    st.subheader(f"===== {pur['name_cn']} 滞销拆解 =====")
    agg_df = agg_single_pur(df_merge_curr, df_merge_prev, pur)
    row_year = agg_df[agg_df["商品类型"] == "年份品"].iloc[0]
    row_non = agg_df[agg_df["商品类型"] == "非年份品"].iloc[0]

    # 合计值
    total_qty_t = row_non["qty_total"] + row_year["qty_total"]
    total_qty_t_prev = row_non["qty_total_prev"] + row_year["qty_total_prev"]
    total_amt_t = row_non["amt_total"] + row_year["amt_total"]
    total_amt_t_prev = row_non["amt_total_prev"] + row_year["amt_total_prev"]

    total_qty_f = row_non["qty_fba"] + row_year["qty_fba"]
    total_qty_f_prev = row_non["qty_fba_prev"] + row_year["qty_fba_prev"]
    total_amt_f = row_non["amt_fba"] + row_year["amt_fba"]
    total_amt_f_prev = row_non["amt_fba_prev"] + row_year["amt_fba_prev"]

    # 组装每一行单元格内容
    rows_data = [
        [
            "滞销总数量",
            fmt_qty_html(total_qty_t, total_qty_t_prev),
            fmt_qty_html(total_qty_f, total_qty_f_prev)
        ],
        [
            "年份品滞销数量（占比）",
            f"{fmt_qty_html(row_year['qty_total'], row_year['qty_total_prev'])} 占比{safe_pct(row_year['qty_total'], total_qty_t):.2f}%",
            f"{fmt_qty_html(row_year['qty_fba'], row_year['qty_fba_prev'])} 占比{safe_pct(row_year['qty_fba'], total_qty_f):.2f}%"
        ],
        [
            "非年份品滞销数量（占比）",
            f"{fmt_qty_html(row_non['qty_total'], row_non['qty_total_prev'])} 占比{safe_pct(row_non['qty_total'], total_qty_t):.2f}%",
            f"{fmt_qty_html(row_non['qty_fba'], row_non['qty_fba_prev'])} 占比{safe_pct(row_non['qty_fba'], total_qty_f):.2f}%"
        ],
        [
            "滞销总金额",
            fmt_amt_html(total_amt_t, total_amt_t_prev),
            fmt_amt_html(total_amt_f, total_amt_f_prev)
        ],
        [
            "年份品滞销金额（占比）",
            f"{fmt_amt_html(row_year['amt_total'], row_year['amt_total_prev'])} 占比{safe_pct(row_year['amt_total'], total_amt_t):.2f}%",
            f"{fmt_amt_html(row_year['amt_fba'], row_year['amt_fba_prev'])} 占比{safe_pct(row_year['amt_fba'], total_amt_f):.2f}%"
        ],
        [
            "非年份品滞销金额（占比）",
            f"{fmt_amt_html(row_non['amt_total'], row_non['amt_total_prev'])} 占比{safe_pct(row_non['amt_total'], total_amt_t):.2f}%",
            f"{fmt_amt_html(row_non['amt_fba'], row_non['amt_fba_prev'])} 占比{safe_pct(row_non['amt_fba'], total_amt_f):.2f}%"
        ]
    ]

    # 拼接完整HTML表格字符串
    html_table = f"""
##### {pur['name_cn']} 滞销明细汇总（双口径横向对比）
<table width="100%" border="1" cellpadding="8" cellspacing="0">
<thead>
<tr style="background:#f5f5f5">
<th align="left">指标名称</th>
<th align="left">总库存口径</th>
<th align="left">FBA+AWD+在途口径</th>
</tr>
</thead>
<tbody>
"""
    for r in rows_data:
        html_table += f"""
<tr>
<td>{r[0]}</td>
<td>{r[1]}</td>
<td>{r[2]}</td>
</tr>
"""
    html_table += "</tbody></table>"

    # 使用markdown渲染HTML，支持颜色
    st.markdown(html_table, unsafe_allow_html=True)
    st.divider()

    # 一行四列饼图不变
    c_pie1, c_pie2, c_pie3, c_pie4 = st.columns(4)
    with c_pie1:
        fig1 = draw_single_pie(agg_df, pur["name_cn"], chart_type="qty", stock_type="total", color_year=pur["color"])
        st.plotly_chart(fig1, use_container_width=True)
    with c_pie2:
        fig2 = draw_single_pie(agg_df, pur["name_cn"], chart_type="amt", stock_type="total", color_year=pur["color"])
        st.plotly_chart(fig2, use_container_width=True)
    with c_pie3:
        fig3 = draw_single_pie(agg_df, pur["name_cn"], chart_type="qty", stock_type="fba", color_year=pur["color"])
        st.plotly_chart(fig3, use_container_width=True)
    with c_pie4:
        fig4 = draw_single_pie(agg_df, pur["name_cn"], chart_type="amt", stock_type="fba", color_year=pur["color"])
        st.plotly_chart(fig4, use_container_width=True)
    st.divider()
    st.divider()








