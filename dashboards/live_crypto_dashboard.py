import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
import threading
import os
from sqlalchemy import text, create_engine
from websocket import WebSocketApp

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Live Terminal 2026", layout="wide", page_icon="📈")

# --- 2. SESSION STATE (Bulletproof Initialization) ---
# This prevents the AttributeError by ensuring keys always exist
if 'auth' not in st.session_state:
    st.session_state.auth = False
if 'company' not in st.session_state:
    st.session_state.company = ""
if 'map' not in st.session_state:
    st.session_state.map = {}
if 'worker_running' not in st.session_state:
    st.session_state.worker_running = False

# --- 3. DATABASE CONNECTION ---
def get_conn():
    try:
        # Matches your Streamlit Secrets: [connections.my_database]
        return st.connection('my_database', type='sql')
    except Exception as e:
        st.error(f"Database Connection Failed: {e}")
        st.stop()

# --- 4. THE BACKGROUND WORKER (Replaces test_ws.py) ---
def run_binance_stream(inventory_map):
    """Background thread function to fetch Binance trades and save to Aiven."""
    try:
        # Get URL directly from secrets for the background engine
        db_url = st.secrets["connections"]["my_database"]["url"]
        engine = create_engine(db_url)

        symbols = [s.lower() for s in inventory_map.keys()]
        if not symbols:
            return
        
        # Build the Binance stream URL
        streams = "/".join([f"{s}@trade" for s in symbols])
        socket_url = f"wss://stream.binance.com:9443/stream?streams={streams}"

        def on_message(ws, message):
            msg_json = json.loads(message)
            data = msg_json['data']
            symbol = data['s'].lower()
            price = float(data['p'])
            category = inventory_map.get(symbol, "General Assets")

            # Write to Aiven MySQL
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO REALTIME_PURCHASES (PRODUCT_ID, REVENUE, REGION) 
                    VALUES (:s, :p, :r)
                """), {"s": symbol, "p": price, "r": category})

        def on_error(ws, error):
            pass # Silent fail to prevent console clutter

        ws = WebSocketApp(socket_url, on_message=on_message, on_error=on_error)
        ws.run_forever()
    except Exception:
        pass # Thread safety

# --- 5. AUTHENTICATION ---
if not st.session_state.auth:
    st.title("🔐 Secure Terminal Login")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            u_in = st.text_input("Company Name")
            p_in = st.text_input("Password", type="password")
            if st.form_submit_button("Access Data", use_container_width=True):
                conn = get_conn()
                res = conn.query("SELECT * FROM CLIENT_CONFIG WHERE COMPANY_NAME=:u AND PASSWORD=:p", 
                                 params={"u":u_in, "p":p_in}, ttl=0)
                if not res.empty:
                    st.session_state.auth = True
                    st.session_state.company = res.iloc[0]['COMPANY_NAME']
                    raw_map = res.iloc[0]['CATEGORY_MAP']
                    # Handle JSON format from Aiven
                    st.session_state.map = json.loads(raw_map) if isinstance(raw_map, str) else raw_map
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab2:
        with st.form("signup_form"):
            n = st.text_input("New Company Name")
            p = st.text_input("Set Password", type="password")
            if st.form_submit_button("Create Account", use_container_width=True):
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, CATEGORY_MAP) VALUES (:n, :p, '{}')"), 
                              {"n": n, "p": p})
                    s.commit()
                st.success("Account Ready! Please Login.")

# --- 6. THE MAIN DASHBOARD ---
else:
    # START BACKGROUND THREAD (Only once)
    if not st.session_state.worker_running and st.session_state.map:
        thread = threading.Thread(
            target=run_binance_stream, 
            args=(st.session_state.map,),
            daemon=True 
        )
        thread.start()
        st.session_state.worker_running = True

    # SIDEBAR MANAGEMENT
    with st.sidebar:
        st.header(f"🏢 {st.session_state.company}")
        st.status("Live Feed Active" if st.session_state.worker_running else "Feed Offline", state="complete")
        
        with st.expander("➕ Add Inventory"):
            new_cat = st.text_input("Category")
            new_prods = st.text_area("Symbols (SOLUSDT, BTCUSDT)")
            if st.button("Sync & Restart"):
                if new_cat and new_prods:
                    added = {p.strip().lower(): new_cat.strip() for p in new_prods.split(',')}
                    st.session_state.map.update(added)
                    with get_conn().session as s:
                        s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"), 
                                  {"m": json.dumps(st.session_state.map), "c": st.session_state.company})
                        s.commit()
                    st.session_state.worker_running = False # Force restart on next loop
                    st.rerun()

        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.auth = False
            st.session_state.worker_running = False
            st.rerun()

    # DASHBOARD VISUALS
    st.title("🚀 Real-Time Market Analytics")
    
    metric_area = st.empty()
    col1, col2 = st.columns(2)
    p1_placeholder = col1.empty()
    p2_placeholder = col2.empty()
    
    with col2:
        available_cats = sorted(list(set(st.session_state.map.values()))) if st.session_state.map else ["None"]
        selected_cat = st.selectbox("Market Category:", available_cats)

    table_placeholder = st.empty()

    # REFRESH LOOP
    try:
        df = get_conn().query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 100", ttl=0)
        
        if not df.empty:
            with metric_area.container():
                m1, m2 = st.columns(2)
                m1.metric("Total Volume ($)", f"{df['REVENUE'].sum():,.2f}")
                m2.metric("Latest Asset", df['PRODUCT_ID'].iloc[0].upper())

            # Chart 1: Market Share
            fig1 = px.pie(df, names='REGION', values='REVENUE', hole=0.5, template="plotly_dark", title="Global Revenue Share")
            p1_placeholder.plotly_chart(fig1, use_container_width=True)

            # Chart 2: Category Assets
            filtered_df = df[df['REGION'] == selected_cat]
            if not filtered_df.empty:
                fig2 = px.pie(filtered_df, names='PRODUCT_ID', values='REVENUE', template="plotly_dark", title=f"Assets in {selected_cat}")
                p2_placeholder.plotly_chart(fig2, use_container_width=True)
            
            table_placeholder.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Waiting for first trade data from Binance... Make sure you've added Inventory!")

        # Auto-refresh trigger
        time.sleep(4)
        st.rerun()
    except Exception as e:
        st.error(f"UI Update Error: {e}")
