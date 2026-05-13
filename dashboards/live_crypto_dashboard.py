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
st.set_page_config(page_title="WebSocket Analytics Engine", layout="wide")

# -----------------------------
# 2. SESSION STATE
# -----------------------------
if "status" not in st.session_state:
    st.session_state.status = "DISCONNECTED"  # DISCONNECTED / CONNECTING / LIVE / ERROR

if "data_stream" not in st.session_state:
    st.session_state.data_stream = deque(maxlen=500)

if "ws_url" not in st.session_state:
    st.session_state.ws_url = ""

if "last_error" not in st.session_state:
    st.session_state.last_error = ""

# -----------------------------
# 3. SAFE PARSER (BINANCE + GENERIC)
# -----------------------------
def safe_parse(message):
    try:
        data = json.loads(message)
    except:
        return None

    if isinstance(data, dict):

        if "data" in data:
            data = data["data"]

        symbol = data.get("s") or data.get("symbol") or "unknown"
        price = data.get("p") or data.get("price") or 0
        qty = data.get("q") or data.get("quantity") or 0

        try:
            price = float(price)
            qty = float(qty)
        except:
            return None

        return {
            "symbol": str(symbol).lower(),
            "price": price,
            "quantity": qty,
            "value": price * qty,
            "category": str(symbol).lower().replace("usdt", ""),
            "time": time.strftime("%H:%M:%S")
        }

    return None

# -----------------------------
# 4. WEBSOCKET WORKER
# -----------------------------
def run_ws(url):

    def on_open(ws):
        st.session_state.status = "LIVE"
        print("✅ CONNECTED")

    def on_message(ws, message):
        parsed = safe_parse(message)

        if parsed is None:
            print("⚠️ DROPPED:", message)
            return

        st.session_state.data_stream.append(parsed)
        print("RECEIVED:", parsed)

    def on_error(ws, error):
        st.session_state.status = "ERROR"
        st.session_state.last_error = str(error)
        print("ERROR:", error)

    def on_close(ws, a, b):
        st.session_state.status = "DISCONNECTED"
        print("CLOSED")

    ws = WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
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

    if st.session_state.status == "LIVE":
        return

    st.session_state.status = "CONNECTING"

    t = threading.Thread(target=run_ws, args=(url,), daemon=True)
    t.start()

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
    if st.button("🚀 Connect"):
        start_connection()

# -----------------------------
# 7. STATUS PANEL (IMPORTANT)
# -----------------------------
st.markdown("### 🧠 Connection Status")

if st.session_state.status == "LIVE":
    st.success("🟢 LIVE - Receiving data")
elif st.session_state.status == "CONNECTING":
    st.info("🟡 CONNECTING...")
elif st.session_state.status == "ERROR":
    st.error(f"🔴 ERROR: {st.session_state.last_error}")
else:
    st.warning("⚪ DISCONNECTED")

# -----------------------------
# 8. DATAFRAME
# -----------------------------
df = pd.DataFrame(list(st.session_state.data_stream))

# -----------------------------
# 9. DASHBOARD
# -----------------------------
if not df.empty:

    st.subheader("📊 Live Analytics")

    c1, c2 = st.columns(2)

    with c1:
        fig = px.pie(df, names="category", values="value", hole=0.5)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        top = df.groupby("symbol")["value"].sum().reset_index()
        fig2 = px.bar(top, x="symbol", y="value")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📦 Live Feed")
    st.dataframe(df.tail(50), use_container_width=True)

else:
    st.info("Waiting for incoming WebSocket data...")

# -----------------------------
# 10. AUTO REFRESH (LIVE MODE ONLY)
# -----------------------------
if st.session_state.status in ["LIVE", "CONNECTING"]:
    time.sleep(2)
    st.rerun()
