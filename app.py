import streamlit as st
import pandas as pd
import datetime
import requests
import json
import gspread
from google.oauth2.service_account import Credentials
import time

# ================= 1. 页面基础配置与高级 CSS 美化 =================
st.set_page_config(page_title="Jelly Poker Tracker", page_icon="🃏", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1200px;
}
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
    border-radius: 10px !important;
}
button {
    border-radius: 10px !important;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    font-size: 2.2rem !important;
    font-weight: 800 !important;
    color: #1E293B;
}
[data-testid="stMetricLabel"] {
    font-size: 1rem !important;
    font-weight: 500 !important;
    color: #64748B;
}
</style>
""", unsafe_allow_html=True)

CURRENCIES = ["CNY", "USD", "AUD", "VND", "KRW"]

# ================= 1.5 极简无密码 ID 登录系统 =================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.current_user = ""

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align: center; margin-top: 15vh; font-size: 3rem;'>🃏 Jelly Poker</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #64748B; margin-bottom: 2rem;'>你的云端专属扑克资金管家</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("请输入专属 ID (首次输入自动注册)", placeholder="例如: Tom Dwan", label_visibility="collapsed")
        if st.button("进入金库", use_container_width=True, type="primary"):
            if username.strip() != "":
                st.session_state.authenticated = True
                st.session_state.current_user = username.strip()
                st.rerun()
            else:
                st.error("❌ ID 不能为空！")
    st.stop()

current_user = st.session_state.current_user

# ================= 2. 连接谷歌云端数据库 =================
@st.cache_resource
def init_connection():
    creds_json = json.loads(st.secrets["google_credentials"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("Jelly Poker DB").sheet1

try:
    sheet = init_connection()
except Exception as e:
    st.error(f"⚠️ 无法连接数据库: {str(e)}")
    st.stop()

records = sheet.get_all_records()
if not records:
    # 增加 Format 列
    df = pd.DataFrame(columns=["Date", "Player", "Format", "Location", "Buy_in", "Entries", "Cashed", "Currency", "Profit_CNY"])
else:
    df = pd.DataFrame(records)
    # 兼容处理：如果老数据没有 Format 列，自动补齐为锦标赛，防止报错
    if "Format" not in df.columns:
        df.insert(2, "Format", "🏆 锦标赛 (MTT)")
        
    numeric_columns = ["Buy_in", "Entries", "Cashed", "Profit_CNY"]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

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

# ================= 4. 侧边栏：聚合工具 =================
st.sidebar.markdown(f"### 👤 {current_user}")
if st.sidebar.button("🚪 切换账号", use_container_width=True):
    st.session_state.authenticated = False
    st.session_state.current_user = ""
    st.rerun()

st.sidebar.markdown("---")

with st.sidebar.expander("💱 汇率换算器", expanded=False):
    calc_amount = st.number_input("输入金额", min_value=0.0, value=1000.0, step=100.0, label_visibility="collapsed")
    col1, col2 = st.columns(2)
    calc_from = col1.selectbox("从", CURRENCIES, index=2, label_visibility="collapsed")
    calc_to = col2.selectbox("至", CURRENCIES, index=0, label_visibility="collapsed")
    converted_amount = (calc_amount / rates_usd_base[calc_from]) * rates_usd_base[calc_to]
    st.markdown(f"**结果：{converted_amount:,.2f} {calc_to}**")
    
    st.caption("实时基准：")
    for c in ["USD", "AUD", "VND", "KRW"]:
        st.caption(f"1 {c} ≈ {rates_cny_base[c]:,.4f} CNY")

with st.sidebar.expander("🧮 智能计算器", expanded=False):
    calc_expr = st.text_input("算式输入", value="", placeholder="(1500+200)/3", label_visibility="collapsed")
    if calc_expr:
        allowed_chars = set("0123456789+-*/.() ")
        if set(calc_expr).issubset(allowed_chars):
            try:
                result = eval(calc_expr)
                st.success(f"= {result:,.2f}")
            except:
                st.error("算式有误")

# ================= 5. 主体内容 (双标签页) =================
tab_dashboard, tab_entry = st.tabs(["📊 数据看板", "➕ 记录赛事"])

# ----------------- 标签页 A：数据看板 -----------------
with tab_dashboard:
    display_df = df[df["Player"] == current_user].copy()
    
    if not display_df.empty:
        display_df = display_df.sort_values(by="Date", ascending=False).reset_index(drop=True)
        
        # 新增：双重筛选项 (赛道 + 类型)
        st.markdown("#### 📍 深度交叉分析")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            track_filter = st.radio("赛道", ["🌟 全部赛道", "💻 线上 (Online)", "🏟️ 现场 (Live)"], horizontal=True)
        with col_f2:
            format_filter = st.radio("类型", ["🌟 全部类型", "🏆 锦标赛 (MTT)", "💵 现金局 (Cash)"], horizontal=True)
        
        calc_df = display_df.copy()
        
        # 应用筛选逻辑
        if track_filter == "💻 线上 (Online)":
            calc_df = calc_df[calc_df["Location"].str.contains("线上|Online", na=False, case=False)]
        elif track_filter == "🏟️ 现场 (Live)":
            calc_df = calc_df[~calc_df["Location"].str.contains("线上|Online", na=False, case=False)]
            
        if format_filter != "🌟 全部类型":
            calc_df = calc_df[calc_df["Format"] == format_filter]
            
        st.markdown("---")
        
        if not calc_df.empty:
            total_profit_cny = calc_df["Profit_CNY"].sum()
            total_tourneys = len(calc_df)
            itm_count = len(calc_df[calc_df["Cashed"] > 0])
            itm_rate = (itm_count / total_tourneys * 100) if total_tourneys > 0 else 0
            
            m1, m2, m3 = st.columns(3)
            # 根据现金局或锦标赛动态改变文案
            session_label = "记录场次" if format_filter == "💵 现金局 (Cash)" else "参赛总数"
            win_rate_label = "盈利场次率 (Win%)" if format_filter == "💵 现金局 (Cash)" else "总进圈率 (ITM)"
            
            m1.metric(session_label, f"{total_tourneys} 场")
            m2.metric("总净利润 (RMB)", f"¥{total_profit_cny:,.2f}")
            m3.metric(win_rate_label, f"{itm_rate:.1f}%")
                
            st.markdown("#### 📈 资金波动曲线")
            df_sorted = calc_df.sort_values(by="Date", ascending=True).reset_index(drop=True)
            df_daily = df_sorted.groupby("Date")["Profit_CNY"].sum().reset_index()
            df_daily["Cumulative_Profit"] = df_daily["Profit_CNY"].cumsum()
            
            chart_data = df_daily.set_index("Date")[["Cumulative_Profit"]]
            st.line_chart(chart_data, color="#29b5e8", height=300)
        else:
            st.info("📭 当前筛选条件下暂无数据，快去打一场吧！")

        st.markdown("---")
        st.markdown("#### 📋 完整详细记录")
        st.caption("💡 电脑端可双击直接修改，选中左侧方框按 Delete 键删除 (此处固定显示全部记录，防止误删)。")
        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            num_rows="dynamic",  
            hide_index=True,
            disabled=["Profit_CNY", "Player"] 
        )
        
        if st.button("💾 确认保存修改", type="primary"):
            def recalc_profit(row):
                try:
                    total_invested = float(row['Buy_in']) * int(row['Entries'])
                    profit_raw = float(row['Cashed']) - total_invested
                    return profit_raw * rates_cny_base[row['Currency']]
                except:
                    return 0
                
            edited_df['Profit_CNY'] = edited_df.apply(recalc_profit, axis=1)
            other_users_df = df[df["Player"] != current_user]
            
            final_df = pd.concat([other_users_df, edited_df], ignore_index=True)
            final_df = final_df.sort_values(by="Date", ascending=False) 
            
            # 确保 Format 列在重新上传时包含在内
            final_df = final_df[["Date", "Player", "Format", "Location", "Buy_in", "Entries", "Cashed", "Currency", "Profit_CNY"]]
            
            sheet.clear()
            updated_data = [final_df.columns.values.tolist()] + final_df.values.tolist()
            sheet.update(values=updated_data, range_name="A1")
            st.success("✅ 数据已同步至云端！")
            time.sleep(1.5)
            st.rerun()
            
    else:
        st.info("👋 你的专属金库已准备就绪，去隔壁标签页录入第一场比赛吧！")

# ----------------- 标签页 B：录入表单 -----------------
with tab_entry:
    with st.form("add_tournament_form", clear_on_submit=True):
        st.markdown("#### 📝 新赛事基础信息")
        
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("比赛时间", datetime.date.today())
            # 新增维度：线上/现场，MTT/Cash
            event_track = st.radio("赛道分类", ["💻 线上 (Online)", "🏟️ 现场 (Live)"], horizontal=True)
            game_format = st.radio("游戏类型", ["🏆 锦标赛 (MTT)", "💵 现金局 (Cash)"], horizontal=True)
            
        with col2:
            historical_locations = df["Location"].dropna().unique().tolist() if not df.empty else []
            default_locations = [""]
            all_locations = list(dict.fromkeys(default_locations + historical_locations))
            location_choice = st.selectbox("赛事地点", ["👇 手动新增地点..."] + all_locations)
            new_location = st.text_input("✍️ 新增地点", placeholder="若不在列表中，请在此输入")
            location = new_location.strip() if new_location.strip() != "" else location_choice
            if location == "👇 手动新增地点...":
                location = "未命名地点"
        
        st.markdown("---")
        st.markdown("#### 💰 资金战果")
        
        col3, col4, col5, col6 = st.columns(4)
        with col3:
            currency = st.selectbox("结算币种", CURRENCIES)
        with col4:
            buy_in = st.number_input("买入 (初始上桌)", min_value=0.0, step=100.0)
        with col5:
            # 锦标赛叫Entries，现金局就理解为买入的子弹数
            entries = st.number_input("买入次数 (子弹数)", min_value=1, value=1, step=1)
        with col6:
            cashed = st.number_input("最终结算 (退桌/奖金)", min_value=0.0, step=100.0)
            
        submitted = st.form_submit_button("🚀 录入并上云", use_container_width=True)
        
        if submitted:
            if "线上" in event_track and not any(kw in location for kw in ["线上", "Online", "online"]):
                location = f"{location} 线上"
                
            profit_raw = cashed - (buy_in * entries)
            profit_cny = profit_raw * rates_cny_base[currency]
            
            # 将 format 插入到上传序列的正确位置
            sheet.append_row([str(date), current_user, game_format, location, float(buy_in), int(entries), float(cashed), currency, float(profit_cny)])
            st.success("✅ 完美！对局记录已安全存入谷歌云端。")
            time.sleep(1.5)
            st.rerun()
