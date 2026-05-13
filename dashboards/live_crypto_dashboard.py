import streamlit as st
import pandas as pd
import plotly.express as px
import time
import json
import threading
from websocket import WebSocketApp

# --- PAGE CONFIG ---
st.set_page_config(page_title="Crypto Analytics 2026", layout="wide", page_icon="📈")

# --- SESSION STATE INIT ---
if "trades" not in st.session_state:
    st.session_state.trades = []

if "map" not in st.session_state:
    st.session_state.map = {"btcusdt": "Majors", "ethusdt": "Majors"}

if "ws_url" not in st.session_state:
    st.session_state.ws_url = "wss://stream.binance.com:9443"

if "worker_started" not in st.session_state:
    st.session_state.worker_started = False


# --- WEBSOCKET WORKER ---
def run_stream(ws_url, inventory_map):

    symbols = [s.strip().lower() for s in inventory_map.keys()]
    streams = "/".join([f"{s}@trade" for s in symbols])

    if "binance.com" in ws_url and "streams=" not in ws_url:
        socket_url = f"{ws_url.rstrip('/')}/stream?streams={streams}"
    else:
        socket_url = ws_url

    def on_message(ws, message):
        try:
            msg = json.loads(message)
            data = msg.get("data", msg)

            symbol = data.get("s", "").lower()
            price = float(data.get("p", 0))
            qty = float(data.get("q", 0))
            revenue = price * qty
            category = inventory_map.get(symbol, "Uncategorized")

            st.session_state.trades.append({
                "PRODUCT_ID": symbol,
                "PRICE": price,
                "QUANTITY": qty,
                "REVENUE": revenue,
                "REGION": category,
                "TIME": time.time()
            })
        except:
            pass

    ws = WebSocketApp(socket_url, on_message=on_message)
    ws.run_forever()


def start_worker():
    if not st.session_state.worker_started:
        t = threading.Thread(
            target=run_stream,
            args=(st.session_state.ws_url, st.session_state.map),
            daemon=True
        )
        t.start()
        st.session_state.worker_started = True


# --- START STREAM ---
start_worker()

# --- UI ---
st.title("📊 Real-Time Crypto Analytics")

df = pd.DataFrame(st.session_state.trades[-200:])

if not df.empty:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Market Share")
        st.plotly_chart(
            px.pie(df, names="REGION", values="REVENUE", hole=0.5),
            use_container_width=True
        )

    with c2:
        st.subheader("Asset Breakdown")
        cat = st.selectbox("Category", df["REGION"].unique())
        filtered = df[df["REGION"] == cat]

        st.plotly_chart(
            px.pie(filtered, names="PRODUCT_ID", values="REVENUE", hole=0.4),
            use_container_width=True
        )

    st.dataframe(df, use_container_width=True)

else:
    st.info("Waiting for live trade data...")

time.sleep(3)
st.rerun()
