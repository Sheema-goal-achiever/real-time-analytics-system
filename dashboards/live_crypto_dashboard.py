import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import time
import json
import sys
import os
from sqlalchemy import text

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Live Terminal 2026", layout="wide", page_icon="📈")

# --- 2. SESSION STATE ---
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'company': "", 'map': {}, 'proc': None})

# --- 3. DATABASE CONNECTION ---
def get_conn():
    try:
        # Matches your Secret: [connections.my_database]
        return st.connection('my_database', type='sql')
    except Exception as e:
        st.error(f"Database Connection Failed: {e}")
        st.stop()

def manage_pipeline(action="start"):
    """Handles the background Binance worker process."""
    # 1. Kill existing process if it exists
    if st.session_state.proc is not None:
        st.session_state.proc.terminate()
        st.session_state.proc.wait()
        st.session_state.proc = None
    
    # 2. Start fresh if requested
    if action == "start":
        try:
            # sys.executable ensures it uses the same environment as the dashboard
            st.session_state.proc = subprocess.Popen(
                [sys.executable, "test_ws.py"],
                env=os.environ.copy()
            )
            st.sidebar.success("🚀 Data Pipeline Active")
        except Exception as e:
            st.sidebar.error(f"Pipeline Error: {e}")

# --- 4. AUTHENTICATION ---
if not st.session_state.auth:
    tab1, tab2 = st.tabs(["🔐 Login", "🚀 Register"])
    with tab1:
        with st.form("login_form"):
            u_in = st.text_input("Company Name")
            p_in = st.text_input("Password", type="password")
            if st.form_submit_button("Enter Terminal"):
                conn = get_conn()
                res = conn.query("SELECT * FROM CLIENT_CONFIG WHERE COMPANY_NAME=:u AND PASSWORD=:p", 
                                 params={"u":u_in, "p":p_in}, ttl=0)
                if not res.empty:
                    st.session_state.auth = True
                    st.session_state.company = res.iloc[0]['COMPANY_NAME']
                    raw_map = res.iloc[0]['CATEGORY_MAP']
                    st.session_state.map = json.loads(raw_map) if isinstance(raw_map, str) else raw_map
                    manage_pipeline("start") # Start worker on login
                    st.rerun()
                else:
                    st.error("Invalid Credentials")
    with tab2:
        with st.form("signup_form"):
            n = st.text_input("New Company Name")
            p = st.text_input("Set Password", type="password")
            url = st.text_input("Binance URL", value="wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/solusdt@trade")
            if st.form_submit_button("Register"):
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, DATA_SOURCE_URL, CATEGORY_MAP) VALUES (:n, :p, :u, '{}')"), 
                              {"n": n, "p": p, "u": url})
                    s.commit()
                st.success("Registered! Login now.")

# --- 5. THE MAIN DASHBOARD ---
else:
    with st.sidebar:
        st.markdown(f"## 🏢 {st.session_state.company}")
        
        # --- ADD INVENTORY ---
        with st.expander("➕ Add Inventory"):
            new_cat = st.text_input("Category Name (e.g., L1, Meme)")
            new_prods = st.text_area("Symbols (e.g., SOLUSDT, XRPUSDT)")
            if st.button("Add & Restart Pipeline"):
                if new_cat and new_prods:
                    added = {p.strip().lower(): new_cat.strip() for p in new_prods.split(',')}
                    st.session_state.map.update(added)
                    with get_conn().session as s:
                        s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"), 
                                  {"m": json.dumps(st.session_state.map), "c": st.session_state.company})
                        s.commit()
                    manage_pipeline("start") # Restarts worker with new coins
                    st.rerun()

        # --- DELETE INVENTORY ---
        with st.expander("🗑️ Delete Inventory"):
            current_coins = list(st.session_state.map.keys())
            to_del = st.multiselect("Select to remove:", current_coins)
            if st.button("Delete & Restart"):
                for coin in to_del: del st.session_state.map[coin]
                with get_conn().session as s:
                    s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"), 
                              {"m": json.dumps(st.session_state.map), "c": st.session_state.company})
                    s.commit()
                manage_pipeline("start") # Restarts worker
                st.rerun()

        # --- DANGER ZONE ---
        with st.expander("🚨 Danger Zone"):
            if st.button("Truncate Table (Wipe Data)"):
                with get_conn().session as s:
                    s.execute(text("TRUNCATE TABLE REALTIME_PURCHASES"))
                    s.commit()
                st.rerun()

        if st.button("🔓 Logout"):
            manage_pipeline("stop")
            st.session_state.update({'auth': False, 'proc': None})
            st.rerun()

    # --- MAIN VIEW ---
    st.title("📊 Live Market Terminal")
    
    metric_area = st.empty()
    col1, col2 = st.columns(2)
    p1_placeholder = col1.empty()
    
    with col2:
        available_cats = sorted(list(set(st.session_state.map.values()))) if st.session_state.map else ["No Inventory"]
        selected_cat = st.selectbox("Filter Category:", available_cats)
        p2_placeholder = st.empty()

    table_placeholder = st.empty()

    # --- THE LIVE LOOP ---
    # Using a fragments approach or a simple loop for real-time feel
    while True:
        try:
            df = get_conn().query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 100", ttl=0)

            if not df.empty:
                with metric_area.container():
                    m1, m2 = st.columns(2)
                    m1.metric("Total Session Volume", f"${df['REVENUE'].sum():,.2f}")
                    m2.metric("Latest Trade", f"{df['PRODUCT_ID'].iloc[0].upper()}")

                # Chart 1: Market Share
                fig1 = px.pie(df, names='REGION', values='REVENUE', hole=0.4, template="plotly_dark")
                p1_placeholder.plotly_chart(fig1, use_container_width=True)

                # Chart 2: Category Assets
                filtered_df = df[df['REGION'] == selected_cat]
                if not filtered_df.empty:
                    fig2 = px.pie(filtered_df, names='PRODUCT_ID', values='REVENUE', hole=0.4, template="plotly_dark")
                    p2_placeholder.plotly_chart(fig2, use_container_width=True)
                
                table_placeholder.dataframe(df, use_container_width=True, hide_index=True)
            
            time.sleep(5)
            st.rerun() # Refresh the UI with new DB data
            
        except Exception as e:
            st.error(f"Display Error: {e}")
            break
