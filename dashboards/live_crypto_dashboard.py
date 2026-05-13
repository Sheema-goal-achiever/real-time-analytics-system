import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
import threading
from websocket import WebSocketApp

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Crypto Analytics 2026", layout="wide", page_icon="📈")

# --- 2. SESSION STATE INIT ---
if 'auth' not in st.session_state:
    st.session_state.update({
        'auth': False,
        'company': "",
        'map': {},
        'ws_url': "",
        'worker_started': False,
        'trades': []   # 👈 in-memory database
    })

# --- 3. BACKGROUND WORKER ---
def run_custom_stream(ws_url, inventory_map):
    try:
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

            # 👇 STORE IN MEMORY INSTEAD OF DB
            st.session_state.trades.append({
                "PRODUCT_ID": raw_symbol,
                "PRICE": price,
                "QUANTITY": quantity,
                "REVENUE": revenue,
                "REGION": category,
                "EVENT_TIME": time.time()
            })

        ws = WebSocketApp(socket_url, on_message=on_message)
        ws.run_forever()

    except Exception:
        pass


def start_worker():
    for t in threading.enumerate():
        if t.name == "CompanyWorker":
            return

    if st.session_state.ws_url and st.session_state.map:
        t = threading.Thread(
            target=run_custom_stream,
            args=(st.session_state.ws_url, st.session_state.map),
            name="CompanyWorker",
            daemon=True
        )
        t.start()
        st.session_state.worker_started = True


# --- 4. AUTH SYSTEM (NOW FAKE / LOCAL) ---
if not st.session_state.auth:
    st.title("🔐 Terminal Gateway")

    tab1, tab2 = st.tabs(["Login", "🚀 Register New Company"])

    with tab1:
        with st.form("login_form"):
            u_in = st.text_input("Company Name")
            p_in = st.text_input("Password", type="password")

            if st.form_submit_button("Enter Terminal"):
                # ⚠️ fake login (since no DB)
                if u_in and p_in:
                    st.session_state.auth = True
                    st.session_state.company = u_in
                    st.session_state.ws_url = "wss://stream.binance.com:9443"
                    st.session_state.map = {"btcusdt": "Majors", "ethusdt": "Majors"}
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab2:
        st.info("No database mode: credentials are not saved anywhere.")

else:
    # --- 5. START STREAM ---
    start_worker()

    with st.sidebar:
        st.header(f"🏢 {st.session_state.company}")

        st.divider()

        if st.button("🔓 Logout"):
            st.session_state.auth = False
            st.rerun()

    # --- 6. ANALYTICS ---
    st.title("📊 Real-Time Market Analytics")

    df = pd.DataFrame(st.session_state.trades[-200:])  # last 200 trades

    if not df.empty:
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Market Segment Volume")
            st.plotly_chart(
                px.pie(df, names='REGION', values='REVENUE', hole=0.5),
                use_container_width=True
            )

        with c2:
            st.subheader("Asset Drill-Down")
            sel_cat = st.selectbox("Select Category", options=df['REGION'].unique())
            sub_df = df[df['REGION'] == sel_cat]

            st.plotly_chart(
                px.pie(sub_df, names='PRODUCT_ID', values='REVENUE', hole=0.3),
                use_container_width=True
            )

        st.dataframe(df, use_container_width=True)

    else:
        st.info("No trade data yet. Waiting for stream...")

    time.sleep(4)
    st.rerun()
