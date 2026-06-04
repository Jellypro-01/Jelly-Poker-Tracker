import streamlit as st
import pandas as pd
import datetime
import os
import requests

# 1. 页面基础配置
st.set_page_config(page_title="Jelly Poker Tracker", page_icon="🃏", layout="wide")

DATA_FILE = "poker_records_v3.csv" # 升级了版本号，防止旧数据冲突
CURRENCIES = ["CNY", "USD", "AUD", "VND", "KRW"] # 把 CNY 放在首位

# 初始化数据文件
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=[
        "Date", "Location", "Buy_in", "Entries", "Cashed", "Currency", "Profit_CNY"
    ])
    df.to_csv(DATA_FILE, index=False)

# ================= 核心功能：获取实时汇率 =================
@st.cache_data(ttl=3600)
def fetch_exchange_rates():
    # 默认兜底汇率（1 USD 兑换各国货币）
    rates_usd_base = {"USD": 1.0, "AUD": 1.54, "CNY": 7.24, "VND": 25400.0, "KRW": 1370.0}
    try:
        fiat_url = "https://open.er-api.com/v6/latest/USD"
        fiat_res = requests.get(fiat_url, timeout=5).json()
        if fiat_res.get("result") == "success":
            for c in CURRENCIES:
                if c != "USD":
                    rates_usd_base[c] = fiat_res["rates"].get(c, rates_usd_base[c])
    except Exception:
        pass 
    
    # 将基准转换为 CNY (1 外币 = 多少 CNY)
    rates_cny_base = {}
    for c in CURRENCIES:
        # 比如 1 USD = (7.24 / 1.0) CNY
        rates_cny_base[c] = rates_usd_base["CNY"] / rates_usd_base[c] 
    
    return rates_cny_base, rates_usd_base

rates_cny_base, rates_usd_base = fetch_exchange_rates()
df = pd.read_csv(DATA_FILE)

# ================= 侧边栏：汇率计算器 & 实时牌价 =================
st.sidebar.markdown("## 💱 汇率计算器")
st.sidebar.caption("输入金额，自动换算。")

with st.sidebar.container(border=True):
    calc_amount = st.number_input("输入金额", min_value=0.0, value=1000.0, step=100.0)
    col1, col2 = st.columns(2)
    # 计算器这里使用 USD 基准即可
    calc_from = col1.selectbox("从 (From)", CURRENCIES, index=2) # 默认 AUD
    calc_to = col2.selectbox("转换至 (To)", CURRENCIES, index=0)   # 默认 CNY
    
    converted_amount = (calc_amount / rates_usd_base[calc_from]) * rates_usd_base[calc_to]
    st.markdown(f"### {converted_amount:,.2f} {calc_to}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 当前基准汇率 (兑换 CNY)")
for c in ["USD", "AUD", "VND", "KRW"]:
    st.sidebar.text(f"1 {c} ≈ {rates_cny_base[c]:,.4f} CNY")



# ================= 侧边栏：极简智能计算器 =================
st.sidebar.markdown("---")
st.sidebar.markdown("## 🧮 智能计算器")
st.sidebar.caption("支持混合运算，输入算式后按回车 ↵")

with st.sidebar.container(border=True):
    # 使用极简的单行输入框，取代拥挤的三个框
    calc_expr = st.text_input(
        "算式输入", 
        value="", 
        placeholder="例如输入: (1500+200)/3", 
        label_visibility="collapsed"
    )
    
    if calc_expr:
        # 安全过滤：只允许数字和基础数学符号，防止乱码报错
        allowed_chars = set("0123456789+-*/.() ")
        if set(calc_expr).issubset(allowed_chars):
            try:
                # 核心魔法：自动解析并计算字符串算式
                result = eval(calc_expr)
                # 使用大字号和显眼的绿色底纹突出结果
                st.success(f"### = {result:,.2f}")
            except ZeroDivisionError:
                st.error("❌ 错误：除数不能为 0")
            except Exception:
                st.error("❌ 算式有误，请检查格式")
        else:
            st.warning("⚠️ 仅支持数字和 + - * / ( ) 符号")

