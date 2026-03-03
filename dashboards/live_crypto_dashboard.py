import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
import threading
from sqlalchemy import text, create_engine
from websocket import WebSocketApp

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Analytics 2026", layout="wide", page_icon="📈")

# --- 2. AUTO-DATABASE FIX (Fixes the WS_URL Column Error) ---
def fix_database_schema():
    conn = st.connection('my_database', type='sql')
    try:
        with conn.session as s:
            # Adds the column if it doesn't exist to prevent the 'Unknown column' error
            s.execute(text("ALTER TABLE CLIENT_CONFIG ADD COLUMN IF NOT EXISTS WS_URL TEXT"))
            s.commit()
    except Exception:
        pass

fix_database_schema()

# --- 3. SESSION STATE ---
if 'auth' not in st.session_state:
    st.session_state.update({
        'auth': False, 'company': "", 'map': {}, 'ws_url': "", 'worker_started': False
    })

# --- 4. THE BACKGROUND WORKER ---
def run_custom_stream(ws_url, inventory_map):
    try:
        db_url = st.secrets["connections"]["my_database"]["url"]
        engine = create_engine(db_url, pool_pre_ping=True)
        
        # Prepare symbols for Binance format
        symbols = [s.strip().lower() for s in inventory_map.keys()]
        streams = "/".join([f"{s}@trade" for s in symbols])
        
        # Build the full stream URL
        if "binance.com" in ws_url and "streams=" not in ws_url:
            socket_url = f"{ws_url.rstrip('/')}/stream?streams={streams}"
        else:
            socket_url = ws_url

        def on_message(ws, message):
            msg_json = json.loads(message)
            data = msg_json.get('data', msg_json)
            
            # CASE CORRECTION: Force symbols to lowercase for mapping match
            raw_symbol = data.get('s', '').lower()
            price = float(data.get('p', 0))
            
            # Lookup category (e.g., 'Majors' or 'Alts') from the map
            category = inventory_map.get(raw_symbol, "Uncategorized")
            
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO REALTIME_PURCHASES (PRODUCT_ID, REVENUE, REGION) 
                    VALUES (:s, :p, :r)
                """), {"s": raw_symbol, "p": price, "r": category})

        ws = WebSocketApp(socket_url, on_message=on_message)
        ws.run_forever()
    except Exception:
        pass

def start_worker():
    # Ensure only one worker thread runs per session
    for t in threading.enumerate():
        if t.name == "CompanyWorker": return 
    if st.session_state.ws_url and st.session_state.map:
        t = threading.Thread(target=run_custom_stream, 
                             args=(st.session_state.ws_url, st.session_state.map), 
                             name="CompanyWorker", daemon=True)
        t.start()
        st.session_state.worker_started = True

# --- 5. AUTH & SIGNUP ---
if not st.session_state.auth:
    st.title("🔐 Terminal Gateway")
    tab1, tab2 = st.tabs(["Login", "🚀 Register New Company"])
    
    with tab1:
        with st.form("login_form"):
            u_in, p_in = st.text_input("Company Name"), st.text_input("Password", type="password")
            if st.form_submit_button("Enter Terminal", width='stretch'):
                res = st.connection('my_database', type='sql').query(
                    "SELECT * FROM CLIENT_CONFIG WHERE COMPANY_NAME=:u AND PASSWORD=:p", 
                    params={"u":u_in, "p":p_in}, ttl=0
                )
                if not res.empty:
                    st.session_state.auth = True
                    st.session_state.company = res.iloc[0]['COMPANY_NAME']
                    st.session_state.ws_url = res.iloc[0]['WS_URL'] or "wss://stream.binance.com:9443"
                    st.session_state.map = json.loads(res.iloc[0]['CATEGORY_MAP'])
                    st.rerun()
                else: st.error("Invalid Credentials")

    with tab2:
        with st.form("signup_form"):
            st.subheader("Company Credentials")
            new_n = st.text_input("Company Name")
            new_p = st.text_input("Password", type="password")
            ws_end = st.text_input("WebSocket URL", value="wss://stream.binance.com:9443")
            
            st.subheader("Inventory Setup")
            c_name = st.text_input("Category Name (e.g., Majors)")
            p_names = st.text_input("Product Symbols (e.g., btcusdt, ethusdt)")
            
            if st.form_submit_button("Create Account", width='stretch'):
                # Split comma-separated names into individual map keys
                f_map = {s.strip().lower(): c_name.strip() for s in p_names.split(',')} if p_names else {}
                
                with st.connection('my_database', type='sql').session as s:
                    s.execute(text("""
                        INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, CATEGORY_MAP, WS_URL) 
                        VALUES (:n, :p, :m, :w)
                    """), {"n": new_n, "p": new_p, "m": json.dumps(f_map), "w": ws_end})
                    s.commit()
                st.success("Registration Successful! Now go to the Login tab.")

# --- 6. MAIN DASHBOARD ---
else:
    start_worker()
    with st.sidebar:
        st.header(f"🏢 {st.session_state.company}")
        
        with st.expander("➕ Add Inventory"):
            add_cat = st.text_input("Category Name (e.g., Alts)")
            add_prods = st.text_area("Product Name(s) (e.g., solusdt, xrpbusd)")
            if st.button("Save to Inventory", width='stretch'):
                for s_item in add_prods.split(','):
                    st.session_state.map[s_item.strip().lower()] = add_cat.strip()
                with st.connection('my_database', type='sql').session as s:
                    s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"),
                              {"m": json.dumps(st.session_state.map), "c": st.session_state.company})
                    s.commit()
                st.rerun()

        st.divider()
        # TRUNCATE resets the table and clears "Uncategorized" data
        if st.button("🧨 Truncate Table (Reset Data)", width='stretch'):
            with st.connection('my_database', type='sql').session as s:
                s.execute(text("TRUNCATE TABLE REALTIME_PURCHASES"))
                s.commit()
            st.rerun()

        if st.button("🔓 Logout", width='stretch'):
            st.session_state.auth = False
            st.rerun()

    # --- ANALYTICS ---
    st.title("📊 Real-Time Market Analytics")
    df = st.connection('my_database', type='sql').query(
        "SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 200", ttl=0
    )

    if not df.empty:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Market Segment Volume")
            # Pulls from 'REGION' column which stores your custom Categories
            st.plotly_chart(px.pie(df, names='REGION', values='REVENUE', hole=0.5, template="plotly_dark"), width='stretch')
        with c2:
            st.subheader("Asset Drill-Down")
            sel_cat = st.selectbox("Filter Chart by Category", options=df['REGION'].unique())
            sub_df = df[df['REGION'] == sel_cat]
            st.plotly_chart(px.pie(sub_df, names='PRODUCT_ID', values='REVENUE', hole=0.3, template="plotly_dark"), width='stretch')
        
        st.dataframe(df, width='stretch', hide_index=True)
    else:
        st.info("Live feed active. Waiting for trades...")

    time.sleep(4)
    st.rerun()
