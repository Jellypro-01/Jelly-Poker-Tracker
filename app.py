import streamlit as st
import pandas as pd
import datetime
import requests
import json
import gspread
from google.oauth2.service_account import Credentials

# ================= 1. 页面基础配置 =================
st.set_page_config(page_title="Jelly Poker Tracker", page_icon="🃏", layout="wide")

CURRENCIES = ["CNY", "USD", "AUD", "VND", "KRW"]

# ================= 2. 连接谷歌云端数据库 =================
@st.cache_resource
def init_connection():
    # 从 Streamlit 的 Secrets 中读取我们藏好的 JSON 钥匙
    creds_json = json.loads(st.secrets["google_credentials"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    # 打开你新建的谷歌表格，名字必须一模一样
    return client.open("Jelly Poker DB").sheet1

try:
    sheet = init_connection()
except Exception as e:
    st.error(f"⚠️ 真正的报错原因是: {str(e)}") # <--- 就改这一行
    st.stop()
# 每次刷新网页时，从云端拉取最新数据
records = sheet.get_all_records()
if not records:
    df = pd.DataFrame(columns=["Date", "Location", "Buy_in", "Entries", "Cashed", "Currency", "Profit_CNY"])
else:
    df = pd.DataFrame(records)

# ================= 3. 核心逻辑：获取实时汇率 =================
@st.cache_data(ttl=3600)
def fetch_exchange_rates():
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
    
    rates_cny_base = {}
    for c in CURRENCIES:
        rates_cny_base[c] = rates_usd_base["CNY"] / rates_usd_base[c] 
    
    return rates_cny_base, rates_usd_base

rates_cny_base, rates_usd_base = fetch_exchange_rates()

# ================= 4. 侧边栏：汇率 & 智能计算器 =================
st.sidebar.markdown("## 💱 汇率计算器")
with st.sidebar.container(border=True):
    calc_amount = st.number_input("输入金额", min_value=0.0, value=1000.0, step=100.0, label_visibility="collapsed")
    col1, col2 = st.columns(2)
    calc_from = col1.selectbox("从 (From)", CURRENCIES, index=2)
    calc_to = col2.selectbox("至 (To)", CURRENCIES, index=0)
    
    converted_amount = (calc_amount / rates_usd_base[calc_from]) * rates_usd_base[calc_to]
    st.markdown(f"### {converted_amount:,.2f} {calc_to}")

st.sidebar.markdown("### 📊 当前基准汇率")
for c in ["USD", "AUD", "VND", "KRW"]:
    st.sidebar.text(f"1 {c} ≈ {rates_cny_base[c]:,.4f} CNY")

st.sidebar.markdown("---")
st.sidebar.markdown("## 🧮 智能计算器")
st.sidebar.caption("输入算式按回车，如: (1500+200)/3")
with st.sidebar.container(border=True):
    calc_expr = st.text_input("算式输入", value="", label_visibility="collapsed")
    if calc_expr:
        allowed_chars = set("0123456789+-*/.() ")
        if set(calc_expr).issubset(allowed_chars):
            try:
                result = eval(calc_expr)
                st.success(f"### = {result:,.2f}")
            except ZeroDivisionError:
                st.error("❌ 除数不能为 0")
            except Exception:
                st.error("❌ 算式有误")
        else:
            st.warning("⚠️ 仅支持数字和基础符号")

# ================= 5. 主体内容 (双标签页) =================
st.title("🃏 Jelly Poker Dashboard")
st.markdown("---")

tab_dashboard, tab_entry = st.tabs(["📈 数据看板 (Dashboard)", "➕ 录入赛事 (New Entry)"])

# ----------------- 标签页 A：录入表单 -----------------
with tab_entry:
    st.markdown("### 📝 记录新赛事")
    with st.form("add_tournament_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("比赛时间", datetime.date.today())
            historical_locations = df["Location"].dropna().unique().tolist() if not df.empty else []
            default_locations = ["GGPoker 线上"]
            all_locations = list(dict.fromkeys(default_locations + historical_locations))
            
            location_choice = st.selectbox("赛事地点 (下拉选择)", ["👇 我要手动输入新地点..."] + all_locations)
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
            
        submitted = st.form_submit_button("💾 保存并同步至云端", use_container_width=True)
        
        if submitted:
            profit_raw = cashed - (buy_in * entries)
            profit_cny = profit_raw * rates_cny_base[currency]
            
            # 核心魔法：直接将新数据推送到你的谷歌表格！
            sheet.append_row([str(date), location, float(buy_in), int(entries), float(cashed), currency, float(profit_cny)])
            st.success(f"✅ 成功记录！数据已永久保存在谷歌表格。该场净利润: ¥{profit_cny:,.2f} CNY")
            st.rerun()

# ----------------- 标签页 B：数据看板与编辑表 -----------------
with tab_dashboard:
    if not df.empty:
        total_profit_cny = df["Profit_CNY"].sum()
        total_tourneys = len(df)
        itm_count = len(df[df["Cashed"] > 0])
        itm_rate = (itm_count / total_tourneys * 100) if total_tourneys > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**参赛总数:** \n### {total_tourneys} 场")
        with col2:
            profit_color = "success" if total_profit_cny >= 0 else "error"
            if profit_color == "success":
                st.success(f"**总净利润 (RMB):** \n### ¥{total_profit_cny:,.2f}")
            else:
                 st.error(f"**总净利润 (RMB):** \n### ¥{total_profit_cny:,.2f}")
        with col3:
            st.warning(f"**总进圈率 (ITM):** \n### {itm_rate:.1f}%")
            
        st.markdown("---")
        
        st.markdown("### 📈 资金波动曲线 (RMB)")
        df_sorted = df.sort_values(by="Date").reset_index(drop=True)
        df_sorted["Cumulative_Profit"] = df_sorted["Profit_CNY"].cumsum()
        
        chart_data = df_sorted.set_index("Date")[["Cumulative_Profit"]]
        st.line_chart(chart_data, color="#29b5e8")
        
        st.markdown("### 📋 历史详细记录 (✏️ 双击修改，选中行删除)")
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",  
            hide_index=True,
            disabled=["Profit_CNY"] 
        )
        
        if st.button("💾 确认并覆盖保存修改至云端", type="primary"):
            def recalc_profit(row):
                total_invested = float(row['Buy_in']) * int(row['Entries'])
                profit_raw = float(row['Cashed']) - total_invested
                return profit_raw * rates_cny_base[row['Currency']]
                
            edited_df['Profit_CNY'] = edited_df.apply(recalc_profit, axis=1)
            
            # 清空旧表格数据，并将修改后的表格完全覆盖写入
            sheet.clear()
            updated_data = [edited_df.columns.values.tolist()] + edited_df.values.tolist()
            sheet.update(values=updated_data, range_name="A1")
            st.success("✅ 数据修改已成功覆盖并同步！")
            st.rerun()
            
    else:
        st.info("👋 欢迎来到 Jelly Poker Dashboard！你的云端数据库已连接，请录入第一场比赛。")
