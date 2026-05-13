import streamlit as st
import pandas as pd
import plotly.express as px
import threading
import json
import time
from websocket import WebSocketApp
from collections import deque

# -----------------------------
# 1. PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="WebSocket Analytics Engine", layout="wide")

# -----------------------------
# 2. SESSION STATE INIT
# -----------------------------
if "connected" not in st.session_state:
    st.session_state.connected = False

if "data_stream" not in st.session_state:
    st.session_state.data_stream = deque(maxlen=500)

if "ws_url" not in st.session_state:
    st.session_state.ws_url = ""

# -----------------------------
# 3. SAFE PARSER (works with any JSON)
# -----------------------------
def safe_parse(message):
    try:
        data = json.loads(message)
    except:
        return {
            "symbol": "raw",
            "value": 0,
            "quantity": 0,
            "category": "unparsed",
            "raw": str(message),
            "time": time.time()
        }

    if isinstance(data, dict):
        inner = data.get("data", data)

        symbol = str(inner.get("s", inner.get("symbol", "unknown"))).lower()

        price = inner.get("p", inner.get("price", 0))
        qty = inner.get("q", inner.get("quantity", 0))

        try:
            price = float(price)
        except:
            price = 0

        try:
            qty = float(qty)
        except:
            qty = 0

        return {
            "symbol": symbol,
            "value": price * qty,
            "price": price,
            "quantity": qty,
            "category": symbol.replace("usdt", "") if "usdt" in symbol else "generic",
            "time": time.time()
        }

    return {
        "symbol": "unknown",
        "value": 0,
        "quantity": 0,
        "category": "unknown",
        "time": time.time()
    }

# -----------------------------
# 4. WEBSOCKET WORKER
# -----------------------------
def run_ws(url):

    def on_message(ws, message):
        parsed = safe_parse(message)
        st.session_state.data_stream.append(parsed)

    def on_error(ws, error):
        st.session_state.connected = False
        print("WS ERROR:", error)

    def on_close(ws, a, b):
        st.session_state.connected = False
        print("WS CLOSED")

    def on_open(ws):
        print("WS CONNECTED")

    ws = WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )

    ws.run_forever()

# -----------------------------
# 5. START CONNECTION
# -----------------------------
def start_connection():
    url = st.session_state.ws_url.strip()

    if not url:
        st.warning("Enter WebSocket URL")
        return

    if st.session_state.connected:
        return

    t = threading.Thread(target=run_ws, args=(url,), daemon=True)
    t.start()

    st.session_state.connected = True

# -----------------------------
# 6. UI
# -----------------------------
st.title("📡 Universal Real-Time WebSocket Analytics Engine")

col1, col2 = st.columns([3, 1])

with col1:
    st.session_state.ws_url = st.text_input(
        "WebSocket URL",
        value=st.session_state.ws_url or
        "wss://stream.binance.com:9443/stream?streams=btcusdt@trade"
    )

with col2:
    if not st.session_state.connected:
        if st.button("🚀 Connect"):
            start_connection()
    else:
        st.success("🟢 Connected")

# -----------------------------
# 7. DATAFRAME
# -----------------------------
df = pd.DataFrame(list(st.session_state.data_stream))

# -----------------------------
# 8. DASHBOARD
# -----------------------------
if not df.empty:

    st.subheader("📊 Live Stream Analytics")

    c1, c2 = st.columns(2)

    with c1:
        if "category" in df.columns:
            fig = px.pie(df, names="category", values="value", hole=0.5)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        top = df.groupby("symbol")["value"].sum().reset_index()
        fig2 = px.bar(top, x="symbol", y="value")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📦 Live Data Feed")
    st.dataframe(df.tail(50), use_container_width=True)

else:
    st.info("Waiting for WebSocket data...")

# -----------------------------
# 9. AUTO REFRESH (CRITICAL)
# -----------------------------
if st.session_state.connected:
    time.sleep(2)
    st.rerun()
