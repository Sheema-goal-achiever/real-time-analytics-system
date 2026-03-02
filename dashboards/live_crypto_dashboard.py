import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
import os, json, time, sys, subprocess

st.set_page_config(page_title="Crypto Live Terminal 2026", layout="wide")

# --- 1. CONNECTION & DATABASE REPAIR ---
def get_conn():
    return st.connection("my_database", type="sql")

def initialize_database():
    conn = get_conn()
    try:
        with conn.session as s:
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS CLIENT_CONFIG (
                    ID INT AUTO_INCREMENT PRIMARY KEY,
                    COMPANY_NAME VARCHAR(255) NOT NULL UNIQUE,
                    PASSWORD VARCHAR(255) NOT NULL,
                    DATA_SOURCE_URL TEXT,
                    CATEGORY_MAP JSON
            );"""))
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS REALTIME_PURCHASES (
                    ID INT AUTO_INCREMENT PRIMARY KEY,
                    EVENT_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRODUCT_ID VARCHAR(50),
                    REVENUE DECIMAL(18, 2),
                    REGION VARCHAR(100)
            );"""))
            s.commit()
    except Exception as e:
        st.error(f"Database Setup Error: {e}")

initialize_database()

# --- 2. AUTHENTICATION ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

def login_user(name, pwd):
    conn = get_conn()
    # Plain string for conn.query to avoid Unhashable error
    df = conn.query("SELECT * FROM CLIENT_CONFIG WHERE COMPANY_NAME = :n AND PASSWORD = :p", 
                    params={"n": name, "p": pwd}, ttl=0)
    if not df.empty:
        st.session_state.logged_in = True
        st.session_state.user_company = name
        return True
    return False

# --- 3. UI LOGIC ---
if not st.session_state.logged_in:
    # ... (Keep your Login/Register forms here)
    st.title("🔐 Login to Crypto Terminal")
    u = st.text_input("Company")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        if login_user(u, p): st.rerun()
else:
    # --- 4. THE FULL DASHBOARD ---
    st.sidebar.title(f"🏢 {st.session_state.user_company}")
    
    # --- WORKER AUTO-START FIX ---
    if 'worker_started' not in st.session_state:
        # Use sys.executable to find the correct Python path on Streamlit Cloud
        subprocess.Popen([sys.executable, "test_ws.py"])
        st.session_state.worker_started = True
        st.sidebar.success("✅ Live Data Worker Active")

    # --- INVENTORY MANAGEMENT SECTION ---
    with st.expander("🛠️ Inventory & Table Management"):
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.write("### Add New Product")
            new_prod = st.text_input("Product ID (e.g. btcusdt)")
            new_rev = st.number_input("Initial Revenue", value=0.0)
            if st.button("Add to Inventory"):
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("INSERT INTO REALTIME_PURCHASES (PRODUCT_ID, REVENUE, REGION) VALUES (:id, :rv, 'Manual')"),
                              {"id": new_prod, "rv": new_rev})
                    s.commit()
                st.success(f"Added {new_prod}")

        with col_b:
            st.write("### Danger Zone")
            if st.button("🗑️ Delete All Purchase Data"):
                conn = get_conn()
                with conn.session as s:
                    s.execute(text("DELETE FROM REALTIME_PURCHASES"))
                    s.commit()
                st.warning("All market data deleted!")
                st.rerun()

    # --- 5. ANALYTICS ---
    conn = get_conn()
    df = conn.query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 100", ttl=0)

    if not df.empty:
        fig = px.line(df, x="EVENT_TIME", y="REVENUE", color="PRODUCT_ID", title="Live Market Feed")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Waiting for data... Add a product above or wait for Binance.")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    time.sleep(3)
    st.rerun()
