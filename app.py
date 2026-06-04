import streamlit as st
import pandas as pd
import datetime
import requests
import json
import gspread
from google.oauth2.service_account import Credentials

# ================= 1. 页面基础配置 =================
st.set_page_config(page_title="Jelly Poker Tracker", page_icon="🃏", layout="wide")


# ================= 1.5 极简私人密码锁 =================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center; margin-top: 100px;'>🔒 Jelly Poker 私人金库</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("请输入访问密码", type="password", placeholder="输入暗号后按回车 ↵")
        if pwd:
            # 去保险柜里核对密码
            if pwd == st.secrets["app_password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 密码错误，非法入侵！")
    # 如果没登录，直接切断程序，后面的代码全都不运行
    st.stop()
CURRENCIES = ["CNY", "USD", "AUD", "VND", "KRW"]

# ================= 1.5 极简私人密码锁 =================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center; margin-top: 100px;'>🔒 Jelly Poker </h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("请输入访问密码", type="password", placeholder="输入暗号后按回车 ↵")
        if pwd:
            if pwd == st.secrets.get("app_password", ""): # 确保你在 Secrets 里设置了 app_password
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ 密码错误，非法入侵！")
    st.stop()

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
    st.error(f"⚠️ 真正的报错原因是: {str(e)}")
    st.stop()

records = sheet.get_all_records()
if not records:
    # 表头加入了 Player
    df = pd.DataFrame(columns=["Date", "Player", "Location", "Buy_in", "Entries", "Cashed", "Currency", "Profit_CNY"])
else:
    df = pd.DataFrame(records)
records = sheet.get_all_records()
if not records:
    df = pd.DataFrame(columns=["Date", "Player", "Location", "Buy_in", "Entries", "Cashed", "Currency", "Profit_CNY"])
else:
    df = pd.DataFrame(records)
    
    # === 新增修复代码：强制将涉及金额和次数的列转换为数字类型 ===
    numeric_columns = ["Buy_in", "Entries", "Cashed", "Profit_CNY"]
    for col in numeric_columns:
        if col in df.columns:
            # pd.to_numeric 会把文本变成真正的数字，errors='coerce' 会把乱码变成空值，fillna(0) 把空值填成 0
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    # ==========================================================
# 提取当前已有的所有玩家名字，去重并过滤空值
existing_players = df["Player"].dropna().unique().tolist() if "Player" in df.columns else []

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

# ================= 4. 侧边栏：玩家筛选、汇率 & 计算器 =================
st.sidebar.markdown("## 👥 数据视图")
player_filter = st.sidebar.selectbox("查看谁的战绩？", ["⭐ 全部玩家 (团队总览)"] + existing_players)

st.sidebar.markdown("---")
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
with st.sidebar.container(border=True):
    calc_expr = st.text_input("算式输入", value="", placeholder="(1500+200)/3", label_visibility="collapsed")
    if calc_expr:
        allowed_chars = set("0123456789+-*/.() ")
        if set(calc_expr).issubset(allowed_chars):
            try:
                result = eval(calc_expr)
                st.success(f"### = {result:,.2f}")
            except Exception:
                st.error("❌ 算式有误")

# ================= 5. 主体内容 (双标签页) =================
st.title("🃏 Jelly Poker Dashboard")
st.markdown("---")

tab_dashboard, tab_entry = st.tabs(["📈 数据看板 (Dashboard)", "➕ 录入赛事 (New Entry)"])