# ================= 主体内容：使用标签页 (Tabs) =================
st.title("🃏 Jelly Poker Dashboard")
st.markdown("---")

tab_dashboard, tab_entry = st.tabs(["📈 数据看板 (Dashboard)", "➕ 录入赛事 (New Entry)"])

with tab_entry:
    st.markdown("### 📝 记录新赛事")
    with st.form("add_tournament_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            date = st.date_input("比赛时间", datetime.date.today())
            
            # --- 修复后的“历史记忆”地点输入 ---
            historical_locations = df["Location"].dropna().unique().tolist() if not df.empty else []
            default_locations = ["GGPoker 线上"]
            all_locations = list(dict.fromkeys(default_locations + historical_locations))
            
            location_choice = st.selectbox("赛事地点 / 平台 (下拉选择历史记录)", ["👇 我要手动输入新地点..."] + all_locations)
            new_location = st.text_input("✍️ 手动输入框 (打字会自动覆盖上方选择)")
            
            location = new_location.strip() if new_location.strip() != "" else location_choice
            if location == "👇 我要手动输入新地点...":
                location = "未命名地点"
                
        with col2:
            currency = st.selectbox("结算币种", CURRENCIES)
            buy_in = st.number_input("单次买入价格", min_value=0.0, step=100.0)
            
        st.markdown("#### 结果录入")
        col3, col4 = st.columns(2)
        with col3:
            entries = st.number_input("总买入次数 (1=无重进)", min_value=1, value=1, step=1)
        with col4:
            cashed = st.number_input("总奖励 (未进圈填 0)", min_value=0.0, step=100.0)
            
        submitted = st.form_submit_button("💾 保存赛事记录", use_container_width=True)
        
        if submitted:
            total_invested_raw = buy_in * entries
            profit_raw = cashed - total_invested_raw
            
            # 计算该场赛事的 CNY 净利润
            profit_cny = profit_raw * rates_cny_base[currency]
            
            new_data = pd.DataFrame([{
                "Date": str(date), "Location": location, "Buy_in": buy_in, 
                "Entries": entries, "Cashed": cashed, "Currency": currency,
                "Profit_CNY": profit_cny
            }])
            new_data.to_csv(DATA_FILE, mode='a', header=False, index=False)
            st.success(f"✅ 成功记录！该场赛事净利润: ¥{profit_cny:,.2f} CNY")

with tab_dashboard:
    if not df.empty:
        # 计算全局指标 (CNY)
        total_profit_cny = df["Profit_CNY"].sum()
        total_tourneys = len(df)
        itm_count = len(df[df["Cashed"] > 0])
        itm_rate = (itm_count / total_tourneys * 100) if total_tourneys > 0 else 0
        
        # 顶部数据卡片
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**参赛总数:** \n### {total_tourneys} 场")
        with col2:
            # 利润正负变色
            profit_color = "success" if total_profit_cny >= 0 else "error"
            if profit_color == "success":
                st.success(f"**总净利润 (RMB):** \n### ¥{total_profit_cny:,.2f}")
            else:
                 st.error(f"**总净利润 (RMB):** \n### ¥{total_profit_cny:,.2f}")
        with col3:
            st.warning(f"**总进圈率 (ITM):** \n### {itm_rate:.1f}%")
            
        st.markdown("---")
        
        # 图表与数据表上下分布
        st.markdown("### 📈 资金波动曲线 (RMB)")
        df_sorted = df.sort_values(by="Date").reset_index(drop=True)
        df_sorted["Cumulative_Profit"] = df_sorted["Profit_CNY"].cumsum()
        st.area_chart(df_sorted.set_index("Date")["Cumulative_Profit"], color="#FF5252") # 换成红色曲线
        
        st.markdown("### 📋 历史详细记录")
        # 格式化显示
        display_df = df.copy()
        display_df["Profit_CNY"] = display_df["Profit_CNY"].map(lambda x: f"¥{x:,.2f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    else:
        st.info("👋 欢迎来到 Jelly Poker Dashboard！请点击上方【➕ 录入赛事】标签页记录你的第一场比赛。")
