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
    if st.session_state.proc is None:
        try:
            st.session_state.proc = subprocess.Popen([sys.executable, "test_ws.py"])
        except Exception as e:
            st.error(f"Failed to start pipeline: {e}")

# --- 4. AUTHENTICATION ---
if not st.session_state.auth:
    tab1, tab2 = st.tabs(["🔐 Login", "🚀 Register"])
    with tab1:
        with st.form("login_form"):
            u_in = st.text_input("Company Name")
            p_in = st.text_input("Password", type="password")
            if st.form_submit_button("Enter Terminal"):
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
        with st.form("signup_form"):
            n = st.text_input("New Company Name")
            p = st.text_input("Set Password", type="password")
            url = st.text_input("Binance URL", value="wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/solusdt@trade/xrpusdt@trade/adausdt@trade/dogeusdt@trade")
            cat, prods = st.text_input("Category", "Majors"), st.text_area("Products", "BTCUSDT, ETHUSDT")
            if st.form_submit_button("Register"):
                mapping = {prod.strip().upper(): cat.strip() for prod in prods.split(',')}
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, DATA_SOURCE_URL, CATEGORY_MAP) VALUES (:n, :p, :u, :m)"), 
                              {"n": n, "p": p, "u": url, "m": json.dumps(mapping)})
                    s.commit()
                st.success("Registered! Go to Login.")

# --- 5. THE DASHBOARD ---
else:
    st.sidebar.markdown(f"## 🏢 {st.session_state.company}")
    
    with st.sidebar.expander("➕ Add Inventory"):
        nc = st.text_input("Category Name")
        np = st.text_area("Product List")
        if st.button("Update Inventory"):
            new_m = {**st.session_state.map, **{p.strip().upper(): nc.strip() for p in np.split(',')}}
            conn = get_conn()
            with conn.session as s:
                s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"), {"m": json.dumps(new_m), "c": st.session_state.company})
                s.commit()
            if st.session_state.proc: st.session_state.proc.terminate()
            st.session_state.proc = None
            time.sleep(1)
            start_ingester()
            st.rerun()

    if st.sidebar.button("🔓 Logout", width="stretch"):
        if st.session_state.proc: st.session_state.proc.terminate()
        st.session_state.update({'auth': False, 'proc': None})
        st.rerun()

    st.title(f"📊 {st.session_state.company} Live Terminal")
    
    metric_area = st.empty()
    col1, col2 = st.columns(2)
    pie1_placeholder = col1.empty()
    pie2_placeholder = col2.empty()
    table_placeholder = st.empty()

    while True:
        conn = get_conn()
        df = conn.query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 100", ttl=0)

        if not df.empty:
            with metric_area.container():
                m1, m2 = st.columns(2)
                m1.metric("Total Session Revenue", f"${df['REVENUE'].sum():,.2f}")
                m2.metric("Latest Symbol", df['PRODUCT_ID'].iloc[0])

            fig1 = px.pie(df, names='REGION', values='REVENUE', hole=0.4, template="plotly_dark", title="Revenue by Category")
            # UPDATED: width="stretch"
            pie1_placeholder.plotly_chart(fig1, width="stretch", key="cat_pie")

            cats = df['REGION'].unique()
            fig2 = px.pie(df[df['REGION'] == cats[0]], names='PRODUCT_ID', values='REVENUE', hole=0.4, template="plotly_dark", title=f"Assets in {cats[0]}")
            # UPDATED: width="stretch"
            pie2_placeholder.plotly_chart(fig2, width="stretch", key="prod_pie")

            # UPDATED: width="stretch"
            table_placeholder.dataframe(df, width="stretch", hide_index=True)

        time.sleep(10)