# ----------------- 标签页 A：录入表单 -----------------
with tab_entry:
    st.markdown("### 📝 记录新赛事")
    with st.form("add_tournament_form", clear_on_submit=True):
        
        # 第一排：时间与玩家
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            date = st.date_input("比赛时间", datetime.date.today())
        with col_p2:
            default_players = ["Jelly"]
            all_players_options = list(dict.fromkeys(default_players + existing_players))
            player_choice = st.selectbox("玩家 (下拉选择)", ["👇 手动新增玩家..."] + all_players_options)
            new_player = st.text_input("✍️ 新增玩家 (打字自动覆盖上方选择)")
            
            final_player = new_player.strip() if new_player.strip() != "" else player_choice
            if final_player == "👇 手动新增玩家...":
                final_player = "未知玩家"
                
        # 第二排：地点与币种买入
        col1, col2 = st.columns(2)
        with col1:
            historical_locations = df["Location"].dropna().unique().tolist() if not df.empty else []
            default_locations = ["GGPoker 线上"]
            all_locations = list(dict.fromkeys(default_locations + historical_locations))
            
            location_choice = st.selectbox("赛事地点", ["👇 手动新增地点..."] + all_locations)
            new_location = st.text_input("✍️ 新增地点")
            
            location = new_location.strip() if new_location.strip() != "" else location_choice
            if location == "👇 手动新增地点...":
                location = "未命名地点"
                
        with col2:
            currency = st.selectbox("结算币种", CURRENCIES)
            buy_in = st.number_input("单次买入价格", min_value=0.0, step=100.0)
            
        # 第三排：赛果
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
            
            # 推送数据时，包含 Player 列
            sheet.append_row([str(date), final_player, location, float(buy_in), int(entries), float(cashed), currency, float(profit_cny)])
            st.success(f"✅ 成功记录！[{final_player}] 该场净利润: ¥{profit_cny:,.2f} CNY")
            st.rerun()

# ----------------- 标签页 B：数据看板与编辑表 -----------------
with tab_dashboard:
    if not df.empty:
        # 核心筛选逻辑：根据左侧边栏的选择过滤数据
        if player_filter == "⭐ 全部玩家 (团队总览)":
            display_df = df.copy()
            chart_title = "📈 团队资金波动总曲线 (RMB)"
        else:
            display_df = df[df["Player"] == player_filter].copy()
            chart_title = f"📈 {player_filter} 的个人资金波动曲线 (RMB)"
            
        if not display_df.empty:
            total_profit_cny = display_df["Profit_CNY"].sum()
            total_tourneys = len(display_df)
            itm_count = len(display_df[display_df["Cashed"] > 0])
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
            
            # 图表渲染
            st.markdown(f"### {chart_title}")
            df_sorted = display_df.sort_values(by="Date").reset_index(drop=True)
            # 每天汇总合并（防止同一天多场比赛导致折线回退倒置）
            df_daily = df_sorted.groupby("Date")["Profit_CNY"].sum().reset_index()
            df_daily["Cumulative_Profit"] = df_daily["Profit_CNY"].cumsum()
            
            chart_data = df_daily.set_index("Date")[["Cumulative_Profit"]]
            st.line_chart(chart_data, color="#29b5e8")
            
        else:
            st.warning(f"📭 暂无 {player_filter} 的比赛数据。")

        # 无论筛选谁，下方始终展示完整互动表格供编辑
        st.markdown("### 📋 完整历史详细记录 (✏️ 双击修改，选中行删除)")
        edited_df = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",  
            hide_index=True,
            disabled=["Profit_CNY"] 
        )
        
        if st.button("💾 确认并覆盖保存修改至云端", type="primary"):
            def recalc_profit(row):
                # 加入防错机制，确保格式正确
                try:
                    total_invested = float(row['Buy_in']) * int(row['Entries'])
                    profit_raw = float(row['Cashed']) - total_invested
                    return profit_raw * rates_cny_base[row['Currency']]
                except:
                    return 0
                
            edited_df['Profit_CNY'] = edited_df.apply(recalc_profit, axis=1)
            
            sheet.clear()
            updated_data = [edited_df.columns.values.tolist()] + edited_df.values.tolist()
            sheet.update(values=updated_data, range_name="A1")
            st.success("✅ 数据修改已成功覆盖并同步！")
            st.rerun()
            
    else:
        st.info("👋 欢迎来到 Jelly Poker Dashboard！请录入第一场比赛。")
