import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
import threading
from sqlalchemy import text, create_engine
from websocket import WebSocketApp

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Live Terminal 2026", layout="wide", page_icon="📈")

# --- 2. SESSION STATE ---
if 'auth' not in st.session_state:
    st.session_state.update({'auth': False, 'company': "", 'map': {}, 'worker_running': False})

# --- 3. DATABASE CONNECTION ---
def get_conn():
    try:
        return st.connection('my_database', type='sql')
    except Exception as e:
        st.error(f"Database Connection Failed: {e}")
        st.stop()

# --- 4. THE BINANCE BACKGROUND WORKER (The "Hidden" Part) ---
def run_binance_stream(company_name, inventory_map):
    """This function runs in a separate thread and saves data to Aiven."""
    # We need a fresh engine for the background thread
    db_url = st.secrets["connections"]["my_database"]["url"]
    engine = create_engine(db_url)

    # Prepare the symbols from your inventory
    symbols = [s.lower() for s in inventory_map.keys()]
    if not symbols:
        return
    
    streams = "/".join([f"{s}@trade" for s in symbols])
    socket_url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    def on_message(ws, message):
        msg_data = json.loads(message)['data']
        symbol = msg_data['s'].lower()
        price = float(msg_data['p'])
        category = inventory_map.get(symbol, "General")

        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO REALTIME_PURCHASES (PRODUCT_ID, REVENUE, REGION) 
                VALUES (:s, :p, :r)
            """), {"s": symbol, "p": price, "r": category})

    ws = WebSocketApp(socket_url, on_message=on_message)
    ws.run_forever()

# --- 5. AUTHENTICATION ---
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
                    st.rerun()
                else:
                    st.error("Invalid Credentials")
    
    with tab2:
        with st.form("signup_form"):
            n = st.text_input("New Company Name")
            p = st.text_input("Set Password", type="password")
            if st.form_submit_button("Register"):
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, CATEGORY_MAP) VALUES (:n, :p, '{}')"), 
                              {"n": n, "p": p})
                    s.commit()
                st.success("Registered! Login now.")

# --- 6. THE MAIN DASHBOARD ---
else:
    # START THE THREAD if it's not already running
    if not st.session_state.worker_running:
        thread = threading.Thread(
            target=run_binance_stream, 
            args=(st.session_state.company, st.session_state.map),
            daemon=True # Important: kills the thread when the app closes
        )
        thread.start()
        st.session_state.worker_running = True

    with st.sidebar:
        st.markdown(f"## 🏢 {st.session_state.company}")
        
        with st.expander("➕ Add Inventory"):
            new_cat = st.text_input("Category Name")
            new_prods = st.text_area("Symbols (SOLUSDT, XRPUSDT)")
            if st.button("Add & Restart Feed"):
                added = {p.strip().lower(): new_cat.strip() for p in new_prods.split(',')}
                st.session_state.map.update(added)
                with get_conn().session as s:
                    s.execute(text("UPDATE CLIENT_CONFIG SET CATEGORY_MAP=:m WHERE COMPANY_NAME=:c"), 
                              {"m": json.dumps(st.session_state.map), "c": st.session_state.company})
                    s.commit()
                # Flip the switch to restart the thread on next rerun
                st.session_state.worker_running = False 
                st.rerun()

        if st.button("🔓 Logout"):
            st.session_state.auth = False
            st.session_state.worker_running = False
            st.rerun()

    # --- MAIN VIEW (Visuals preserved) ---
    st.title("📊 Live Market Terminal")
    metric_area = st.empty()
    col1, col2 = st.columns(2)
    p1_placeholder = col1.empty()
    
    with col2:
        available_cats = sorted(list(set(st.session_state.map.values()))) if st.session_state.map else ["No Inventory"]
        selected_cat = st.selectbox("Filter Category:", available_cats)
        p2_placeholder = st.empty()

    table_placeholder = st.empty()

    # --- DATA REFRESH LOOP ---
    while True:
        try:
            df = get_conn().query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 100", ttl=0)
            if not df.empty:
                with metric_area.container():
                    m1, m2 = st.columns(2)
                    m1.metric("Total Session Volume", f"${df['REVENUE'].sum():,.2f}")
                    m2.metric("Latest Trade", f"{df['PRODUCT_ID'].iloc[0].upper()}")

                fig1 = px.pie(df, names='REGION', values='REVENUE', hole=0.4, template="plotly_dark")
                p1_placeholder.plotly_chart(fig1, use_container_width=True)

                filtered_df = df[df['REGION'] == selected_cat]
                if not filtered_df.empty:
                    fig2 = px.pie(filtered_df, names='PRODUCT_ID', values='REVENUE', hole=0.4, template="plotly_dark")
                    p2_placeholder.plotly_chart(fig2, use_container_width=True)
                
                table_placeholder.dataframe(df, use_container_width=True, hide_index=True)
            
            time.sleep(5)
            st.rerun() 
        except Exception as e:
            st.error(f"Feed error: {e}")
            break
