import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
import threading
from websocket import WebSocketApp
from collections import deque

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Analytics 2026", layout="wide", page_icon="📈")

# --- 2. SESSION STATE ---
if 'auth' not in st.session_state:
    st.session_state.update({
        'auth': False,
        'company': "",
        'map': {},
        'ws_url': "wss://stream.binance.com:9443",
        'worker_started': False
    })

# --- 3. IN-MEMORY DATA STORE ---
if "data_store" not in st.session_state:
    st.session_state.data_store = deque(maxlen=1000)

if "users" not in st.session_state:
    st.session_state.users = {}  # fake database

# --- 4. BACKGROUND STREAM WORKER ---
def run_custom_stream(ws_url, inventory_map):
    symbols = [s.strip().lower() for s in inventory_map.keys()]
    streams = "/".join([f"{s}@trade" for s in symbols])

    if "binance.com" in ws_url and "streams=" not in ws_url:
        socket_url = f"{ws_url.rstrip('/')}/stream?streams={streams}"
    else:
        socket_url = ws_url

    def on_message(ws, message):
        msg_json = json.loads(message)
        data = msg_json.get('data', msg_json)

        raw_symbol = data.get('s', '').lower()
        price = float(data.get('p', 0))
        quantity = float(data.get('q', 0))
        revenue = price * quantity
        category = inventory_map.get(raw_symbol, "Uncategorized")

        st.session_state.data_store.append({
            "symbol": raw_symbol,
            "price": price,
            "quantity": quantity,
            "revenue": revenue,
            "region": category
        })

    ws = WebSocketApp(socket_url, on_message=on_message)
    ws.run_forever()


def start_worker():
    if st.session_state.ws_url and st.session_state.map:
        if not st.session_state.worker_started:
            t = threading.Thread(
                target=run_custom_stream,
                args=(st.session_state.ws_url, st.session_state.map),
                daemon=True
            )
            t.start()
            st.session_state.worker_started = True


# --- 5. AUTH SYSTEM (IN-MEMORY) ---
if not st.session_state.auth:
    st.title("🔐 Terminal Gateway (Local Mode)")

    tab1, tab2 = st.tabs(["Login", "🚀 Register New Company"])

    with tab1:
        with st.form("login_form"):
            u_in = st.text_input("Company Name")
            p_in = st.text_input("Password", type="password")

            if st.form_submit_button("Enter Terminal"):
                if u_in in st.session_state.users and st.session_state.users[u_in]["password"] == p_in:
                    st.session_state.auth = True
                    st.session_state.company = u_in
                    st.session_state.ws_url = st.session_state.users[u_in]["ws_url"]
                    st.session_state.map = st.session_state.users[u_in]["map"]
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab2:
        with st.form("signup_form"):
            new_n = st.text_input("Company Name")
            new_p = st.text_input("Password", type="password")
            ws_end = st.text_input("WebSocket URL", value="wss://stream.binance.com:9443")
            c_name = st.text_input("Category (e.g., Majors)")
            p_names = st.text_input("Symbols (e.g., btcusdt, ethusdt)")

            if st.form_submit_button("Create Account"):
                f_map = {s.strip().lower(): c_name.strip() for s in p_names.split(',') if s.strip()}
                st.session_state.users[new_n] = {
                    "password": new_p,
                    "ws_url": ws_end,
                    "map": f_map
                }
                st.success("Registration Successful!")


# --- 6. MAIN DASHBOARD ---
else:
    start_worker()

    with st.sidebar:
        st.header(f"🏢 {st.session_state.company}")

        with st.expander("➕ Add Inventory"):
            add_cat = st.text_input("Category Name")
            add_prods = st.text_area("Product Symbols")

            if st.button("Save"):
                for s_item in add_prods.split(','):
                    st.session_state.map[s_item.strip().lower()] = add_cat.strip()
                st.rerun()

        st.divider()

        if st.button("🧨 Clear Data"):
            st.session_state.data_store.clear()
            st.rerun()

        if st.button("🔓 Logout"):
            st.session_state.auth = False
            st.rerun()


    # --- ANALYTICS ---
    st.title("📊 Real-Time Market Analytics")

    df = pd.DataFrame(list(st.session_state.data_store))

    if not df.empty:
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Market Segment Volume")
            st.plotly_chart(
                px.pie(df, names='region', values='revenue', hole=0.5, template="plotly_dark"),
                use_container_width=True
            )

        with c2:
            st.subheader("Asset Drill-Down")
            sel_cat = st.selectbox("Select Category", options=df['region'].unique())
            sub_df = df[df['region'] == sel_cat]

            st.plotly_chart(
                px.pie(sub_df, names='symbol', values='revenue', hole=0.3, template="plotly_dark"),
                use_container_width=True
            )

        st.dataframe(df, use_container_width=True)

    else:
        st.info("Waiting for incoming stream...")

    time.sleep(2)
    st.rerun()
