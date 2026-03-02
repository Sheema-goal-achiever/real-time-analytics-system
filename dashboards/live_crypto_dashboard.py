import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import time
import json
import sys
from sqlalchemy import text

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Live Terminal", layout="wide", page_icon="📈")

# --- 2. SESSION STATE ---
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'company': "", 'map': {}, 'proc': None})

# --- 3. DATABASE CONNECTION ---
def get_conn():
    try:
        return st.connection('my_database', type='sql')
    except:
        url = "mysql+mysqlconnector://root:Sheema%40123@localhost:3306/real_time_analytics"
        return st.connection("backup_db", type="sql", url=url)

def start_ingester():
    """Launches test_ws.py in the background"""
    if st.session_state.proc is None:
        try:
            st.session_state.proc = subprocess.Popen([sys.executable, "test_ws.py"])
        except Exception as e:
            st.error(f"Failed to start pipeline: {e}")

# --- 4. AUTHENTICATION UI ---
if not st.session_state.auth:
    tab1, tab2 = st.tabs(["🔐 Login", "🚀 Register"])
    
    with tab1:
        st.header("Login")
        with st.form("login_form"):
            u_in = st.text_input("Company Name")
            p_in = st.text_input("Password", type="password")
            if st.form_submit_button("Enter"):
                conn = get_conn()
                res = conn.query("SELECT COMPANY_NAME, CATEGORY_MAP FROM CLIENT_CONFIG WHERE COMPANY_NAME=:u AND PASSWORD=:p", params={"u":u_in, "p":p_in}, ttl=0)
                if not res.empty:
                    st.session_state.auth = True
                    st.session_state.company = res.iloc[0]['COMPANY_NAME']
                    raw_map = res.iloc[0]['CATEGORY_MAP']
                    st.session_state.map = json.loads(raw_map) if isinstance(raw_map, str) else raw_map
                    start_ingester()
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab2:
        st.header("Register")
        with st.form("signup_form"):
            n = st.text_input("New Company Name")
            p = st.text_input("Set Password", type="password")
            url = st.text_input("WebSocket URL", value="wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade/adausdt@trade/dogeusdt@trade")
            cat = st.text_input("Initial Category", value="Majors")
            prods = st.text_area("Products (BTCUSDT, ETHUSDT)")
            if st.form_submit_button("Create Account"):
                mapping = {prod.strip().upper(): cat.strip() for prod in prods.split(',')}
                conn = get_conn()
                ins = text("INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, DATA_SOURCE_URL, CATEGORY_MAP) VALUES (:n, :p, :u, :m)")
                with conn.session as s:
                    s.execute(ins, {"n": n, "p": p, "u": url, "m": json.dumps(mapping)})
                    s.commit()
                st.success("✅ Registered! Switch to Login.")

# --- 5. MAIN DASHBOARD ---
else:
    # --- SIDEBAR (Static - No Flickering) ---
    st.sidebar.markdown(f"## 🏢 {st.session_state.company}")
    st.sidebar.divider()

    with st.sidebar.expander("➕ Add Category / Products", expanded=False):
        new_cat = st.text_input("Category (e.g., Alts)")
        new_prods = st.text_area("Products (SOLUSDT, XRPUSDT, DOGEUSDT)")
        if st.button("Update Inventory"):
            if new_cat and new_prods:
                new_items = {p.strip().upper(): new_cat.strip() for p in new_prods.split(',')}
                full_map = {**st.session_state.map, **new_items}
                
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"), 
                              {"m": json.dumps(full_map), "c": st.session_state.company})
                    s.commit()
                
                st.session_state.map = full_map
                
                if st.session_state.proc:
                    st.session_state.proc.terminate()
                    st.session_state.proc = None
                time.sleep(1)
                start_ingester()
                st.sidebar.success("Restarting Pipeline...")
                st.rerun()

    st.sidebar.markdown("<div style='height: 50vh'></div>", unsafe_allow_html=True)
    if st.sidebar.button("🔓 Logout", use_container_width=True):
        if st.session_state.proc: st.session_state.proc.terminate()
        st.session_state.update({'auth': False, 'proc': None})
        st.rerun()

    # --- LIVE DATA FRAGMENT (Auto-updates without flickering) ---
    st.title(f"📊 {st.session_state.company} Live Terminal")

    @st.fragment(run_every=2)
    def show_live_updates():
        conn = get_conn()
        df = conn.query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 1000", ttl=0)

        if not df.empty:
            # Metrics
            m1, m2 = st.columns(2)
            m1.metric("Total Session Revenue", f"${df['REVENUE'].sum():,.2f}")
            m2.metric("Active Streams", len(df['PRODUCT_ID'].unique()))

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📁 Revenue by Category")
                st.plotly_chart(px.pie(df, names='REGION', values='REVENUE', hole=0.4, template="plotly_dark"), use_container_width=True)
            with col2:
                st.subheader("🪙 Product Breakdown")
                cats = df['REGION'].unique()
                sel_cat = st.selectbox("View products in:", cats)
                st.plotly_chart(px.pie(df[df['REGION'] == sel_cat], names='PRODUCT_ID', values='REVENUE', hole=0.4, template="plotly_dark"), use_container_width=True)
            
            st.subheader("📜 Live Ledger")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("🔄 Pipeline active. Waiting for trade data...")

    show_live_updates()