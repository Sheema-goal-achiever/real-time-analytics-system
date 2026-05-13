import streamlit as st
import pandas as pd
import plotly.express as px
import threading
import json
import time
from websocket import WebSocketApp
from collections import deque

# -----------------------------
# 1. CONFIG
# -----------------------------
st.set_page_config(page_title="Universal WebSocket Analytics", layout="wide")

# -----------------------------
# 2. SESSION STATE INIT
# -----------------------------
if "ws_running" not in st.session_state:
    st.session_state.ws_running = False

if "data_stream" not in st.session_state:
    st.session_state.data_stream = deque(maxlen=500)

if "ws_url" not in st.session_state:
    st.session_state.ws_url = ""

# -----------------------------
# 3. SAFE PARSER (works with ANY websocket)
# -----------------------------
def safe_parse(msg):
    """
    Tries to extract useful fields from ANY JSON message.
    If unknown format → still stores raw message.
    """

    try:
        data = json.loads(msg)
    except:
        return {
            "raw": str(msg),
            "symbol": "unknown",
            "value": 0,
            "quantity": 0,
            "category": "unparsed",
            "time": time.time()
        }

    # Binance-style
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

        value = price * qty

        return {
            "symbol": symbol,
            "value": value,
            "price": price,
            "quantity": qty,
            "category": symbol.split("usdt")[0] if "usdt" in symbol else "generic",
            "time": time.time()
        }

    return {
        "raw": str(data),
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
        st.error(f"WebSocket error: {error}")

    def on_close(ws, close_status_code, close_msg):
        st.warning("WebSocket closed")

    ws = WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()

# -----------------------------
# 5. START CONNECTION
# -----------------------------
def start_connection():
    if st.session_state.ws_running:
        return

    url = st.session_state.ws_url.strip()

    if not url:
        st.warning("Enter WebSocket URL")
        return

    t = threading.Thread(target=run_ws, args=(url,), daemon=True)
    t.start()

    st.session_state.ws_running = True

# -----------------------------
# 6. UI
# -----------------------------
st.title("📡 Universal Real-Time WebSocket Analytics Engine")

col1, col2 = st.columns([3, 1])

with col1:
    st.session_state.ws_url = st.text_input(
        "WebSocket URL",
        value=st.session_state.ws_url or "wss://stream.binance.com:9443/stream?streams=btcusdt@trade"
    )

with col2:
    if st.button("🚀 Connect"):
        start_connection()

# -----------------------------
# 7. DATA PROCESSING
# -----------------------------
df = pd.DataFrame(list(st.session_state.data_stream))

# -----------------------------
# 8. DASHBOARD
# -----------------------------
if not df.empty:

    st.subheader("📊 Live Data Stream")

    c1, c2 = st.columns(2)

    with c1:
        if "category" in df.columns:
            fig = px.pie(df, names="category", values="value", hole=0.5)
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        if "symbol" in df.columns:
            top = df.groupby("symbol")["value"].sum().reset_index()
            fig2 = px.bar(top, x="symbol", y="value")
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📦 Raw Stream Data")
    st.dataframe(df.tail(50), use_container_width=True)

else:
    st.info("Waiting for WebSocket data... connect to start streaming.")

# -----------------------------
# 9. AUTO REFRESH
# -----------------------------
time.sleep(2)
st.rerun()
